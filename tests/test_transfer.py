import unittest
import os
import tempfile
import socket
import threading
from transfer.progress import TransferProgress
from transfer.file_receiver import FileReceiver
from transfer.file_sender import FileSender
from config import DEFAULT_DOWNLOAD_DIR


class TestTransferModules(unittest.TestCase):
    def test_progress(self):
        tp = TransferProgress("test.txt", 1000, "Gửi")
        self.assertFalse(tp.update(50))
        self.assertTrue(tp.update(50))  # 100 / 1000 = 10%
        self.assertIn("10%", tp.format_status())

    def test_file_transfer_over_loopback(self):
        # Create temp test file
        with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".txt") as tf:
            tf.write("Hello P2P File Transfer Test Content!" * 500)
            src_path = tf.name

        download_dir = tempfile.mkdtemp()
        received_path = None

        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        port = server_sock.getsockname()[1]

        def server_thread():
            nonlocal received_path
            client, _ = server_sock.accept()
            # In real system, INTRO is consumed by TCPServer, but here we can simulate or directly receive
            from network.protocol import recv_frame
            intro, _ = recv_frame(client)
            from network.protocol import send_frame, FrameType
            send_frame(client, {"type": FrameType.INTRO, "name": "Server", "tcp_port": port, "channel": "file"})
            received_path = FileReceiver.receive_file(client, "Client", download_dir=download_dir)
            server_sock.close()

        t = threading.Thread(target=server_thread, daemon=True)
        t.start()

        success = FileSender.send_file(
            target_ip="127.0.0.1",
            target_port=port,
            own_name="Client",
            own_tcp_port=9999,
            filepath=src_path,
        )
        t.join(timeout=5.0)

        self.assertTrue(success)
        self.assertIsNotNone(received_path)
        self.assertTrue(os.path.exists(received_path))

        with open(src_path, "rb") as f1, open(received_path, "rb") as f2:
            self.assertEqual(f1.read(), f2.read())

        # Cleanup
        try:
            os.remove(src_path)
            if received_path and os.path.exists(received_path):
                os.remove(received_path)
            os.rmdir(download_dir)
        except OSError:
            pass


if __name__ == "__main__":
    unittest.main()
