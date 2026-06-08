"""Internal advisory file locking for the file-backed stores.

Provides a single, fail-closed exclusive lock used to serialize the
read-modify-write sequences in :mod:`agent_sudo.delegations` and the
hash-chained append in :mod:`agent_sudo.audit`.

Design notes:

* POSIX ``fcntl.flock`` only (stdlib, no dependencies). Suitable for the
  macOS/Linux runtimes agent-sudo targets.
* The lock is **advisory** -- all writers in this codebase cooperate by going
  through this helper. It is associated with the open file description, so two
  separate ``open`` calls (even in the same process) contend, which is what we
  rely on for the lock-timeout behaviour.
* **Fail closed:** if the lock cannot be acquired within ``timeout`` seconds we
  raise :class:`LockTimeout`. Callers must treat that as a denial, never as a
  silent fallback.
* **Auto-release:** the kernel releases an ``flock`` when the holding fd is
  closed or the process exits, so a crashed holder cannot wedge the store.
"""

from __future__ import annotations

import errno
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

if sys.platform == "win32":
    import msvcrt
else:
    try:  # pragma: no cover - import guard
        import fcntl
    except ImportError as exc:  # pragma: no cover - non-POSIX platforms
        raise ImportError(
            "agent_sudo file locking requires POSIX fcntl (macOS/Linux) or Windows msvcrt"
        ) from exc


DEFAULT_LOCK_TIMEOUT = 5.0
_POLL_INTERVAL = 0.01

# errno values that mean "lock is currently held, retry": EWOULDBLOCK/EAGAIN come
# from POSIX ``fcntl.flock``; EACCES/EDEADLK are what ``msvcrt.locking`` raises on
# Windows when a non-blocking lock conflicts.
_LOCK_BUSY_ERRNOS = frozenset(
    {errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES, errno.EDEADLK}
)
# Windows surfaces the same condition as a winerror rather than an errno:
# ERROR_SHARING_VIOLATION (32) and ERROR_LOCK_VIOLATION (33).
_WIN_LOCK_BUSY_WINERRORS = frozenset({32, 33})


def _is_lock_busy(exc: OSError) -> bool:
    """True if ``exc`` means the lock is held and we should keep retrying."""
    return (
        exc.errno in _LOCK_BUSY_ERRNOS
        or getattr(exc, "winerror", None) in _WIN_LOCK_BUSY_WINERRORS
    )


class LockTimeout(Exception):
    """Raised when the advisory lock cannot be acquired within the deadline."""


@contextmanager
def file_lock(lock_path: Path, timeout: float = DEFAULT_LOCK_TIMEOUT) -> Iterator[None]:
    """Hold an exclusive advisory lock on ``lock_path`` for the with-block.

    Raises :class:`LockTimeout` if the lock is not acquired within ``timeout``
    seconds. The dedicated ``.lock`` file is created if absent; its contents are
    never read or written -- only the lock state matters.
    """
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            try:
                if sys.platform == "win32":
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if not _is_lock_busy(exc):
                    raise
                if time.monotonic() >= deadline:
                    raise LockTimeout(
                        f"could not acquire lock {lock_path} within {timeout}s"
                    ) from exc
                time.sleep(_POLL_INTERVAL)
        yield
    finally:
        try:
            if sys.platform == "win32":
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def fsync_dir(directory: Path) -> None:
    """Best-effort ``fsync`` of a directory so a rename is durable.

    Directory fsync is not portable to every filesystem; failures are ignored
    because the preceding file fsync already provides the safety we need.
    """
    try:
        dir_fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)
