from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.settings import default_config_dir

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

_configured = False


def setup_logging(log_dir: Path | None = None) -> Path:
    """Configura logging a consola + fichero rotatorio. Devuelve la ruta del log."""
    global _configured
    log_dir = log_dir or default_config_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "sonar_compare.log"

    root = logging.getLogger()
    if _configured:
        return log_file

    root.setLevel(logging.INFO)
    formatter = logging.Formatter(_LOG_FORMAT)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    _configured = True
    return log_file


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
