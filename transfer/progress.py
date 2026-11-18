import time
import threading
import unicodedata


class TransferProgress:
    def __init__(self, filename: str, total_bytes: int, direction: str = "Gửi"):
        self.filename = filename
        self.total_bytes = total_bytes
        self.direction = direction
        self.transferred = 0
        self.last_percent = -1
        self.start_time = time.monotonic()
        self.finished = False
        self._lock = threading.Lock()

    def update(self, chunk_size: int) -> bool:
        with self._lock:
            self.transferred = min(self.total_bytes, self.transferred + chunk_size)
            percent = int(self.transferred / self.total_bytes * 100) if self.total_bytes else 100

        # Giữ giá trị trả về cũ; giao diện mới redraw theo thời gian, không dùng mốc này.
        if percent != self.last_percent and (percent % 10 == 0 or percent == 100):
            self.last_percent = percent
            return True
        return False

    def format_status(self) -> str:
        percent = self.transferred / self.total_bytes * 100 if self.total_bytes else 100
        cur_kb = self.transferred / 1024
        tot_kb = self.total_bytes / 1024
        if tot_kb >= 1024:
            size_str = f"{cur_kb / 1024:.2f}/{tot_kb / 1024:.2f} MB"
        else:
            size_str = f"{cur_kb:.1f}/{tot_kb:.1f} KB"

        return f"[{self.direction}] {self.filename}: {percent:.0f}% ({size_str})"

    def render_bar(self, columns: int) -> str:
        with self._lock:
            percent = self.transferred / self.total_bytes * 100 if self.total_bytes else 100
        width = max(3, min(24, columns // 4))
        filled = int(width * percent / 100)
        bar = '#' * filled + '-' * (width - filled)
        label = f"[{self.direction}] "
        ending = f" [{bar}] {percent:5.1f}%"
        available = max(1, columns - len(label) - len(ending))
        name = ''
        cells = 0
        for char in self.filename:
            size = 0 if unicodedata.combining(char) else (2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1)
            if cells + size > available:
                name = name[:-1] + '…'
                break
            name += char
            cells += size
        return f"{label}{name}{ending}"[:columns]
