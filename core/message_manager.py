import threading
from typing import Dict, List, Optional
from .message import Message


class MessageManager:
    """
    Thread-safe message history repository with unread message tracking.
    """
    def __init__(self, max_history_per_peer: int = 100):
        self._history: Dict[str, List[Message]] = {}
        self._unread_counts: Dict[str, int] = {}
        self._lock = threading.Lock()
        self.max_history_per_peer = max_history_per_peer

    def add_message(
        self,
        message: Message,
        is_active_session: bool = False,
        conversation_partner: Optional[str] = None,
    ) -> None:
        """
        Stores an incoming or outgoing message.
        If conversation_partner is provided, stores under that partner's history.
        Otherwise defaults to message.receiver (if outgoing) or message.sender.
        """
        if conversation_partner:
            peer_key = conversation_partner.lower()
        else:
            peer_key = message.sender.lower()

        with self._lock:
            if peer_key not in self._history:
                self._history[peer_key] = []
            self._history[peer_key].append(message)

            if len(self._history[peer_key]) > self.max_history_per_peer:
                self._history[peer_key].pop(0)

            # Only increment unread count for incoming messages not currently active
            if not is_active_session and message.sender.lower() == peer_key:
                self._unread_counts[peer_key] = self._unread_counts.get(peer_key, 0) + 1

    def get_history(self, peer_name: str) -> List[Message]:
        """Returns message history for a given peer name."""
        peer_key = peer_name.lower()
        with self._lock:
            return list(self._history.get(peer_key, []))

    def get_unread_count(self, peer_name: str) -> int:
        """Returns number of unread messages from a peer."""
        peer_key = peer_name.lower()
        with self._lock:
            return self._unread_counts.get(peer_key, 0)

    def mark_as_read(self, peer_name: str) -> None:
        """Resets unread count for a peer."""
        peer_key = peer_name.lower()
        with self._lock:
            self._unread_counts[peer_key] = 0

    def get_all_unread(self) -> Dict[str, int]:
        """Returns map of all peers with unread message counts > 0."""
        with self._lock:
            return {k: v for k, v in self._unread_counts.items() if v > 0}
