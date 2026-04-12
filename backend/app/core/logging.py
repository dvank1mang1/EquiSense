import sys

from loguru import logger

from app.core.config import settings


_CONTEXT_DEFAULTS = {
    "request_id": "-",
    "method": "-",
    "path": "-",
    "status_code": "-",
    "client_ip": "-",
    "duration_ms": "-",
    "run_id": "-",
    "job_type": "-",
    "worker_id": "-",
}


def _patch_record(record: dict) -> None:
    extra = record["extra"]
    for key, value in _CONTEXT_DEFAULTS.items():
        extra.setdefault(key, value)

    context_parts = []
    if extra["request_id"] != "-":
        context_parts.append(f"request_id={extra['request_id']}")
    if extra["method"] != "-":
        context_parts.append(f"method={extra['method']}")
    if extra["path"] != "-":
        context_parts.append(f"path={extra['path']}")
    if extra["status_code"] != "-":
        context_parts.append(f"status={extra['status_code']}")
    if extra["duration_ms"] != "-":
        context_parts.append(f"duration_ms={extra['duration_ms']}")
    if extra["client_ip"] != "-":
        context_parts.append(f"client_ip={extra['client_ip']}")
    if extra["run_id"] != "-":
        context_parts.append(f"run_id={extra['run_id']}")
    if extra["job_type"] != "-":
        context_parts.append(f"job_type={extra['job_type']}")
    if extra["worker_id"] != "-":
        context_parts.append(f"worker_id={extra['worker_id']}")
    extra["context"] = " ".join(context_parts) if context_parts else "-"


def setup_logging() -> None:
    logger.remove()
    level = "DEBUG" if settings.debug else "INFO"
    logger.configure(patcher=_patch_record)
    logger.add(
        sys.stdout,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level> | "
            "<cyan>{extra[context]}</cyan>"
        ),
        colorize=True,
    )
    logger.add(
        "logs/equisense.log",
        level="INFO",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
    )
