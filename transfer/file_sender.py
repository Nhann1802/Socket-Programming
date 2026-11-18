import os
import socket
from pathlib import Path
from typing import Optional, Callable
from config import FILE_CHUNK_SIZE, CONNECT_TIMEOUT
from network.protocol import send_frame, FrameType
from network.tcp_client import TCPClient
from .progress import TransferProgress


class FileSender:
    """
    Sends a file to a remote peer over an independent TCP channel (channel='file').
    """
    @staticmethod
    def send_file(
        target_ip: str,
        target_port: int,
        own_name: str,
        own_tcp_port: int,
        filepath: str,
        progress_callback: Optional[Callable[[str], None]] = None,
        timeout: float = CONNECT_TIMEOUT,
    ) -> bool:
        """
        Transmits file to target peer.
        Returns True if transfer succeeds, False otherwise.
        """
        path = Path(filepath).resolve()
        if not path.is_file():
            if progress_callback:
                progress_callback(f"[!] Tệp không tồn tại: {filepath}")
            return False

        filesize = path.stat().st_size
        filename = path.name

        sock: Optional[socket.socket] = None
        try:
            # 1. Connect to peer with channel="file"
            sock, send_lock, remote_name = TCPClient.connect_to_peer(
                ip=target_ip,
                tcp_port=target_port,
                own_name=own_name,
                own_tcp_port=own_tcp_port,
                channel="file",
                timeout=timeout,
            )

            # 2. Transmit FILE frame header
            file_header = {
                "type": FrameType.FILE,
                "filename": filename,
                "size": filesize,
            }
            send_frame(sock, file_header, payload=b"", send_lock=send_lock)

            # 3. Stream file chunks
            progress = TransferProgress(filename, filesize, direction="Gửi")
            if progress_callback:
                progress_callback(f"[*] Bắt đầu gửi [{filename}] ({filesize / 1024:.1f} KB) tới [{remote_name}]...")

            with open(path, "rb") as f:
                while True:
                    chunk = f.read(FILE_CHUNK_SIZE)
                    if not chunk:
                        break
                    sock.sendall(chunk)
                    if progress.update(len(chunk)) and progress_callback:
                        progress_callback(progress.format_status())

            if progress_callback:
                progress_callback(f"[✓] Gửi thành công [{filename}] tới [{remote_name}]!")
            return True

        except Exception as e:
            if progress_callback:
                progress_callback(f"[!] Lỗi khi gửi tệp [{filename}]: {e}")
            return False

        finally:
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass
