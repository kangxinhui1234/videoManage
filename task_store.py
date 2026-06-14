import json
import os
import time
from threading import Lock

STORAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks.json")


class TaskStore:
    """Thread-safe local JSON store for image/video task records."""

    def __init__(self, path=None):
        self._path = path or STORAGE_PATH
        self._lock = Lock()
        if not os.path.exists(self._path):
            self._write([])

    def _read(self):
        with open(self._path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []

    def _write(self, data):
        # atomic write: temp file → rename, avoids corruption on crash
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)

    # ---- CRUD ----

    def add(self, task):
        """Insert a new task record."""
        with self._lock:
            tasks = self._read()
            tasks.insert(0, task)  # newest first
            self._write(tasks)
        return task

    def update(self, task_id, updates):
        """Merge updates into a task by id."""
        with self._lock:
            tasks = self._read()
            for t in tasks:
                if t.get("id") == task_id:
                    t.update(updates)
                    t["updated_at"] = int(time.time())
                    break
            self._write(tasks)

    def get(self, task_id):
        for t in self._read():
            if t.get("id") == task_id:
                return t
        return None

    def list_all(self, task_type=None, limit=50):
        tasks = self._read()
        if task_type:
            tasks = [t for t in tasks if t.get("type") == task_type]
        return tasks[:limit]

    def count_pending_videos(self):
        return sum(
            1 for t in self._read()
            if t.get("type") == "video" and t.get("status") in ("queued", "in_progress")
        )

    # ---- helpers ----

    @staticmethod
    def make_task(task_type, task_id, **extra):
        return {
            "id": task_id,
            "type": task_type,  # "image" | "video"
            "status": "completed" if task_type == "image" else "queued",
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
            **extra,
        }


# singleton
store = TaskStore()
