"""
ratelimit.py — sliding-window limiter (in-memory, fail-closed ต่อ key)
กัน brute-force access token / สแปม endpoint ที่เรียก Meta/AI หรือใช้เงิน
"""
import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def allow(key: str, limit: int, window_s: int) -> tuple[bool, int]:
    """คืน (allowed?, retry_after_s)"""
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            retry = int(window_s - (now - q[0])) + 1
            return False, max(retry, 1)
        q.append(now)
        return True, 0


def reset():
    with _lock:
        _hits.clear()
