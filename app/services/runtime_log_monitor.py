from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional


class InMemoryLogMonitor:
    def __init__(self, max_entries: int = 1000) -> None:
        self.max_entries = max(100, int(max_entries))
        self._entries: Deque[Dict[str, Any]] = deque(maxlen=self.max_entries)
        self._lock = threading.Lock()
        self._next_id = 1

    def add(self, level: str, logger_name: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            entry = {
                "id": self._next_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": (level or "INFO").upper(),
                "logger": logger_name,
                "message": message,
                "extra": extra or {},
            }
            self._next_id += 1
            self._entries.append(entry)

    def query(
        self,
        limit: int = 200,
        since_id: Optional[int] = None,
        level: Optional[str] = None,
        contains: Optional[str] = None,
        logger: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        max_limit = 1000
        target_limit = min(max(1, int(limit)), max_limit)
        level_filter = (level or "").upper().strip()
        contains_filter = (contains or "").lower().strip()
        logger_filter = (logger or "").lower().strip()

        with self._lock:
            items = list(self._entries)

        filtered: List[Dict[str, Any]] = []
        for item in items:
            if since_id is not None and int(item.get("id", 0)) <= int(since_id):
                continue
            if level_filter and str(item.get("level", "")).upper() != level_filter:
                continue
            if contains_filter and contains_filter not in str(item.get("message", "")).lower():
                continue
            if logger_filter and logger_filter not in str(item.get("logger", "")).lower():
                continue
            filtered.append(item)

        if len(filtered) > target_limit:
            filtered = filtered[-target_limit:]
        return filtered

    def clear(self) -> int:
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
        return count


class InMemoryLogHandler(logging.Handler):
    def __init__(self, monitor: InMemoryLogMonitor) -> None:
        super().__init__()
        self.monitor = monitor

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            extra = {
                "module": record.module,
                "func": record.funcName,
                "line": record.lineno,
            }
            self.monitor.add(record.levelname, record.name, message, extra=extra)
        except Exception:
            # Never allow logging failures to break API processing.
            return


def setup_log_monitor(max_entries: int = 1000, level: int = logging.INFO) -> InMemoryLogMonitor:
    monitor = InMemoryLogMonitor(max_entries=max_entries)
    root = logging.getLogger()
    root.setLevel(level)

    existing = any(isinstance(handler, InMemoryLogHandler) for handler in root.handlers)
    if not existing:
        handler = InMemoryLogHandler(monitor)
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)
    return monitor
