from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import psycopg2
from loguru import logger

from app.contracts.jobs import JobStore
from app.core.config import settings


class FileJobStore:
    """Filesystem-backed job store (current default implementation)."""

    def __init__(self, root: Path | None = None) -> None:
        data_root = (root or Path(settings.model_dir).resolve().parent).resolve()
        self._jobs_dir = data_root / "jobs"
        self._jobs_dir.mkdir(parents=True, exist_ok=True)

    def status_path(self, run_id: str) -> Path:
        return self._jobs_dir / f"refresh_status_{run_id}.json"

    def lineage_path(self, run_id: str) -> Path:
        return self._jobs_dir / f"refresh_lineage_{run_id}.jsonl"

    def metrics_path(self, run_id: str) -> Path:
        return self._jobs_dir / f"refresh_metrics_{run_id}.json"

    def write_status(self, run_id: str, payload: dict[str, Any]) -> Path:
        path = self.status_path(run_id)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def append_lineage_row(self, run_id: str, payload: dict[str, Any]) -> Path:
        path = self.lineage_path(run_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return path

    def write_metrics(self, run_id: str, payload: dict[str, Any]) -> Path:
        path = self.metrics_path(run_id)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def read_status(self, run_id: str) -> dict[str, Any] | None:
        path = self.status_path(run_id)
        if not path.exists():
            return None
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))

    def read_lineage(self, run_id: str, limit: int) -> list[dict[str, Any]] | None:
        path = self.lineage_path(run_id)
        if not path.exists():
            return None
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines()[:limit]:
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def read_metrics(self, run_id: str) -> dict[str, Any] | None:
        path = self.metrics_path(run_id)
        if not path.exists():
            return None
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))

    def latest_lineage_for_ticker(self, ticker: str) -> dict[str, Any] | None:
        sym = ticker.strip().upper()
        candidates = sorted(
            self._jobs_dir.glob("refresh_lineage_*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in candidates:
            lines = path.read_text(encoding="utf-8").splitlines()
            for line in reversed(lines):
                if not line.strip():
                    continue
                row = cast(dict[str, Any], json.loads(line))
                if str(row.get("ticker", "")).upper() == sym:
                    return row
        return None


class PostgresJobStore:
    """Postgres-backed job store for run status, lineage, and metrics."""

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
                    CREATE TABLE IF NOT EXISTS job_runs (
                        run_id TEXT PRIMARY KEY,
                        status_json TEXT NULL,
                        metrics_json TEXT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS job_lineage (
                        id BIGSERIAL PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        ticker TEXT NULL,
                        row_json TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_job_lineage_run_id ON job_lineage(run_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_job_lineage_ticker ON job_lineage(ticker)"
                )
            conn.commit()
        self._schema_ready = True

    def status_path(self, run_id: str) -> Path:
        return Path(f"postgres/jobs/{run_id}/status.json")

    def lineage_path(self, run_id: str) -> Path:
        return Path(f"postgres/jobs/{run_id}/lineage.jsonl")

    def metrics_path(self, run_id: str) -> Path:
        return Path(f"postgres/jobs/{run_id}/metrics.json")

    def write_status(self, run_id: str, payload: dict[str, Any]) -> Path:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO job_runs(run_id, status_json, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (run_id) DO UPDATE
                    SET status_json = EXCLUDED.status_json,
                        updated_at = NOW()
                    """,
                    (run_id, json.dumps(payload, ensure_ascii=False)),
                )
            conn.commit()
        return self.status_path(run_id)

    def append_lineage_row(self, run_id: str, payload: dict[str, Any]) -> Path:
        self._ensure_schema()
        ticker = str(payload.get("ticker", "")).upper() or None
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO job_lineage(run_id, ticker, row_json) VALUES (%s, %s, %s)",
                    (run_id, ticker, json.dumps(payload, ensure_ascii=False)),
                )
            conn.commit()
        return self.lineage_path(run_id)

    def write_metrics(self, run_id: str, payload: dict[str, Any]) -> Path:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO job_runs(run_id, metrics_json, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (run_id) DO UPDATE
                    SET metrics_json = EXCLUDED.metrics_json,
                        updated_at = NOW()
                    """,
                    (run_id, json.dumps(payload, ensure_ascii=False)),
                )
            conn.commit()
        return self.metrics_path(run_id)

    def read_status(self, run_id: str) -> dict[str, Any] | None:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status_json FROM job_runs WHERE run_id = %s", (run_id,))
                row = cur.fetchone()
        if row is None or row[0] is None:
            return None
        return cast(dict[str, Any], json.loads(cast(str, row[0])))

    def read_lineage(self, run_id: str, limit: int) -> list[dict[str, Any]] | None:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT row_json
                    FROM job_lineage
                    WHERE run_id = %s
                    ORDER BY created_at ASC, id ASC
                    LIMIT %s
                    """,
                    (run_id, limit),
                )
                rows = cur.fetchall()
        if not rows:
            return None
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(cast(dict[str, Any], json.loads(cast(str, row[0]))))
        return out

    def read_metrics(self, run_id: str) -> dict[str, Any] | None:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT metrics_json FROM job_runs WHERE run_id = %s", (run_id,))
                row = cur.fetchone()
        if row is None or row[0] is None:
            return None
        return cast(dict[str, Any], json.loads(cast(str, row[0])))

    def latest_lineage_for_ticker(self, ticker: str) -> dict[str, Any] | None:
        self._ensure_schema()
        sym = ticker.strip().upper()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT row_json
                    FROM job_lineage
                    WHERE ticker = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """,
                    (sym,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return cast(dict[str, Any], json.loads(cast(str, row[0])))


class ResilientJobStore:
    """Wrapper that falls back to file store if primary storage fails."""

    def __init__(self, primary: JobStore, fallback: JobStore) -> None:
        self._primary = primary
        self._fallback = fallback

    def status_path(self, run_id: str) -> Path:
        return self._primary.status_path(run_id)

    def lineage_path(self, run_id: str) -> Path:
        return self._primary.lineage_path(run_id)

    def metrics_path(self, run_id: str) -> Path:
        return self._primary.metrics_path(run_id)

    def write_status(self, run_id: str, payload: dict[str, Any]) -> Path:
        self._fallback.write_status(run_id, payload)
        try:
            return self._primary.write_status(run_id, payload)
        except Exception as e:  # noqa: BLE001
            logger.warning("Primary job store write_status failed: {}", e)
            return self._fallback.status_path(run_id)

    def append_lineage_row(self, run_id: str, payload: dict[str, Any]) -> Path:
        self._fallback.append_lineage_row(run_id, payload)
        try:
            return self._primary.append_lineage_row(run_id, payload)
        except Exception as e:  # noqa: BLE001
            logger.warning("Primary job store append_lineage_row failed: {}", e)
            return self._fallback.lineage_path(run_id)

    def write_metrics(self, run_id: str, payload: dict[str, Any]) -> Path:
        self._fallback.write_metrics(run_id, payload)
        try:
            return self._primary.write_metrics(run_id, payload)
        except Exception as e:  # noqa: BLE001
            logger.warning("Primary job store write_metrics failed: {}", e)
            return self._fallback.metrics_path(run_id)

    def read_status(self, run_id: str) -> dict[str, Any] | None:
        local = self._fallback.read_status(run_id)
        if local is not None:
            return local
        try:
            return self._primary.read_status(run_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("Primary job store read_status failed: {}", e)
            return None

    def read_lineage(self, run_id: str, limit: int) -> list[dict[str, Any]] | None:
        local = self._fallback.read_lineage(run_id, limit=limit)
        if local is not None:
            return local
        try:
            return self._primary.read_lineage(run_id, limit=limit)
        except Exception as e:  # noqa: BLE001
            logger.warning("Primary job store read_lineage failed: {}", e)
            return None

    def read_metrics(self, run_id: str) -> dict[str, Any] | None:
        local = self._fallback.read_metrics(run_id)
        if local is not None:
            return local
        try:
            return self._primary.read_metrics(run_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("Primary job store read_metrics failed: {}", e)
            return None

    def latest_lineage_for_ticker(self, ticker: str) -> dict[str, Any] | None:
        local = self._fallback.latest_lineage_for_ticker(ticker)
        if local is not None:
            return local
        try:
            return self._primary.latest_lineage_for_ticker(ticker)
        except Exception as e:  # noqa: BLE001
            logger.warning("Primary job store latest_lineage_for_ticker failed: {}", e)
            return None
