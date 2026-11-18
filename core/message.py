import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Message:
    """Represents a chat or file transfer event message."""
    sender: str
    receiver: str
    content: str
    timestamp: float = field(default_factory=time.time)
    is_file: bool = False
    file_path: Optional[str] = None

    def formatted_time(self) -> str:
        """Returns time formatted as HH:MM:SS."""
        return time.strftime("%H:%M:%S", time.localtime(self.timestamp))
