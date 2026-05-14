"""
In-memory log buffer for scrape runs.
Stores the last N log lines per run_id, thread-safe via a Lock.
"""
import threading
from collections import deque
from datetime import datetime
from typing import Dict, List, Deque

_MAX_LINES = 200
_lock = threading.Lock()
_buffers: Dict[int, Deque[dict]] = {}


def init_run(run_id: int) -> None:
    with _lock:
        _buffers[run_id] = deque(maxlen=_MAX_LINES)


def append(run_id: int, level: str, message: str) -> None:
    with _lock:
        buf = _buffers.get(run_id)
        if buf is not None:
            buf.append({"ts": datetime.utcnow().isoformat(), "level": level, "msg": message})


def get(run_id: int) -> List[dict]:
    with _lock:
        buf = _buffers.get(run_id)
        return list(buf) if buf else []


def clear_old(keep_last: int = 5) -> None:
    """Prune buffers for all but the most recent `keep_last` runs."""
    with _lock:
        if len(_buffers) > keep_last:
            keys = sorted(_buffers.keys())
            for k in keys[:-keep_last]:
                del _buffers[k]
