"""Request limit per client (SR-19, TH-04).

A client that has made more than RATE_LIMIT_PER_MINUTE requests within one
minute is rejected until the minute has passed. Clients are told apart by IP
address. The counts are kept in memory, so they reset when the server
restarts; this is enough for a single-server prototype.
"""
import threading
from collections import defaultdict, deque
from datetime import timedelta


class RateLimiter:
    def __init__(self, limit_per_minute):
        self.limit = limit_per_minute
        self.window = timedelta(minutes=1)
        self._requests = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client, now):
        with self._lock:
            times = self._requests[client]
            # Forget requests older than one minute.
            while times and now - times[0] >= self.window:
                times.popleft()
            if len(times) >= self.limit:
                return False
            times.append(now)
            return True
