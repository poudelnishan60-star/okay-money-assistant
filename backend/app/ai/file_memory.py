"""What O-Kay read from a visitor's files, remembered for follow-up questions.

Only the text read from a file (already masked: see attachments.py) is kept, never the file,
and only in this server process's memory: nothing is written to disk, a restart forgets it,
and each reading expires an hour after it was read (FILE_MEMORY_MINUTES). Clearing the chat
forgets it at once.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence

from app.ai.attachments import Reading

PER_USER = 3  # the latest files per visitor
MAX_USERS = 500  # bounds the memory used; the visitor whose files are oldest goes first


class FileMemory:
    def __init__(self, minutes: int = 60, clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl = minutes * 60
        self._clock = clock
        self._lock = threading.Lock()
        self._by_user: dict[str, list[tuple[float, Reading]]] = {}

    @property
    def enabled(self) -> bool:
        return self.ttl > 0

    def remember(self, user_id: str, readings: Sequence[Reading]) -> None:
        if not self.enabled or not readings:
            return
        now = self._clock()
        with self._lock:
            new_names = {r.name for r in readings}
            kept = [(t, r) for t, r in self._fresh(user_id, now) if r.name not in new_names]
            kept += [(now + self.ttl, r) for r in readings]
            self._by_user[user_id] = kept[-PER_USER:]
            while len(self._by_user) > MAX_USERS:
                oldest = min(self._by_user, key=lambda u: max(t for t, _ in self._by_user[u]))
                del self._by_user[oldest]

    def recall(self, user_id: str) -> list[Reading]:
        """The visitor's files that haven't expired, oldest first."""
        if not self.enabled:
            return []
        with self._lock:
            return [r for _, r in self._fresh(user_id, self._clock())]

    def forget(self, user_id: str) -> None:
        with self._lock:
            self._by_user.pop(user_id, None)

    def _fresh(self, user_id: str, now: float) -> list[tuple[float, Reading]]:
        items = [(t, r) for t, r in self._by_user.get(user_id, []) if t > now]
        if items:
            self._by_user[user_id] = items
        else:
            self._by_user.pop(user_id, None)
        return items
