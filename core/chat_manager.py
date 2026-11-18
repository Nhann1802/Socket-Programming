import socket
import threading
from typing import Optional, Tuple, Dict, Any, List


class ChatManager:
    """
    Manages multiple concurrent TCP peer chat sessions.
    Sessions are uniquely keyed by (ip, port) to prevent collision when
    multiple peers share the same display name.
    """
    def __init__(self):
        self._lock = threading.Lock()
        # Maps (ip, port) -> {"sock": sock, "name": str, "ip": str, "port": int, "send_lock": Lock}
        self._sessions: Dict[Tuple[str, int], Dict[str, Any]] = {}
        # Unique (ip, port) key of the currently active/focused chat partner
        self._active_key: Optional[Tuple[str, int]] = None

    def add_session(
        self,
        sock: socket.socket,
        name: str,
        ip: str = "",
        port: int = 0,
        send_lock: Optional[threading.Lock] = None,
        set_active: bool = False,
    ) -> Tuple[str, int]:
        """Registers a new or updated peer chat session uniquely identified by (ip, port)."""
        clean_ip = ip.strip() if ip.strip() else "127.0.0.1"
        key = (clean_ip, int(port)) if port > 0 else (name.strip().lower(), 0)

        with self._lock:
            # If a session with this exact (ip, port) already exists with a different socket, close old one
            if key in self._sessions and self._sessions[key]["sock"] != sock:
                try:
                    self._sessions[key]["sock"].close()
                except OSError:
                    pass

            self._sessions[key] = {
                "sock": sock,
                "name": name.strip(),
                "ip": clean_ip,
                "port": int(port),
                "send_lock": send_lock or threading.Lock(),
            }

            if self._active_key is None or set_active:
                self._active_key = key

            return key

    def has_session(self, identifier: Any) -> bool:
        """
        Checks if there is an established session.
        identifier can be (ip, port) tuple, port (int), or peer name (str).
        """
        with self._lock:
            if isinstance(identifier, tuple) and identifier in self._sessions:
                return True
            if isinstance(identifier, int):
                return any(s["port"] == identifier for s in self._sessions.values())
            if isinstance(identifier, str):
                target = identifier.strip().lower()
                if ":" in target:
                    parts = target.split(":", 1)
                    try:
                        p_key = (parts[0].strip(), int(parts[1].strip()))
                        if p_key in self._sessions:
                            return True
                    except ValueError:
                        pass
                return any(s["name"].lower() == target for s in self._sessions.values())
            return False

    def get_session(self, identifier: Any) -> Optional[Dict[str, Any]]:
        """Gets session dict by (ip, port), port (int), or peer name (str)."""
        with self._lock:
            if isinstance(identifier, tuple) and identifier in self._sessions:
                return self._sessions[identifier]
            if isinstance(identifier, int):
                for s in self._sessions.values():
                    if s["port"] == identifier:
                        return s
                return None
            if isinstance(identifier, str):
                target = identifier.strip().lower()
                if ":" in target:
                    parts = target.split(":", 1)
                    try:
                        p_key = (parts[0].strip(), int(parts[1].strip()))
                        if p_key in self._sessions:
                            return self._sessions[p_key]
                    except ValueError:
                        pass
                for s in self._sessions.values():
                    if s["name"].lower() == target:
                        return s
                if target.isdigit():
                    p_num = int(target)
                    for s in self._sessions.values():
                        if s["port"] == p_num:
                            return s
            return None

    def get_active_session(self) -> Optional[Dict[str, Any]]:
        """Returns session dict of the currently focused chat partner."""
        with self._lock:
            if not self._active_key or self._active_key not in self._sessions:
                return None
            return self._sessions[self._active_key]

    def get_active_partner(self) -> Optional[str]:
        """Returns display name of the currently focused chat partner."""
        with self._lock:
            if not self._active_key or self._active_key not in self._sessions:
                return None
            return self._sessions[self._active_key]["name"]

    def get_active_port(self) -> int:
        """Returns port of the currently focused chat partner, or 0."""
        with self._lock:
            if not self._active_key or self._active_key not in self._sessions:
                return 0
            return self._sessions[self._active_key].get("port", 0)

    def set_active_partner(self, target: Any) -> bool:
        """
        Switches active focus.
        target can be None (leave room), (ip, port), port (int), or peer name (str).
        """
        with self._lock:
            if target is None:
                self._active_key = None
                return True
            if isinstance(target, tuple) and target in self._sessions:
                self._active_key = target
                return True
            if isinstance(target, int):
                for k, s in self._sessions.items():
                    if s["port"] == target:
                        self._active_key = k
                        return True
                return False
            if isinstance(target, str):
                t_str = target.strip()
                if not t_str:
                    self._active_key = None
                    return True
                if ":" in t_str:
                    parts = t_str.split(":", 1)
                    try:
                        p_key = (parts[0].strip(), int(parts[1].strip()))
                        if p_key in self._sessions:
                            self._active_key = p_key
                            return True
                    except ValueError:
                        pass
                t_lower = t_str.lower()
                for k, s in self._sessions.items():
                    if s["name"].lower() == t_lower:
                        self._active_key = k
                        return True
                if t_str.isdigit():
                    p_num = int(t_str)
                    for k, s in self._sessions.items():
                        if s["port"] == p_num:
                            self._active_key = k
                            return True
            return False

    def remove_session(
        self,
        target: Any = None,
        sock: Optional[socket.socket] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Removes a session by socket object, (ip, port), port (int), or peer name (str).
        If the active session is closed, active focus is reset to None (DOES NOT JUMP TO RANDOM PEER).
        """
        with self._lock:
            key_to_remove = None

            # 1. Match by exact socket instance if provided (most reliable!)
            if sock is not None:
                for k, s in self._sessions.items():
                    if s["sock"] == sock:
                        key_to_remove = k
                        break

            # 2. Match by tuple (ip, port)
            elif isinstance(target, tuple):
                if target in self._sessions:
                    key_to_remove = target

            # 3. Match by port int
            elif isinstance(target, int):
                for k, s in self._sessions.items():
                    if s["port"] == target:
                        key_to_remove = k
                        break

            # 4. Match by string (ip:port, name, or port number)
            elif isinstance(target, str):
                t_str = target.strip()
                if ":" in t_str:
                    parts = t_str.split(":", 1)
                    try:
                        p_key = (parts[0].strip(), int(parts[1].strip()))
                        if p_key in self._sessions:
                            key_to_remove = p_key
                    except ValueError:
                        pass
                if not key_to_remove:
                    t_lower = t_str.lower()
                    for k, s in self._sessions.items():
                        if s["name"].lower() == t_lower:
                            key_to_remove = k
                            break

            if key_to_remove:
                removed_session = self._sessions.pop(key_to_remove, None)
                if self._active_key == key_to_remove:
                    # Reset to None to prevent accidental message leakage to other peers!
                    self._active_key = None
                return removed_session

            return None

    def session_count(self) -> int:
        """Returns total number of open background sessions."""
        with self._lock:
            return len(self._sessions)

    def list_all_sessions(self) -> List[Dict[str, Any]]:
        """Returns shallow copy list of all active session dicts."""
        with self._lock:
            return [dict(s) for s in self._sessions.values()]

    def list_connected_peer_names(self) -> List[str]:
        """Returns list of display names of all connected peers."""
        with self._lock:
            return [s["name"] for s in self._sessions.values()]

    def list_connected_ports(self) -> List[int]:
        """Returns list of TCP ports of all connected peers."""
        with self._lock:
            return [s["port"] for s in self._sessions.values() if s.get("port", 0) > 0]

    def close_all(self) -> List[socket.socket]:
        """Clears all sessions and returns sockets for final cleanup."""
        with self._lock:
            sockets = [s["sock"] for s in self._sessions.values()]
            self._sessions.clear()
            self._active_key = None
            return sockets

    # Backward compatibility helpers
    def is_in_chat(self) -> bool:
        with self._lock:
            return self._active_key is not None

    def get_partner_info(self) -> Tuple[Optional[socket.socket], str, str, int, threading.Lock]:
        sess = self.get_active_session()
        if sess:
            return sess["sock"], sess["name"], sess["ip"], sess["port"], sess["send_lock"]
        return None, "", "", 0, threading.Lock()
