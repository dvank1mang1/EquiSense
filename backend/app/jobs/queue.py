from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any

import psycopg2
from loguru import logger

from app.core.config import settings


@dataclass
class JobQueueItem:
    run_id: str
    payload: dict[str, Any]
    worker_id: str | None = None


class PostgresJobQueue:
    def __init__(self) -> None:
        self._dsn = settings.database_url_sync
        self._schema_ready = False

    def _connect(self):
        return psycopg2.connect(self._dsn)

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS job_queue (
                        run_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        max_attempts INTEGER NOT NULL DEFAULT 3,
                        worker_id TEXT NULL,
                        error TEXT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute("ALTER TABLE job_queue ADD COLUMN IF NOT EXISTS worker_id TEXT NULL")
                cur.execute(
                    "ALTER TABLE job_queue ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0"
                )
                cur.execute(
                    "ALTER TABLE job_queue ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 3"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_job_queue_status_created ON job_queue(status, created_at)"
                )
            conn.commit()
        self._schema_ready = True

    def enqueue(self, run_id: str, payload: dict[str, Any]) -> None:
        self._ensure_schema()
        max_attempts = int(payload.get("max_attempts", settings.job_queue_max_attempts))
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO job_queue(run_id, status, payload_json, attempt_count, max_attempts, updated_at)
                    VALUES (%s, 'queued', %s, 0, %s, NOW())
                    ON CONFLICT (run_id) DO UPDATE
                    SET status = 'queued',
                        payload_json = EXCLUDED.payload_json,
                        max_attempts = EXCLUDED.max_attempts,
                        error = NULL,
                        updated_at = NOW()
                    """,
                    (run_id, json.dumps(payload, ensure_ascii=False), max(1, max_attempts)),
                )
            conn.commit()

    def status(self, run_id: str) -> str | None:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM job_queue WHERE run_id = %s", (run_id,))
                row = cur.fetchone()
        if row is None:
            return None
        return str(row[0])

    def claim_next(self, *, worker_id: str | None = None) -> JobQueueItem | None:
        self._ensure_schema()
        worker = worker_id or f"worker-{socket.gethostname()}"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH next_item AS (
                        SELECT run_id
                        FROM job_queue
                        WHERE status = 'queued'
                        ORDER BY created_at ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE job_queue q
                    SET status = 'running',
                        worker_id = %s,
                        attempt_count = q.attempt_count + 1,
                        updated_at = NOW()
                    FROM next_item
                    WHERE q.run_id = next_item.run_id
                    RETURNING q.run_id, q.payload_json, q.worker_id
                    """,
                    (worker,),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            return None
        return JobQueueItem(
            run_id=str(row[0]),
            payload=json.loads(str(row[1])),
            worker_id=str(row[2]) if row[2] else None,
        )

    def mark_completed(self, run_id: str) -> None:
        self._set_status(run_id, "completed", error=None)

    def mark_failed(self, run_id: str, error: str) -> None:
        self._set_status(run_id, "failed", error=error)

    def requeue_run(self, run_id: str, *, reason: str | None = None) -> None:
        self._ensure_schema()
        msg = reason or "requeued"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE job_queue
                    SET status = CASE
                            WHEN attempt_count >= max_attempts THEN 'failed'
                            ELSE 'queued'
                        END,
                        error = CASE
                            WHEN attempt_count >= max_attempts THEN
                                COALESCE(%s, 'failed: max delivery attempts reached')
                            ELSE %s
                        END,
                        updated_at = NOW()
                    WHERE run_id = %s AND status = 'running'
                    """,
                    (msg, msg, run_id),
                )
            conn.commit()

    def _set_status(self, run_id: str, status: str, error: str | None) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE job_queue SET status = %s, error = %s, updated_at = NOW() WHERE run_id = %s",
                    (status, error, run_id),
                )
            conn.commit()

    def heartbeat(self, run_id: str, *, worker_id: str | None = None) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                if worker_id:
                    cur.execute(
                        """
                        UPDATE job_queue
                        SET updated_at = NOW(), worker_id = %s
                        WHERE run_id = %s AND status = 'running'
                        """,
                        (worker_id, run_id),
                    )
                else:
                    cur.execute(
                        "UPDATE job_queue SET updated_at = NOW() WHERE run_id = %s AND status = 'running'",
                        (run_id,),
                    )
            conn.commit()

    def requeue_stale_running(self, *, stale_after_sec: int) -> int:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE job_queue
                    SET status = CASE
                            WHEN attempt_count >= max_attempts THEN 'failed'
                            ELSE 'queued'
                        END,
                        error = CASE
                            WHEN attempt_count >= max_attempts THEN
                                COALESCE(error, 'failed: max delivery attempts reached')
                            ELSE COALESCE(error, 'requeued after stale running heartbeat')
                        END,
                        updated_at = NOW()
                    WHERE status = 'running'
                      AND updated_at < NOW() - (%s * INTERVAL '1 second')
                    """,
                    (max(1, stale_after_sec),),
                )
                updated = cur.rowcount
            conn.commit()
        return int(updated)

    def get_job(self, run_id: str) -> dict[str, Any] | None:
        """Return raw job row for introspection (status, error, payload, timestamps)."""
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, status, payload_json, error, created_at, updated_at
                    FROM job_queue
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "run_id": str(row[0]),
            "status": str(row[1]),
            "payload": json.loads(str(row[2])) if row[2] is not None else None,
            "error": str(row[3]) if row[3] is not None else None,
            "created_at": str(row[4]) if row[4] is not None else None,
            "updated_at": str(row[5]) if row[5] is not None else None,
        }

    def snapshot(self, *, stale_after_sec: int) -> dict[str, int]:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        SUM(CASE WHEN status='queued' THEN 1 ELSE 0 END) AS queued,
                        SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) AS running,
                        SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed,
                        SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
                        SUM(
                            CASE
                                WHEN status='running' AND updated_at < NOW() - (%s * INTERVAL '1 second')
                                THEN 1 ELSE 0
                            END
                        ) AS stale_running,
                        SUM(
                            CASE
                                WHEN status='failed' AND error LIKE 'failed: max delivery attempts%%'
                                THEN 1 ELSE 0
                            END
                        ) AS dead_letter
                    FROM job_queue
                    """,
                    (max(1, stale_after_sec),),
                )
                row = cur.fetchone()
        if row is None:
            return {
                "queued": 0,
                "running": 0,
                "completed": 0,
                "failed": 0,
                "stale_running": 0,
                "dead_letter": 0,
            }
        return {
            "queued": int(row[0] or 0),
            "running": int(row[1] or 0),
            "completed": int(row[2] or 0),
            "failed": int(row[3] or 0),
            "stale_running": int(row[4] or 0),
            "dead_letter": int(row[5] or 0),
        }

    def list_dead_letter(self, *, limit: int = 100) -> list[dict[str, Any]]:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, attempt_count, max_attempts, worker_id, error, updated_at
                    FROM job_queue
                    WHERE status = 'failed' AND error LIKE 'failed: max delivery attempts%%'
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (max(1, min(limit, 1000)),),
                )
                rows = cur.fetchall()
        out: list[dict[str, Any]] = []
        for run_id, attempt_count, max_attempts, worker_id, error, updated_at in rows:
            out.append(
                {
                    "run_id": str(run_id),
                    "attempt_count": int(attempt_count or 0),
                    "max_attempts": int(max_attempts or 0),
                    "worker_id": str(worker_id) if worker_id else None,
                    "error": str(error) if error else None,
                    "updated_at": str(updated_at) if updated_at else None,
                }
            )
        return out

    def requeue_failed(self, run_id: str) -> bool:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE job_queue
                    SET status = 'queued',
                        error = 'requeued manually',
                        attempt_count = 0,
                        worker_id = NULL,
                        updated_at = NOW()
                    WHERE run_id = %s AND status = 'failed'
                    """,
                    (run_id,),
                )
                updated = cur.rowcount
            conn.commit()
        return bool(updated)


