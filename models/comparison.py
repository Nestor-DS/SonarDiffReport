from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from models.file_change import FileChange


@dataclass
class ComparisonEntry:
    """Una fila de la tabla Antes/Después del documento Word."""

    change: FileChange
    before_image: Path | None = None
    after_image: Path | None = None
