import socket
import threading
import time
import ipaddress
import os
import subprocess
import re
from typing import Callable, Optional
from config import (
    DEFAULT_UDP_PORT,
    DEFAULT_BROADCAST_IP,
    HEARTBEAT_INTERVAL,
)
from network.protocol import encode_hello


def get_broadcast_interfaces(primary_ip: str = "") -> list:
    """
    Returns (local IPv4, subnet broadcast) pairs for active Windows adapters.
    """
    interfaces = set()
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["ipconfig"], capture_output=True, text=True, timeout=3,
                check=False, encoding="oem", errors="replace",
            )
            current_ip = None
            for line in result.stdout.splitlines():
                ip_match = re.search(r"IPv4[^:]*:\s*([0-9.]+)", line, re.I)
                mask_match = re.search(r"Subnet Mask[^:]*:\s*([0-9.]+)", line, re.I)
                if ip_match:
                    current_ip = ip_match.group(1)
                elif mask_match and current_ip:
                    try:
                        interface = ipaddress.IPv4Interface(f"{current_ip}/{mask_match.group(1)}")
                        if not interface.ip.is_loopback and not interface.ip.is_link_local:
                            interfaces.add((str(interface.ip), str(interface.network.broadcast_address)))
                    except ValueError:
                        pass
                    current_ip = None
        except (OSError, subprocess.SubprocessError):
            pass
    # Fallback for non-Windows systems or when ipconfig could not be parsed.
    if not interfaces:
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if ip and not ip.startswith(("127.", "169.254.")):
                    interfaces.add((ip, DEFAULT_BROADCAST_IP))
        except OSError:
            pass
    if primary_ip and primary_ip not in ("255.255.255.255", "127.255.255.255"):
        if primary_ip.startswith("127."):
            interfaces = {("127.0.0.1", primary_ip)}
        else:
            interfaces = {(ip, primary_ip) for ip, _ in interfaces}
    return sorted(interfaces)


def get_broadcast_destinations(primary_ip: str) -> set:
    """Compatibility helper returning broadcast destinations only."""
    return {destination for _, destination in get_broadcast_interfaces(primary_ip)}


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
        self._sockets = []

    def start(self) -> None:
        """Initializes UDP broadcast socket and starts sender thread."""
        if self._thread and self._thread.is_alive():
            return

        for local_ip, destination in get_broadcast_interfaces(self.broadcast_ip):
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.bind((local_ip, 0))
                self._sockets.append((sock, destination))
            except OSError:
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="UDPBroadcaster", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Signals broadcaster to terminate and waits for thread exit."""
        self._stop_event.set()
        for sock, _ in self._sockets:
            try:
                sock.close()
            except OSError:
                pass
        self._sockets.clear()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run_loop(self) -> None:
        """Main loop: broadcasts presence immediately on start, then at fixed intervals."""
        while not self._stop_event.is_set():
            try:
                current_status = self.status_provider()
                packet = encode_hello(self.name, self.tcp_port, current_status)
                for sock, target_ip in self._sockets:
                    try:
                        sock.sendto(packet, (target_ip, self.udp_port))
                    except OSError:
                        pass
            except Exception:
                pass

            # Wait for interval or instant wakeup on stop
            if self._stop_event.wait(self.interval):
                break
