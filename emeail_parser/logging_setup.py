from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger


_CONFIGURED = False


def configure_logging() -> Path:
    """Configure Loguru sinks for console + file once and return log directory."""
    global _CONFIGURED
    if _CONFIGURED:
        return Path(os.getenv("AGENT_LOG_DIR", "logs")).resolve()

    project_root = Path(__file__).resolve().parent.parent
    log_dir = Path(os.getenv("AGENT_LOG_DIR", str(project_root / "logs"))).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    level = os.getenv("LOG_LEVEL", "INFO").upper()

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = f"agentic_execution_{timestamp}.txt"

    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        backtrace=False,
        diagnose=False,
        enqueue=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
    )
    logger.add(
        str(log_dir / log_filename),
        level=level,
        enqueue=True,
        encoding="utf-8",
        retention="14 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
    )

    _CONFIGURED = True
    logger.info("Loguru configured. Log file: {}", log_dir / log_filename)
    return log_dir
