"""Sliding-window rate limiter (in memory, one process).

Protects the free Groq quota on the public site. For several backend instances, swap this for
a shared store (e.g. Redis) behind the same `check` signature.
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Limit:
    count: int
    seconds: int


@dataclass(frozen=True, slots=True)
class Verdict:
    allowed: bool
    retry_after_seconds: int = 0


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limits: Sequence[Limit]) -> Verdict:
        """Record a hit for `key` if every limit allows it; otherwise say how long to wait."""
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            longest = max((lim.seconds for lim in limits), default=0)
            while hits and hits[0] <= now - longest:
                hits.popleft()
            wait = 0.0
            for lim in limits:
                if lim.count <= 0:
                    continue
                recent = [t for t in hits if t > now - lim.seconds]
                if len(recent) >= lim.count:
                    wait = max(wait, recent[-lim.count] + lim.seconds - now)
            if wait > 0:
                return Verdict(False, max(1, math.ceil(wait)))
            hits.append(now)
            return Verdict(True)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
