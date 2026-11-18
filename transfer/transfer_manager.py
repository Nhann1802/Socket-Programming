import socket
import threading
from typing import Optional, Callable
from config import DEFAULT_DOWNLOAD_DIR
from .file_sender import FileSender
from .file_receiver import FileReceiver
from .progress import TransferProgress


class TransferManager:
    def __init__(self, download_dir: str = DEFAULT_DOWNLOAD_DIR,
                 on_notify: Optional[Callable[[str], None]] = None,
                 on_progress: Optional[Callable[[TransferProgress], None]] = None):
        self.download_dir = download_dir
        self.on_notify = on_notify or print
        self.on_progress = on_progress
        self._active_workers = []
        self._sockets = set()
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()

    def send_file_async(self, target_ip, target_port, own_name, own_tcp_port, filepath):
        return self._start_worker(FileSender.send_file, {
            'target_ip': target_ip, 'target_port': target_port,
            'own_name': own_name, 'own_tcp_port': own_tcp_port, 'filepath': filepath,
        })

    def handle_incoming_file(self, sock, sender_name, advertised_port, client_ip):
        return self._start_worker(FileReceiver.receive_file, {
            'sock': sock, 'sender_name': sender_name, 'download_dir': self.download_dir,
        }, sock)

    def _register_socket(self, sock):
        with self._lock:
            if self._cancel_event.is_set():
                sock.close()
                raise InterruptedError("Đã hủy truyền tệp.")
            self._sockets.add(sock)

    def _start_worker(self, target, arguments, incoming_sock=None):
        def run():
            try:
                target(**arguments)
            finally:
                with self._lock:
                    self._sockets = {sock for sock in self._sockets if sock.fileno() != -1}

        arguments.update(progress_callback=self.on_notify, cancel_event=self._cancel_event, on_progress=self.on_progress)
        if incoming_sock is None:
            arguments['on_socket'] = self._register_socket
        worker = threading.Thread(target=run, name='FileTransferWorker', daemon=False)
        with self._lock:
            if self._cancel_event.is_set():
                if incoming_sock:
                    incoming_sock.close()
                return None
            if incoming_sock:
                self._sockets.add(incoming_sock)
            self._active_workers = [thread for thread in self._active_workers if thread.is_alive()]
            self._active_workers.append(worker)
            worker.start()
        return worker

    def shutdown(self):
        with self._lock:
            self._cancel_event.set()
            sockets = list(self._sockets)
            workers = list(self._active_workers)
        # shutdown đánh thức recv/send đang chờ trước khi đợi worker dọn file tạm.
        for sock in sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        for worker in workers:
            worker.join()
        with self._lock:
            self._active_workers.clear()
            self._sockets.clear()

    def active_transfers_count(self):
        with self._lock:
            return sum(worker.is_alive() for worker in self._active_workers)
