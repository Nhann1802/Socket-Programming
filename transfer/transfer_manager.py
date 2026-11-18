import socket
import threading
from typing import Optional, Callable
from config import DEFAULT_DOWNLOAD_DIR
from .file_sender import FileSender
from .file_receiver import FileReceiver


class TransferManager:
    """
    Coordinates asynchronous file transfers on dedicated worker threads.
    Guarantees non-blocking file sending and receiving.
    """
    def __init__(
        self,
        download_dir: str = DEFAULT_DOWNLOAD_DIR,
        on_notify: Optional[Callable[[str], None]] = None,
    ):
        self.download_dir = download_dir
        self.on_notify = on_notify or print
        self._active_workers: list[threading.Thread] = []
        self._lock = threading.Lock()

    def send_file_async(
        self,
        target_ip: str,
        target_port: int,
        own_name: str,
        own_tcp_port: int,
        filepath: str,
    ) -> threading.Thread:
        """Starts background thread to transmit a file."""
        worker = threading.Thread(
            target=FileSender.send_file,
            kwargs={
                "target_ip": target_ip,
                "target_port": target_port,
                "own_name": own_name,
                "own_tcp_port": own_tcp_port,
                "filepath": filepath,
                "progress_callback": self.on_notify,
            },
            name="FileSenderWorker",
            daemon=True,
        )
        self._track_and_start(worker)
        return worker

    def handle_incoming_file(
        self,
        sock: socket.socket,
        sender_name: str,
        advertised_port: int,
        client_ip: str,
    ) -> threading.Thread:
        """Starts background thread to receive an incoming file stream."""
        worker = threading.Thread(
            target=FileReceiver.receive_file,
            kwargs={
                "sock": sock,
                "sender_name": sender_name,
                "download_dir": self.download_dir,
                "progress_callback": self.on_notify,
            },
            name=f"FileReceiverWorker-{sender_name}",
            daemon=True,
        )
        self._track_and_start(worker)
        return worker

    def _track_and_start(self, worker: threading.Thread) -> None:
        with self._lock:
            self._active_workers = [t for t in self._active_workers if t.is_alive()]
            self._active_workers.append(worker)
        worker.start()

    def active_transfers_count(self) -> int:
        """Returns the number of currently active file transfers."""
        with self._lock:
            return sum(1 for t in self._active_workers if t.is_alive())
