from __future__ import annotations

import time
from contextlib import contextmanager


@contextmanager
def elapsed_ms():
    started_at = time.perf_counter()
    yield lambda: (time.perf_counter() - started_at) * 1000
