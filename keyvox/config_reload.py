"""Lightweight file-based config reloader."""
from pathlib import Path
from typing import Callable, Optional, TypeVar
import time


T = TypeVar("T")


class FileReloader:
    """Poll a file and load content only when it changes."""

    def __init__(
        self,
        path_getter: Callable[[], Optional[Path]],
        loader: Callable[[Path], T],
        min_interval_s: float = 0.5,
    ):
        self.path_getter = path_getter
        self.loader = loader
        self.min_interval_s = min_interval_s
        self._last_check_ts = 0.0
        self._last_path: Optional[Path] = None
        self._last_mtime_ns: Optional[int] = None

    def prime(self) -> None:
        """Capture current file state without loading."""
        path = self.path_getter()
        if not path:
            self._last_path = None
            self._last_mtime_ns = None
            return

        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            self._last_path = None
            self._last_mtime_ns = None
            return

        self._last_path = path
        self._last_mtime_ns = mtime_ns

    def poll(self) -> Optional[T]:
        """Return loaded value when changed, else None."""
        now = time.monotonic()
        if now - self._last_check_ts < self.min_interval_s:
            return None
        self._last_check_ts = now

        path = self.path_getter()
        if not path:
            return None

        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            return None

        if path == self._last_path and mtime_ns == self._last_mtime_ns:
            return None

        self._last_path = path
        self._last_mtime_ns = mtime_ns
        return self.loader(path)
