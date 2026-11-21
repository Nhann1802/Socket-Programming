import re
import socket
import tempfile
import threading
from pathlib import Path
from typing import Optional, Callable
from config import FILE_CHUNK_SIZE, DEFAULT_DOWNLOAD_DIR, MAX_FILE_SIZE
from network.protocol import recv_header, recv_exact, FrameType, ProtocolError
from .progress import TransferProgress


class FileReceiver:
    @staticmethod
    def safe_filename(filename: str) -> str:
        if not isinstance(filename, str):
            raise ProtocolError("Tên tệp phải là chuỗi.")
        name = re.split(r"[/\\]", filename)[-1]
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', name).rstrip(' .')
        if not name:
            name = "downloaded_file"
        base = name.split('.')[0].rstrip(' ').upper()
        if base in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} or re.fullmatch(r"(?:COM|LPT)[1-9¹²³]", base):
            name = '_' + name
        # Chừa chỗ cho hậu tố khi trùng tên và giới hạn đường dẫn trên Windows.
        if len(name.encode('utf-16-le')) // 2 > 100:
            name = name.encode('utf-16-le')[:200].decode('utf-16-le', errors='ignore').rstrip(' .')
        return name

    @staticmethod
    def _save_unique(temp_path: Path, target_dir: Path, filename: str) -> Path:
        path = target_dir / filename
        counter = 0
        while True:
            try:
                # Tạo độc quyền để hai worker không cùng giữ một tên đích.
                with path.open('xb'):
                    pass
                break
            except FileExistsError:
                counter += 1
                original = Path(filename)
                path = target_dir / f"{original.stem}_{counter}{original.suffix}"
        try:
            temp_path.replace(path)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return path

    @staticmethod
    def receive_file(
        sock: socket.socket,
        sender_name: str,
        download_dir: str = DEFAULT_DOWNLOAD_DIR,
        progress_callback: Optional[Callable[[str], None]] = None,
        cancel_event: Optional[threading.Event] = None,
        on_progress: Optional[Callable[[TransferProgress], None]] = None,
    ) -> Optional[str]:
        temp_path = None
        progress = None
        try:
            sock.settimeout(15.0)
            header = recv_header(sock)
            if header.get('type') != FrameType.FILE:
                raise ProtocolError("Frame trên kênh tệp phải có loại FILE.")
            size = header.get('size')
            if type(size) is not int or not 0 <= size <= MAX_FILE_SIZE:
                raise ProtocolError("Kích thước tệp phải là số nguyên từ 0 đến 10 GiB.")
            filename = FileReceiver.safe_filename(header.get('filename', 'downloaded_file'))
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Đã hủy truyền tệp.")
            target_dir = Path(download_dir).resolve()
            target_dir.mkdir(parents=True, exist_ok=True)
            progress = TransferProgress(filename, size, "Nhận")
            if on_progress:
                on_progress(progress)
            sock.settimeout(30.0)
            with tempfile.NamedTemporaryFile(mode='wb', dir=target_dir, prefix='.lanchat-', suffix='.part', delete=False) as file:
                temp_path = Path(file.name)
                remaining = size
                while remaining:
                    if cancel_event and cancel_event.is_set():
                        raise InterruptedError("Đã hủy truyền tệp.")
                    chunk = recv_exact(sock, min(FILE_CHUNK_SIZE, remaining))
                    file.write(chunk)
                    remaining -= len(chunk)
                    if progress.update(len(chunk)) and on_progress:
                        on_progress(progress)
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Đã hủy truyền tệp.")
            destination = FileReceiver._save_unique(temp_path, target_dir, filename)
            if progress_callback:
                progress_callback(f"[✓] Nhận 100% từ [{sender_name}]: {destination}")
            return str(destination)
        except Exception as error:
            reason = "Đã hủy truyền tệp." if cancel_event and cancel_event.is_set() else str(error)
            if progress_callback:
                progress_callback(f"[!] Nhận tệp từ [{sender_name}] thất bại: {reason}")
            return None
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)
            if progress and on_progress:
                progress.finished = True
                on_progress(progress)
            sock.close()
