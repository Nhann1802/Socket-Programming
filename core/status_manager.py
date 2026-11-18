import threading
from typing import Optional, Callable


class StatusManager:
    """
    Manages self presence status (online / away).
    """
    VALID_STATUSES = ("online", "away")

    def __init__(self, initial_status: str = "online", on_status_changed: Optional[Callable[[str], None]] = None):
        if initial_status not in self.VALID_STATUSES:
            initial_status = "online"
        self._status = initial_status
        self._lock = threading.Lock()
        self.on_status_changed = on_status_changed

    def get_status(self) -> str:
        """Returns the current status."""
        with self._lock:
            return self._status

    def set_status(self, new_status: str) -> bool:
        """
        Sets a new status. Returns True if valid and changed.
        """
        clean = new_status.strip().lower()
        if clean not in self.VALID_STATUSES:
            return False

        changed = False
        with self._lock:
            if self._status != clean:
                self._status = clean
                changed = True

        if changed and self.on_status_changed:
            self.on_status_changed(clean)

        return True
