"""Serialize release mutations for threads and workers sharing storage."""

import fcntl
from contextlib import contextmanager


@contextmanager
def release_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
