"""SQLite repository: each operation owns its connection and transaction."""

import asyncio
import sqlite3
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.models.schemas import TaskRecord, TaskStatus


class QueueFull(ValueError):
    pass


class UploadRateExceeded(ValueError):
    pass


class SQLiteTaskStore:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    async def initialize(self):
        def operation():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.connection() as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute(
                    "CREATE TABLE IF NOT EXISTS tasks "
                    "(id TEXT PRIMARY KEY, status TEXT NOT NULL, created TEXT NOT NULL, data TEXT NOT NULL)"
                )
                db.execute("CREATE INDEX IF NOT EXISTS tasks_status ON tasks(status, created)")
                db.execute("CREATE TABLE IF NOT EXISTS uploads (accepted REAL NOT NULL)")
                db.execute("PRAGMA user_version=1")

        await asyncio.to_thread(operation)

    async def add(self, record: TaskRecord, max_pending: int, per_minute: int):
        def operation():
            with self.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM uploads WHERE accepted < ?", (time.time() - 60,))
                if db.execute("SELECT COUNT(*) FROM uploads").fetchone()[0] >= per_minute:
                    raise UploadRateExceeded
                count = db.execute(
                    "SELECT COUNT(*) FROM tasks WHERE status IN ('pending', 'processing')"
                ).fetchone()[0]
                if count >= max_pending:
                    raise QueueFull
                db.execute("INSERT INTO uploads VALUES (?)", (time.time(),))
                db.execute(
                    "INSERT INTO tasks VALUES (?, ?, ?, ?)",
                    (
                        record.task_id,
                        record.status.value,
                        record.created_at.isoformat(),
                        record.model_dump_json(),
                    ),
                )

        await asyncio.to_thread(operation)

    async def set(self, task_id: str, record: TaskRecord):
        def operation():
            with self.connection() as db:
                db.execute(
                    "INSERT INTO tasks VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                    "status=excluded.status, data=excluded.data",
                    (
                        task_id,
                        record.status.value,
                        record.created_at.isoformat(),
                        record.model_dump_json(),
                    ),
                )

        await asyncio.to_thread(operation)

    async def get(self, task_id: str) -> TaskRecord | None:
        def operation():
            with self.connection() as db:
                row = db.execute("SELECT data FROM tasks WHERE id=?", (task_id,)).fetchone()
                return TaskRecord.model_validate_json(row[0]) if row else None

        return await asyncio.to_thread(operation)

    async def list(self, limit=20, offset=0):
        def operation():
            with self.connection() as db:
                total = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
                rows = db.execute(
                    "SELECT data FROM tasks ORDER BY created DESC, id DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
                return [TaskRecord.model_validate_json(row[0]) for row in rows], total

        return await asyncio.to_thread(operation)

    async def claim(self):
        def operation():
            with self.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT data FROM tasks WHERE status='pending' ORDER BY created, id LIMIT 1"
                ).fetchone()
                if not row:
                    return None
                record = TaskRecord.model_validate_json(row[0])
                record.status = TaskStatus.PROCESSING
                record.updated_at = datetime.now(UTC)
                db.execute(
                    "UPDATE tasks SET status=?, data=? WHERE id=?",
                    (record.status.value, record.model_dump_json(), record.task_id),
                )
                return record

        return await asyncio.to_thread(operation)

    async def recover(self):
        def operation():
            with self.connection() as db:
                rows = db.execute("SELECT data FROM tasks WHERE status='processing'").fetchall()
                for row in rows:
                    record = TaskRecord.model_validate_json(row[0])
                    record.status = TaskStatus.PENDING
                    record.updated_at = datetime.now(UTC)
                    db.execute(
                        "UPDATE tasks SET status=?, data=? WHERE id=?",
                        (record.status.value, record.model_dump_json(), record.task_id),
                    )

        await asyncio.to_thread(operation)

    async def delete(self, task_id: str):
        def operation():
            with self.connection() as db:
                db.execute(
                    "DELETE FROM tasks WHERE id=? AND status IN ('completed', 'failed')", (task_id,)
                )

        await asyncio.to_thread(operation)
