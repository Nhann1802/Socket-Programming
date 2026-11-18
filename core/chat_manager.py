import socket
import threading
from typing import Optional, Tuple, Dict, Any, List


class ChatManager:
    """
    Manages multiple concurrent TCP peer chat sessions.
    Allows user to switch active focus between partners while keeping
    background connections open for unread message delivery.
    """
    def __init__(self):
        self._lock = threading.Lock()
        # Maps lowercase peer_name -> {"sock": sock, "name": str, "ip": str, "port": int, "send_lock": Lock}
        self._sessions: Dict[str, Dict[str, Any]] = {}
        # Lowercase name of the currently active/focused chat partner
        self._active_partner: Optional[str] = None

    def add_session(
        self,
        sock: socket.socket,
        name: str,
        ip: str = "",
        port: int = 0,
        send_lock: Optional[threading.Lock] = None,
        set_active: bool = False,
    ) -> None:
        """Registers a new or updated peer chat session."""
        key = name.strip().lower()
        with self._lock:
            # If already exists, close old socket if different
            if key in self._sessions and self._sessions[key]["sock"] != sock:
                try:
                    self._sessions[key]["sock"].close()
                except OSError:
                    pass

            self._sessions[key] = {
                "sock": sock,
                "name": name.strip(),
                "ip": ip,
                "port": port,
                "send_lock": send_lock or threading.Lock(),
            }

            if self._active_partner is None or set_active:
                self._active_partner = key

    def has_session(self, name: str) -> bool:
        """Checks if there is an established session with a peer."""
        with self._lock:
            return name.strip().lower() in self._sessions

    def get_session(self, name: str) -> Optional[Dict[str, Any]]:
        """Gets session dict for a peer."""
        with self._lock:
            return self._sessions.get(name.strip().lower())

    def get_active_session(self) -> Optional[Dict[str, Any]]:
        """Returns session dict of the currently focused chat partner."""
        with self._lock:
            if not self._active_partner:
                return None
            return self._sessions.get(self._active_partner)

    def get_active_partner(self) -> Optional[str]:
        """Returns display name of the currently focused chat partner."""
        with self._lock:
            if not self._active_partner or self._active_partner not in self._sessions:
                return None
            return self._sessions[self._active_partner]["name"]

    def set_active_partner(self, name: Optional[str]) -> bool:
        """Switches active focus to a peer. Returns True if peer exists or name is None."""
        with self._lock:
            if name is None:
                self._active_partner = None
                return True
            key = name.strip().lower()
            if key in self._sessions:
                self._active_partner = key
                return True
            return False

    def remove_session(self, name: str) -> Optional[Dict[str, Any]]:
        """Removes a session with a peer and returns it."""
        key = name.strip().lower()
        with self._lock:
            session = self._sessions.pop(key, None)
            if self._active_partner == key:
                # If there are other sessions, pick one, or set to None
                self._active_partner = next(iter(self._sessions.keys())) if self._sessions else None
            return session

    def list_connected_peer_names(self) -> List[str]:
        """Returns list of original display names of all connected peers."""
        with self._lock:
            return [s["name"] for s in self._sessions.values()]

    def close_all(self) -> List[socket.socket]:
        """Clears all sessions and returns sockets for final cleanup."""
        with self._lock:
            sockets = [s["sock"] for s in self._sessions.values()]
            self._sessions.clear()
            self._active_partner = None
            return sockets

    # Backward compatibility helpers
    def is_in_chat(self) -> bool:
        with self._lock:
            return self._active_partner is not None

    def get_partner_info(self) -> Tuple[Optional[socket.socket], str, str, int, threading.Lock]:
        sess = self.get_active_session()
        if sess:
            return sess["sock"], sess["name"], sess["ip"], sess["port"], sess["send_lock"]
        return None, "", "", 0, threading.Lock()
