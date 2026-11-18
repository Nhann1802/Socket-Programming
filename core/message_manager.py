import threading
from typing import Dict, List, Optional, Any
from .message import Message


class MessageManager:
    """
    Thread-safe message history repository with unread message tracking.
    Supports isolating sessions by (ip, port) tuple, port int, or display name.
    """
    def __init__(self, max_history_per_peer: int = 100):
        self._history: Dict[Any, List[Message]] = {}
        self._unread_counts: Dict[Any, int] = {}
        self._lock = threading.Lock()
        self.max_history_per_peer = max_history_per_peer

    @staticmethod
    def _normalize_key(target: Any) -> Any:
        if target is None:
            return None
        if isinstance(target, tuple):
            return (str(target[0]).strip(), int(target[1]))
        if isinstance(target, int):
            return target
        if isinstance(target, str):
            t_str = target.strip()
            if ":" in t_str:
                parts = t_str.split(":", 1)
                try:
                    return (parts[0].strip(), int(parts[1].strip()))
                except ValueError:
                    pass
            return t_str.lower()
        return target

    def add_message(
        self,
        message: Message,
        is_active_session: bool = False,
        conversation_partner: Any = None,
    ) -> None:
        """
        Stores an incoming or outgoing message.
        If conversation_partner is provided, stores under that partner's key:
        tuple (ip, port), int (port), or str (name).
        Otherwise defaults to message.receiver (if outgoing) or message.sender.
        """
        if conversation_partner is not None:
            peer_key = self._normalize_key(conversation_partner)
        else:
            peer_key = message.sender.lower()

        with self._lock:
            if peer_key not in self._history:
                self._history[peer_key] = []
            self._history[peer_key].append(message)

            if len(self._history[peer_key]) > self.max_history_per_peer:
                self._history[peer_key].pop(0)

            # Increment unread count for incoming messages when not in active session
            if not is_active_session:
                self._unread_counts[peer_key] = self._unread_counts.get(peer_key, 0) + 1

    def get_history(self, target: Any) -> List[Message]:
        """Returns message history for a given partner (tuple (ip, port), port int, or name str)."""
        key = self._normalize_key(target)
        with self._lock:
            # 1. Exact match
            if key in self._history:
                return list(self._history[key])

            # 2. If target is a port or tuple with port, search matching port
            port = None
            if isinstance(key, tuple):
                port = key[1]
            elif isinstance(key, int):
                port = key

            if port:
                for k, msgs in self._history.items():
                    if isinstance(k, tuple) and k[1] == port:
                        return list(msgs)
                    if k == port:
                        return list(msgs)

            # 3. If target is a string name, search matching name
            if isinstance(key, str):
                for k, msgs in self._history.items():
                    if isinstance(k, str) and k == key:
                        return list(msgs)

            return []

    def get_unread_count(self, target: Any = None) -> int:
        """
        Returns number of unread messages from a partner.
        If target is None, returns total unread count across all peers.
        """
        with self._lock:
            if target is None:
                return sum(self._unread_counts.values())
            key = self._normalize_key(target)
            if key in self._unread_counts:
                return self._unread_counts[key]
            port = key[1] if isinstance(key, tuple) else (key if isinstance(key, int) else None)
            if port:
                for k, count in self._unread_counts.items():
                    if (isinstance(k, tuple) and k[1] == port) or k == port:
                        return count
            if isinstance(key, str):
                for k, count in self._unread_counts.items():
                    if isinstance(k, str) and k == key:
                        return count
            return 0

    def mark_as_read(self, target: Any) -> None:
        """Resets unread count for a partner."""
        key = self._normalize_key(target)
        with self._lock:
            if key in self._unread_counts:
                self._unread_counts[key] = 0
            port = key[1] if isinstance(key, tuple) else (key if isinstance(key, int) else None)
            if port:
                for k in list(self._unread_counts.keys()):
                    if (isinstance(k, tuple) and k[1] == port) or k == port:
                        self._unread_counts[k] = 0
            if isinstance(key, str):
                for k in list(self._unread_counts.keys()):
                    if isinstance(k, str) and k == key:
                        self._unread_counts[k] = 0

    def get_all_unread(self) -> Dict[Any, int]:
        """Returns map of all partners with unread message counts > 0."""
        with self._lock:
            return {k: v for k, v in self._unread_counts.items() if v > 0}
