"""
Тонкая обёртка: см. backend/scripts/download_ohlcv_dataset.py (plotly-demo, stooq, csv).
"""

import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
_SCRIPT = _BACKEND / "scripts" / "download_ohlcv_dataset.py"


def main() -> None:
    uv = shutil.which("uv")
    cmd: list[str]
    if uv:
        cmd = [uv, "run", "python", str(_SCRIPT), "plotly-demo", "--run-etl"]
    else:
        cmd = [sys.executable, str(_SCRIPT), "plotly-demo", "--run-etl"]
    print("Running:", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(_BACKEND), check=False)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
