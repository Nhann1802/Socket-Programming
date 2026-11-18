import os
import socket
from pathlib import Path
from typing import Optional, Callable
from config import FILE_CHUNK_SIZE, DEFAULT_DOWNLOAD_DIR
from network.protocol import recv_header, recv_exact, FrameType
from .progress import TransferProgress


class FileReceiver:
    """
    Receives and writes streaming file chunks from incoming TCP connections.
    """
    @staticmethod
    def receive_file(
        sock: socket.socket,
        sender_name: str,
        download_dir: str = DEFAULT_DOWNLOAD_DIR,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Optional[str]:
        """
        Receives streamed file and writes to download_dir.
        Returns the absolute destination path if successful, None otherwise.
        """
        target_dir = Path(download_dir).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Read FILE frame header
            sock.settimeout(15.0)
            header = recv_header(sock)
            if header.get("type") != FrameType.FILE:
                if progress_callback:
                    progress_callback(f"[!] Nhận loại frame không hợp lệ trên kênh file: {header.get('type')}")
                return None

            raw_filename = header.get("filename", "unknown_file")
            # Prevent path traversal attacks
            safe_filename = Path(raw_filename).name
            if not safe_filename:
                safe_filename = "downloaded_file"

            total_size = int(header.get("size", 0))

            # 2. Avoid overwriting existing files: append counter
            dest_path = target_dir / safe_filename
            counter = 1
            stem = dest_path.stem
            suffix = dest_path.suffix
            while dest_path.exists():
                dest_path = target_dir / f"{stem}_{counter}{suffix}"
                counter += 1

            progress = TransferProgress(safe_filename, total_size, direction="Nhận")
            if progress_callback:
                progress_callback(
                    f"[*] Đang nhận tệp [{safe_filename}] ({total_size / 1024:.1f} KB) từ [{sender_name}]..."
                )

            # 3. Stream chunks directly to disk
            sock.settimeout(30.0)
            remaining = total_size
            with open(dest_path, "wb") as f:
                while remaining > 0:
                    read_len = min(FILE_CHUNK_SIZE, remaining)
                    chunk = recv_exact(sock, read_len)
                    f.write(chunk)
                    remaining -= len(chunk)
                    if progress.update(len(chunk)) and progress_callback:
                        progress_callback(progress.format_status())

            if progress_callback:
                progress_callback(f"[✓] Đã nhận thành công [{safe_filename}] và lưu tại: {dest_path}")

            return str(dest_path)

        except Exception as e:
            if progress_callback:
                progress_callback(f"[!] Lỗi khi nhận tệp từ [{sender_name}]: {e}")
            return None

        finally:
            try:
                sock.close()
            except OSError:
                pass