class InMemoryJobQueue:
    def enqueue(self, run_id: str, payload: dict[str, Any]) -> None:
        _ = run_id, payload

    def status(self, run_id: str) -> str | None:
        _ = run_id
        return None

    def snapshot(self, *, stale_after_sec: int) -> dict[str, int]:
        _ = stale_after_sec
        return {
            "queued": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "stale_running": 0,
            "dead_letter": 0,
        }

    def list_dead_letter(self, *, limit: int = 100) -> list[dict[str, Any]]:
        _ = limit
        return []

    def requeue_failed(self, run_id: str) -> bool:
        _ = run_id
        return False


_queue = (
    PostgresJobQueue() if settings.job_queue_backend.lower() == "postgres" else InMemoryJobQueue()
)


def get_job_queue() -> PostgresJobQueue | InMemoryJobQueue:
    return _queue


def safe_queue_status(run_id: str) -> str | None:
    try:
        return get_job_queue().status(run_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("Job queue status lookup failed: {}", e)
        return None


def safe_queue_snapshot(*, stale_after_sec: int) -> dict[str, int] | None:
    try:
        queue = get_job_queue()
        if hasattr(queue, "snapshot"):
            return queue.snapshot(stale_after_sec=stale_after_sec)
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("Job queue snapshot failed: {}", e)
        return None


def safe_get_job(run_id: str) -> dict[str, Any] | None:
    """Safe wrapper around PostgresJobQueue.get_job for API usage."""
    try:
        queue = get_job_queue()
        if hasattr(queue, "get_job"):
            return queue.get_job(run_id)  # type: ignore[no-any-return]
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("Job queue get_job failed: {}", e)
        return None


def safe_dead_letter_list(*, limit: int = 100) -> list[dict[str, Any]] | None:
    try:
        queue = get_job_queue()
        if hasattr(queue, "list_dead_letter"):
            return queue.list_dead_letter(limit=limit)
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("Dead-letter list failed: {}", e)
        return None


def safe_requeue_failed(run_id: str) -> bool:
    try:
        queue = get_job_queue()
        if hasattr(queue, "requeue_failed"):
            return bool(queue.requeue_failed(run_id))
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("Dead-letter requeue failed: {}", e)
        return False
