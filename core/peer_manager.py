import threading
import time
from typing import Optional, List, Dict, Tuple, Callable
from .peer import Peer


class PeerManager:
    """
    Thread-safe repository and lifecycle tracker for active LAN peers.
    """
    def __init__(
        self,
        on_peer_added: Optional[Callable[[Peer], None]] = None,
        on_peer_removed: Optional[Callable[[Peer], None]] = None,
    ):
        self._peers: Dict[Tuple[str, int], Peer] = {}
        self._lock = threading.Lock()
        self.on_peer_added = on_peer_added
        self.on_peer_removed = on_peer_removed

    def add_or_update(self, name: str, ip: str, tcp_port: int, status: str = "online") -> Tuple[Peer, bool]:
        """
        Registers a new peer or updates an existing peer's presence.
        Returns: (peer, is_new: bool)
        """
        key = (ip, tcp_port)
        is_new = False
        with self._lock:
            if key not in self._peers:
                peer = Peer(name=name, ip=ip, tcp_port=tcp_port, status=status)
                self._peers[key] = peer
                is_new = True
            else:
                peer = self._peers[key]
                peer.name = name
                peer.update_presence(status)

        if is_new and self.on_peer_added:
            self.on_peer_added(peer)

        return peer, is_new

    def remove(self, ip: str, tcp_port: int) -> Optional[Peer]:
        """Removes a peer explicitly."""
        key = (ip, tcp_port)
        peer = None
        with self._lock:
            if key in self._peers:
                peer = self._peers.pop(key)

        if peer and self.on_peer_removed:
            self.on_peer_removed(peer)

        return peer

    def get_peer(self, ip: str, tcp_port: int) -> Optional[Peer]:
        """Retrieves a peer by (ip, tcp_port)."""
        with self._lock:
            return self._peers.get((ip, tcp_port))

    def find_by_name(self, name: str) -> Optional[Peer]:
        """Finds the first peer matching the given name (case-insensitive)."""
        target = name.strip().lower()
        with self._lock:
            for peer in self._peers.values():
                if peer.name.lower() == target:
                    return peer
        return None

    def find_by_port(self, port: int) -> Optional[Peer]:
        """Finds peer matching a TCP port."""
        with self._lock:
            for peer in self._peers.values():
                if peer.tcp_port == port:
                    return peer
        return None

    def list_peers(self) -> List[Peer]:
        """Returns a snapshot list of all currently tracked peers, sorted by name."""
        with self._lock:
            return sorted(self._peers.values(), key=lambda p: p.name.lower())

    def count(self) -> int:
        """Returns total number of tracked peers."""
        with self._lock:
            return len(self._peers)

    def cleanup_expired(self, timeout_sec: float = 10.0) -> List[Peer]:
        """
        Scans and removes all peers that have timed out without heartbeats.
        Returns the list of removed peers.
        """
        expired: List[Peer] = []
        with self._lock:
            keys_to_remove = []
            for key, peer in self._peers.items():
                if peer.is_expired(timeout_sec):
                    keys_to_remove.append(key)
                    expired.append(peer)

            for key in keys_to_remove:
                self._peers.pop(key, None)

        if self.on_peer_removed:
            for p in expired:
                self.on_peer_removed(p)

        return expired
