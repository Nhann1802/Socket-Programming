import socket
import os
import threading
from pathlib import Path
from typing import Optional, Callable
from config import FILE_CHUNK_SIZE, CONNECT_TIMEOUT, MAX_FILE_SIZE
from network.protocol import send_frame, FrameType
from network.tcp_client import TCPClient
from .progress import TransferProgress


class FileSender:
    @staticmethod
    def send_file(
        target_ip: str,
        target_port: int,
        own_name: str,
        own_tcp_port: int,
        filepath: str,
        progress_callback: Optional[Callable[[str], None]] = None,
        timeout: float = CONNECT_TIMEOUT,
        cancel_event: Optional[threading.Event] = None,
        on_socket: Optional[Callable[[socket.socket], None]] = None,
        on_progress: Optional[Callable[[TransferProgress], None]] = None,
    ) -> bool:
        sock = None
        progress = None
        filename = Path(filepath).name
        try:
            path = Path(filepath).resolve()
            with path.open('rb') as file:
                size = os.fstat(file.fileno()).st_size
                if size > MAX_FILE_SIZE:
                    raise ValueError("Tệp vượt giới hạn 10 GiB.")
                if cancel_event and cancel_event.is_set():
                    raise InterruptedError("Đã hủy truyền tệp.")
                sock, lock, remote_name = TCPClient.connect_to_peer(
                    ip=target_ip, tcp_port=target_port, own_name=own_name,
                    own_tcp_port=own_tcp_port, channel='file', timeout=timeout,
                    on_socket=on_socket,
                )
                send_frame(sock, {'type': FrameType.FILE, 'filename': path.name, 'size': size}, send_lock=lock)
                progress = TransferProgress(filename, size, "Gửi")
                if on_progress:
                    on_progress(progress)
                remaining = size
                while remaining:
                    if cancel_event and cancel_event.is_set():
                        raise InterruptedError("Đã hủy truyền tệp.")
                    chunk = file.read(min(FILE_CHUNK_SIZE, remaining))
                    if not chunk:
                        raise OSError("Tệp nguồn đã bị thay đổi trong lúc gửi.")
                    sock.sendall(chunk)
                    remaining -= len(chunk)
                    if progress.update(len(chunk)) and on_progress:
                        on_progress(progress)
                if cancel_event and cancel_event.is_set():
                    raise InterruptedError("Đã hủy truyền tệp.")
            if progress_callback:
                progress_callback(f"[✓] Gửi 100% [{filename}] tới [{remote_name}].")
            return True
        except Exception as error:
            reason = "Đã hủy truyền tệp." if cancel_event and cancel_event.is_set() else str(error)
            if progress_callback:
                progress_callback(f"[!] Gửi [{filename}] thất bại: {reason}")
            return False
        finally:
            if progress and on_progress:
                progress.finished = True
                on_progress(progress)
            if sock:
                sock.close()
