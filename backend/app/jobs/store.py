from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

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
