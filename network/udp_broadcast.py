import socket
import threading
import time
from typing import Callable, Optional
from config import (
    DEFAULT_UDP_PORT,
    DEFAULT_BROADCAST_IP,
    HEARTBEAT_INTERVAL,
)
from network.protocol import encode_hello


class UDPBroadcaster:
    """
    Periodically transmits presence announcements (HELLO packets) over UDP broadcast.
    """
    def __init__(
        self,
        name: str,
        tcp_port: int,
        status_provider: Optional[Callable[[], str]] = None,
        broadcast_ip: str = DEFAULT_BROADCAST_IP,
        udp_port: int = DEFAULT_UDP_PORT,
        interval: float = HEARTBEAT_INTERVAL,
    ):
        self.name = name
        self.tcp_port = tcp_port
        self.status_provider = status_provider or (lambda: "online")
        self.broadcast_ip = broadcast_ip
        self.udp_port = udp_port
        self.interval = interval

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

    def start(self) -> None:
        """Initializes UDP broadcast socket and starts sender thread."""
        if self._thread and self._thread.is_alive():
            return

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Enable broadcast transmission
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="UDPBroadcaster", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Signals broadcaster to terminate and waits for thread exit."""
        self._stop_event.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run_loop(self) -> None:
        """Main loop: broadcasts presence immediately on start, then at fixed intervals."""
        while not self._stop_event.is_set():
            try:
                current_status = self.status_provider()
                packet = encode_hello(self.name, self.tcp_port, current_status)
                if self._sock:
                    self._sock.sendto(packet, (self.broadcast_ip, self.udp_port))
            except Exception:
                # Silently catch transient network errors so the thread keeps running
                pass

            # Wait for interval or instant wakeup on stop
            if self._stop_event.wait(self.interval):
                break
