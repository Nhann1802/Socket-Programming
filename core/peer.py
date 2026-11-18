import time
from dataclasses import dataclass, field


@dataclass
class Peer:
    """Represents a discovered network peer in the LAN."""
    name: str
    ip: str
    tcp_port: int
    status: str = "online"
    last_seen: float = field(default_factory=time.monotonic)

    @property
    def key(self) -> tuple[str, int]:
        """Unique identifier key for the peer."""
        return (self.ip, self.tcp_port)

    def is_expired(self, timeout_sec: float = 10.0) -> bool:
        """Checks if peer has timed out without heartbeats."""
        return (time.monotonic() - self.last_seen) > timeout_sec

    def update_presence(self, status: str = "online") -> None:
        """Refreshes last_seen timestamp and updates status."""
        self.last_seen = time.monotonic()
        if status in ("online", "away"):
            self.status = status
