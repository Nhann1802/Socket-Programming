import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from config import MAX_FILE_SIZE
from network.protocol import send_frame
from transfer.file_receiver import FileReceiver
from transfer.transfer_manager import TransferManager
from transfer.progress import TransferProgress
from ui.progress_display import ProgressDisplay


class TestTransferSafety(unittest.TestCase):
    def receive(self, directory, filename, size, payload=b''):
        sender, receiver = socket.socketpair()
        messages = []
        results = []
        thread = threading.Thread(target=lambda: results.append(FileReceiver.receive_file(
            receiver, 'Sender', str(directory), messages.append)))
        thread.start()
        send_frame(sender, {'type': 'FILE', 'filename': filename, 'size': size}, payload)
        sender.close()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        return results[0], messages

    def test_rejects_invalid_sizes_before_creating_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            for size in [-1, MAX_FILE_SIZE + 1, 10**18, True, '12', 1.5, None]:
                with self.subTest(size=size):
                    target = Path(directory) / 'not-created'
                    result, messages = self.receive(target, 'invalid.bin', size)
                    self.assertIsNone(result)
                    self.assertFalse(target.exists())
                    self.assertEqual(len(messages), 1)
                    self.assertIn('thất bại', messages[0])

    def test_concurrent_same_name_keeps_every_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            pairs = [socket.socketpair() for _ in range(8)]
            results = []
            threads = [threading.Thread(target=lambda sock=receiver: results.append(
                FileReceiver.receive_file(sock, 'Sender', directory))) for _, receiver in pairs]
            for thread in threads:
                thread.start()
            for sender, _ in pairs:
                send_frame(sender, {'type': 'FILE', 'filename': 'same.bin', 'size': 65536})
            for index, (sender, _) in enumerate(pairs):
                sender.sendall(bytes([index]) * 65536)
                sender.close()
            for thread in threads:
                thread.join(5)
                self.assertFalse(thread.is_alive())
            self.assertEqual(len(set(results)), 8)
            files = list(Path(directory).iterdir())
            self.assertEqual(len(files), 8)
            self.assertEqual({file.read_bytes() for file in files}, {bytes([index]) * 65536 for index in range(8)})

    def test_windows_names_and_path_traversal(self):
        names = {
            '..\\escape.txt': 'escape.txt', '../escape.txt': 'escape.txt',
            'bad:*?"<>|.txt': 'bad_______.txt', 'CON': '_CON', 'nul.txt': '_nul.txt',
            'LPT1.pdf': '_LPT1.pdf', 'name. ': 'name', '..': 'downloaded_file',
            'C:secret.txt': 'C_secret.txt', 'tệp [1] #.txt': 'tệp [1] #.txt',
            '😀' * 100 + '.txt': '😀' * 50,
        }
        for raw, safe in names.items():
            with self.subTest(name=raw), tempfile.TemporaryDirectory() as directory:
                path, messages = self.receive(directory, raw, 4, b'DATA')
                self.assertIsNotNone(path)
                self.assertEqual(Path(path).name, safe)
                self.assertEqual(Path(path).parent, Path(directory).resolve())
                self.assertEqual(Path(path).read_bytes(), b'DATA')
                self.assertIn(str(path), messages[0])

    def test_empty_file_and_one_final_line(self):
        with tempfile.TemporaryDirectory() as directory:
            result, messages = self.receive(directory, 'empty.txt', 0)
            self.assertEqual(Path(result).stat().st_size, 0)
            self.assertEqual(len(messages), 1)
            self.assertIn('100%', messages[0])

    def test_interrupted_file_is_not_committed(self):
        with tempfile.TemporaryDirectory() as directory:
            result, messages = self.receive(directory, 'partial.bin', 100, b'partial')
            self.assertIsNone(result)
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertEqual(len(messages), 1)
            self.assertIn('thất bại', messages[0])

    def test_failed_rename_cleans_its_reservation_only(self):
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / 'same.bin'
            old.write_bytes(b'OLD')
            with patch.object(Path, 'replace', side_effect=PermissionError('rename denied')):
                result, messages = self.receive(directory, 'same.bin', 4, b'DATA')
            self.assertIsNone(result)
            self.assertEqual(old.read_bytes(), b'OLD')
            self.assertEqual(list(Path(directory).iterdir()), [old])
            self.assertIn('rename denied', messages[0])

    def test_shutdown_unblocks_receiver_and_removes_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            sender, receiver = socket.socketpair()
            messages = []
            manager = TransferManager(directory, messages.append)
            worker = manager.handle_incoming_file(receiver, 'Sender', 5001, '127.0.0.1')
            send_frame(sender, {'type': 'FILE', 'filename': 'cancel.bin', 'size': 200000}, b'X' * 100)
            deadline = time.monotonic() + 2
            while not list(Path(directory).glob('*.part')) and time.monotonic() < deadline:
                threading.Event().wait(.01)
            self.assertTrue(list(Path(directory).glob('*.part')))
            manager.shutdown()
            sender.close()
            self.assertFalse(worker.is_alive())
            self.assertFalse(worker.daemon)
            self.assertEqual(manager.active_transfers_count(), 0)
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertEqual(len(messages), 1)
            self.assertIn('hủy', messages[0])
            late_sender, late_receiver = socket.socketpair()
            self.assertIsNone(manager.handle_incoming_file(late_receiver, 'Late', 5001, '127.0.0.1'))
            self.assertEqual(late_receiver.fileno(), -1)
            late_sender.close()

    def test_display_tracks_multiple_transfers_and_removes_finished(self):
        display = ProgressDisplay()
        first = TransferProgress('first.txt', 1000)
        second = TransferProgress('second.txt', 1000, 'Nhận')
        display.update(first)
        display.update(second)
        first.update(357)
        with patch('prompt_toolkit.application.get_app') as app:
            app.return_value.output.get_size.return_value.columns = 80
            text = display.render()
            self.assertEqual(len(text.splitlines()), 2)
            self.assertIn('35.7%', text)
            first.finished = True
            display.update(first)
            self.assertNotIn('first.txt', display.render())
            second.finished = True
            display.update(second)
            self.assertEqual(display.render(), '')

    def test_bar_handles_empty_and_long_unicode_names(self):
        self.assertIn('100.0%', TransferProgress('empty', 0).render_bar(80))
        from unicodedata import east_asian_width
        text = TransferProgress('漢' * 100, 100).render_bar(60)
        self.assertLessEqual(sum(2 if east_asian_width(char) in ('W', 'F') else 1 for char in text), 60)

    def test_shutdown_cancels_stalled_outgoing_handshake(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.bin'
            source.write_bytes(b'DATA')
            listener = socket.socket()
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            listener.settimeout(3)
            messages = []
            manager = TransferManager(directory, messages.append)
            worker = manager.send_file_async('127.0.0.1', listener.getsockname()[1], 'A', 5001, str(source))
            remote, _ = listener.accept()
            start = time.monotonic()
            manager.shutdown()
            elapsed = time.monotonic() - start
            remote.close()
            listener.close()
            self.assertFalse(worker.is_alive())
            self.assertLess(elapsed, 2)
            self.assertEqual(len(messages), 1)
            self.assertIn('hủy', messages[0])


if __name__ == '__main__':
    unittest.main()
