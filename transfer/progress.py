import time


class TransferProgress:
    """
    Helper to track and display progress percentage of file transfers.
    """
    def __init__(self, filename: str, total_bytes: int, direction: str = "Gửi"):
        self.filename = filename
        self.total_bytes = max(1, total_bytes)
        self.direction = direction
        self.transferred = 0
        self.last_percent = -1
        self.start_time = time.monotonic()

    def update(self, chunk_size: int) -> bool:
        """
        Increments transferred count.
        Returns True if percentage crossed a new milestone (every 10% or 100%).
        """
        self.transferred = min(self.total_bytes, self.transferred + chunk_size)
        percent = int((self.transferred / self.total_bytes) * 100)

        # Update on every 10% step or at completion
        if percent != self.last_percent and (percent % 10 == 0 or percent == 100):
            self.last_percent = percent
            return True
        return False

    def format_status(self) -> str:
        """Renders formatted status text."""
        percent = (self.transferred / self.total_bytes) * 100
        cur_kb = self.transferred / 1024
        tot_kb = self.total_bytes / 1024
        if tot_kb >= 1024:
            size_str = f"{cur_kb / 1024:.2f}/{tot_kb / 1024:.2f} MB"
        else:
            size_str = f"{cur_kb:.1f}/{tot_kb:.1f} KB"

        return f"[{self.direction}] {self.filename}: {percent:.0f}% ({size_str})"
