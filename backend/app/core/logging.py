import sys
from loguru import logger
from app.core.config import settings


def setup_logging() -> None:
    logger.remove()
    level = "DEBUG" if settings.debug else "INFO"
    logger.add(
        sys.stdout,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )
    logger.add(
        "logs/equisense.log",
        level="INFO",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
    )
