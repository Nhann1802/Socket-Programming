import socket
import threading
import sys
from typing import Callable, Optional
from config import DEFAULT_UDP_PORT, get_local_ip
from network.protocol import parse_hello


class UDPListener:
    """
    Listens for UDP presence broadcast packets on port 9999,
    parses HELLO messages, filters self-announcements,
    and invokes peer discovery callback.
    """
    def __init__(
        self,
        on_peer_discovered: Callable[[str, str, int, str], None],
        own_tcp_port: int,
        own_name: str = "",
        bind_ip: str = "",
        udp_port: int = DEFAULT_UDP_PORT,
    ):
        self.on_peer_discovered = on_peer_discovered
        self.own_tcp_port = own_tcp_port
        self.own_name = own_name
        self.bind_ip = bind_ip
        self.udp_port = udp_port

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self._local_ips = {"127.0.0.1", get_local_ip()}

    def start(self) -> None:
        """Binds to UDP port with address reuse and starts listener thread."""
        if self._thread and self._thread.is_alive():
            return

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Allow port reuse so multiple instances can run locally or co-exist
        if hasattr(socket, "SO_REUSEADDR"):
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass

        # Windows-specific: Allow broadcast reception on all interfaces
        self._sock.bind((self.bind_ip, self.udp_port))
        self._sock.settimeout(1.0)  # Check stop_event periodically

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="UDPListener", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Terminates listener thread and closes socket."""
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
        """Continuous receiving loop."""
        while not self._stop_event.is_set():
            try:
                data, (src_ip, _) = self._sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break

            parsed = parse_hello(data)
            if not parsed:
                continue

            name, tcp_port, status = parsed

            # Ignore own announcement:
            # Matches if advertised TCP port matches own TCP port and source IP is local,
            # or if name matches and advertised port matches.
            is_self = (tcp_port == self.own_tcp_port) and (
                src_ip in self._local_ips or (self.own_name and name == self.own_name)
            )
            if is_self:
                continue

            # Notify discovery layer
            try:
                self.on_peer_discovered(name, src_ip, tcp_port, status)
            except Exception:
                # Listener must remain resilient to callback errors
                pass
