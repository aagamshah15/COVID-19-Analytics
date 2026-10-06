"""In-memory request limits. The service runs as a single instance, so memory is enough.

Guards that keep usage inside Cloud Run's free tier even if someone hammers the endpoint: a cap on
the size of a request, a limit per address per minute, a limit across all callers per day (which
bounds the data sent back), a budget of compute seconds per day (which bounds the instance time
billed), and, in ``main.py``, one heavy analysis at a time.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager

from starlette.exceptions import HTTPException

DAY = 86400.0


class Limit:
    """At most ``per_minute`` calls a minute from one address and ``per_day`` a day from everyone."""

    def __init__(self, per_minute: int, per_day: int, clock=time.monotonic):
        self.per_minute = per_minute
        self.per_day = per_day
        self._clock = clock
        self._lock = threading.Lock()
        self._recent: dict[str, deque[float]] = defaultdict(deque)
        self._day_start = clock()
        self._day_count = 0

    def check(self, address: str) -> float | None:
        """Record a call. Returns None if allowed, else the seconds to wait before retrying."""
        now = self._clock()
        with self._lock:
            if now - self._day_start >= DAY:
                self._day_start, self._day_count = now, 0
            if self._day_count >= self.per_day:
                return self._day_start + DAY - now
            calls = self._recent[address]
            while calls and now - calls[0] >= 60:
                calls.popleft()
            if len(calls) >= self.per_minute:
                return calls[0] + 60 - now if calls else 60.0  # a limit of zero closes the endpoint
            calls.append(now)
            self._day_count += 1
            if len(self._recent) > 5000:  # forget idle addresses
                for key in [k for k, v in self._recent.items() if not v or now - v[-1] >= 60]:
                    del self._recent[key]
            return None


class Budget:
    """At most ``seconds_per_day`` of compute a day, across all callers.

    Cloud Run bills by the second an instance spends serving requests, so this bounds the bill
    directly, however slow the machine turns out to be.
    """

    def __init__(self, seconds_per_day: float, clock=time.monotonic):
        self.seconds_per_day = seconds_per_day
        self._clock = clock
        self._lock = threading.Lock()
        self._day_start = clock()
        self._spent = 0.0

    def wait(self) -> float | None:
        """None while there is budget left, else the seconds until the next day starts."""
        now = self._clock()
        with self._lock:
            if now - self._day_start >= DAY:
                self._day_start, self._spent = now, 0.0
            return None if self._spent < self.seconds_per_day else self._day_start + DAY - now

    @contextmanager
    def spend(self):
        """Charge the time spent inside the block to today's budget."""
        started = self._clock()
        try:
            yield
        finally:
            elapsed = self._clock() - started
            with self._lock:
                self._spent += elapsed


class BodyLimit:
    """ASGI middleware: stop reading a request body once it passes ``limit`` bytes.

    Counts the bytes as they arrive, so a caller can't get around it by leaving out Content-Length.
    """

    def __init__(self, app, limit: int):
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        received = 0

        async def limited():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit:
                    raise HTTPException(413, "Request body too large.")
            return message

        await self.app(scope, limited, send)
