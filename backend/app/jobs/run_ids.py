"""Unique job / orchestration run identifiers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime


def new_run_id() -> str:
    """
    Return a unique id for each call.

    Seconds-only timestamps collide when many clients POST in parallel (e.g. six
    ``POST /backtesting/{ticker}/run`` from the compare UI), which overwrote a
    single in-memory job row and one ``jobs/backtests/{run_id}.json`` file — all
    models then appeared identical.
    """
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:12]}"
