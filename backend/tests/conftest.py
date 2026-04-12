"""
Shared fixtures.

Layout mirrors app layers: synthetic market data → feature engineers → persistence.
Paths are always isolated under `tmp_path` to keep tests hermetic.

If `import numpy` fails in a subprocess (e.g. SIGSEGV under a restricted sandbox),
most tests are skipped from collection and only a tiny no-numpy subset runs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

for _k in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ.setdefault(_k, "1")

_NUMERIC_RUNTIME_OK: bool | None = None


def _numeric_runtime_ok() -> bool:
    """True iff a child process can `import numpy` without crashing."""
    global _NUMERIC_RUNTIME_OK
    if _NUMERIC_RUNTIME_OK is not None:
        return _NUMERIC_RUNTIME_OK
    backend_root = Path(__file__).resolve().parent.parent
    try:
        completed = subprocess.run(
            [sys.executable, "-c", "import numpy"],
            cwd=backend_root,
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _NUMERIC_RUNTIME_OK = False
        return False
    _NUMERIC_RUNTIME_OK = completed.returncode == 0
    return _NUMERIC_RUNTIME_OK


def _collect_ignore_when_numeric_broken() -> list[str]:
    tests_root = Path(__file__).resolve().parent
    allowed = frozenset(
        {
            "unit/test_job_queue_inmemory.py",
            "unit/test_av_rate_limit.py",
            "unit/test_numeric_runtime_smoke.py",
        }
    )
    ignored: list[str] = []
    for path in tests_root.rglob("test_*.py"):
        rel = path.relative_to(tests_root).as_posix()
        if rel not in allowed:
            ignored.append(rel)
    return ignored


_NUMERIC_OK = _numeric_runtime_ok()
collect_ignore = _collect_ignore_when_numeric_broken() if not _NUMERIC_OK else []
pytest_plugins = ["tests.conftest_ml"] if _NUMERIC_OK else []

if collect_ignore:
    print(
        "EquiSense: numpy unavailable in a child process — running a minimal test subset "
        "(3 files). Use a full environment for the sklearn/pandas suite.",
        file=sys.stderr,
    )


@pytest.fixture(autouse=True)
def _limit_blas_threads_for_integration(request: pytest.FixtureRequest):
    """Single-thread BLAS/OpenMP for integration tests — fewer flakes on GitHub runners."""
    if request.node.get_closest_marker("integration") is None:
        yield
        return

    keys = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")
    saved = {k: os.environ.get(k) for k in keys}
    try:
        for k in keys:
            os.environ[k] = "1"
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@pytest.fixture
def isolated_data_root(tmp_path: Path) -> Path:
    """
    Mirrors repo layout: {tmp}/raw/..., {tmp}/processed/..., {tmp}/models optional.
    """
    root = tmp_path / "data"
    (root / "raw" / "ohlcv").mkdir(parents=True)
    (root / "raw" / "fundamentals").mkdir(parents=True)
    (root / "processed").mkdir(parents=True)
    (root / "models").mkdir(parents=True)
    return root


@pytest.fixture
def sample_overview_dict() -> dict:
    """Alpha Vantage OVERVIEW-shaped payload (string values like API)."""
    return {
        "Symbol": "TEST",
        "PERatio": "28.5",
        "EPS": "6.15",
        "QuarterlyRevenueGrowthYOY": "0.082",
        "ReturnOnEquityTTM": "0.147",
        "DebtToEquityRatio": "1.23",
        "DividendYield": "0.015",
    }
