#!/usr/bin/env python3
import fnmatch
import logging
import signal
import threading
from pathlib import Path
from typing import Any, List, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from src.mimir.indexing import (
    EXCLUDE_PATTERNS,
    detect_changed_files,
    incremental_reindex,
    save_hash_state,
    load_hash_state,
)
from src.mimir.knowledge_graph import incremental_graph_update

import sys
from datetime import datetime

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 2.0

KG_DEBOUNCE_SECONDS = 5.0

WATCHER_EXCLUDE_DIRS = {
    ".knowledge",
    "node_modules",
    "__pycache__",
    ".git",
    ".github",
    ".venv",
    "venv",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".sisyphus",
    ".opencode",
}


def _path_is_excluded(path_str: "str | bytes") -> bool:
    s = path_str.decode() if isinstance(path_str, bytes) else path_str
    for part in Path(s).parts:
        if part in WATCHER_EXCLUDE_DIRS:
            return True
    for pattern in EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(Path(s).name, pattern):
            return True
        if pattern in s:
            return True
    return False


class _DebounceHandler(FileSystemEventHandler):
    def __init__(self, watcher: "MimirFileWatcher"):
        super().__init__()
        self._watcher = watcher
        self._timer: Optional[threading.Timer] = None
        self._kg_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._changed_files: dict = {}

    def _schedule_reindex(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(
                DEBOUNCE_SECONDS, self._watcher._trigger_reindex
            )
            self._timer.daemon = True
            self._timer.start()

    def _schedule_kg_update(self) -> None:
        with self._lock:
            if self._kg_timer is not None:
                self._kg_timer.cancel()
            self._kg_timer = threading.Timer(
                KG_DEBOUNCE_SECONDS, self._watcher._trigger_kg_update
            )
            self._kg_timer.daemon = True
            self._kg_timer.start()

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        if _path_is_excluded(event.src_path):
            logger.debug(f"Ignored (excluded): {event.src_path}")
            return
        logger.debug(f"Created: {event.src_path}")
        self._schedule_reindex()
        self._schedule_kg_update()

    def on_modified(self, event) -> None:
        if event.is_directory:
            return
        if _path_is_excluded(event.src_path):
            logger.debug(f"Ignored (excluded): {event.src_path}")
            return
        logger.debug(f"Modified: {event.src_path}")
        self._schedule_reindex()
        self._schedule_kg_update()

    def on_deleted(self, event) -> None:
        if event.is_directory:
            return
        if _path_is_excluded(event.src_path):
            logger.debug(f"Ignored (excluded): {event.src_path}")
            return
        logger.debug(f"Deleted: {event.src_path}")
        self._schedule_reindex()
        self._schedule_kg_update()

    def on_moved(self, event) -> None:
        if event.is_directory:
            return
        src_excluded = _path_is_excluded(event.src_path)
        dst_excluded = _path_is_excluded(event.dest_path)
        if src_excluded and dst_excluded:
            logger.debug(f"Ignored (excluded): {event.src_path} -> {event.dest_path}")
            return
        logger.debug(f"Moved: {event.src_path} -> {event.dest_path}")
        self._schedule_reindex()
        self._schedule_kg_update()

    def cancel(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if self._kg_timer is not None:
                self._kg_timer.cancel()
                self._kg_timer = None


class MimirFileWatcher:
    def __init__(
        self,
        project_root: Path,
        watched_dirs: List[Path],
        knowledge_dir: Path,
        index_lock: Optional[threading.RLock] = None,
    ):
        self._project_root = project_root
        self._watched_dirs = watched_dirs
        self._knowledge_dir = knowledge_dir
        self._index_lock = index_lock or threading.RLock()
        self._observer: Optional[Any] = None
        self._handler: Optional[_DebounceHandler] = None
        self._running = False
        self._reindex_count = 0
        self._last_reindex_result: Optional[dict] = None
        self._last_graph_update: Optional[str] = None

    def start(self) -> None:
        if self._running:
            logger.warning("Watcher already running")
            return

        self._handler = _DebounceHandler(self)
        observer = Observer()
        self._observer = observer

        for watched_dir in self._watched_dirs:
            if watched_dir.exists():
                observer.schedule(self._handler, str(watched_dir), recursive=True)
                logger.info(f"Watching: {watched_dir}")
            else:
                logger.warning(f"Watch dir does not exist, skipping: {watched_dir}")

        observer.start()
        self._running = True
        logger.info("MimirFileWatcher started")

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def stop(self) -> None:
        if not self._running:
            return

        self._running = False

        if self._handler is not None:
            self._handler.cancel()

        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None

        logger.info("MimirFileWatcher stopped")

    def status(self) -> dict:
        return {
            "running": self._running,
            "watched_dirs": [str(d) for d in self._watched_dirs],
            "project_root": str(self._project_root),
            "knowledge_dir": str(self._knowledge_dir),
            "reindex_count": self._reindex_count,
            "last_reindex_result": self._last_reindex_result,
            "last_index_update": self._last_reindex_result.get("timestamp")
            if self._last_reindex_result
            else None,
            "last_graph_update": self._last_graph_update,
        }

    def _trigger_reindex(self) -> None:
        logger.info("Debounce elapsed — triggering incremental reindex")
        try:
            with self._index_lock:
                result = incremental_reindex(
                    project_root=self._project_root,
                    watched_dirs=self._watched_dirs,
                    knowledge_dir=self._knowledge_dir,
                    verbose=False,
                )
                self._reindex_count += 1
                self._last_reindex_result = result

                if result["success"]:
                    state = load_hash_state(self._project_root)
                    save_hash_state(self._project_root, state)
                    logger.info(
                        f"Reindex #{self._reindex_count} complete: "
                        f"+{result['added_count']} ~{result['modified_count']} "
                        f"-{result['deleted_count']}"
                    )
                else:
                    logger.warning(f"Reindex #{self._reindex_count} failed")
        except Exception as e:
            logger.error(f"Watcher reindex error (non-fatal): {e}")

    def _trigger_kg_update(self) -> None:
        logger.info("Debounce elapsed — triggering KG update")
        try:
            changed = detect_changed_files(self._project_root, self._watched_dirs)
            changed_str = {k: [str(p) for p in v] for k, v in changed.items()}
            if sum(len(lst) for lst in changed_str.values()) == 0:
                logger.debug("No file changes for KG update")
                return

            added, removed, mod_rel = incremental_graph_update(
                self._project_root, changed_str
            )

            # Invalidate web UI graph cache
            project_root_str = str(self._project_root)
            if project_root_str not in sys.path:
                sys.path.insert(0, project_root_str)
            import web.server

            web.server._graph_cache.clear()
            logger.info("Graph cache invalidated")

            self._last_graph_update = datetime.now().isoformat()

            logger.info(
                f"Knowledge graph updated: +{added} entities, -{removed} entities, ~{mod_rel} relationships changed"
            )
        except Exception as e:
            logger.error(f"Watcher KG update error (non-fatal): {e}")

    def _handle_signal(self, signum, frame) -> None:
        logger.info(f"Received signal {signum}, shutting down watcher")
        self.stop()
