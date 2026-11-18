import threading


class ProgressDisplay:
    def __init__(self):
        self._transfers = {}
        self._lock = threading.Lock()

    def update(self, progress):
        with self._lock:
            if progress.finished:
                self._transfers.pop(id(progress), None)
            else:
                self._transfers[id(progress)] = progress

    def render(self):
        from prompt_toolkit.application import get_app

        columns = max(1, get_app().output.get_size().columns - 1)
        with self._lock:
            transfers = list(self._transfers.values())
        return '\n'.join(progress.render_bar(columns) for progress in transfers)
