from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import psycopg2
from loguru import logger

from app.core.config import settings


@dataclass
class JobQueueItem:
    run_id: str
    payload: dict[str, Any]


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
                        error TEXT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_job_queue_status_created ON job_queue(status, created_at)"
                )
            conn.commit()
        self._schema_ready = True

    def enqueue(self, run_id: str, payload: dict[str, Any]) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO job_queue(run_id, status, payload_json, updated_at)
                    VALUES (%s, 'queued', %s, NOW())
                    ON CONFLICT (run_id) DO UPDATE
                    SET status = 'queued',
                        payload_json = EXCLUDED.payload_json,
                        error = NULL,
                        updated_at = NOW()
                    """,
                    (run_id, json.dumps(payload, ensure_ascii=False)),
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

    def claim_next(self) -> JobQueueItem | None:
        self._ensure_schema()
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
                    SET status = 'running', updated_at = NOW()
                    FROM next_item
                    WHERE q.run_id = next_item.run_id
                    RETURNING q.run_id, q.payload_json
                    """
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            return None
        return JobQueueItem(run_id=str(row[0]), payload=json.loads(str(row[1])))

    def mark_completed(self, run_id: str) -> None:
        self._set_status(run_id, "completed", error=None)

    def mark_failed(self, run_id: str, error: str) -> None:
        self._set_status(run_id, "failed", error=error)

    def _set_status(self, run_id: str, status: str, error: str | None) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE job_queue SET status = %s, error = %s, updated_at = NOW() WHERE run_id = %s",
                    (status, error, run_id),
                )
            conn.commit()


class InMemoryJobQueue:
    def enqueue(self, run_id: str, payload: dict[str, Any]) -> None:
        _ = run_id, payload

    def status(self, run_id: str) -> str | None:
        _ = run_id
        return None


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
