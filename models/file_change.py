from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ChangeStatus(str, Enum):
    """Estado de un archivo en un diff de Git."""

    MODIFIED = "M"
    ADDED = "A"
    DELETED = "D"
    RENAMED = "R"
    COPIED = "C"
    TYPE_CHANGED = "T"


@dataclass(frozen=True)
class FileChange:
    """Archivo cambiado entre dos ramas."""

    path: str
    status: ChangeStatus
    old_path: str | None = None

    @property
    def in_before(self) -> bool:
        """True si el archivo debe capturarse en la fase Antes."""
        return self.status in {
            ChangeStatus.MODIFIED,
            ChangeStatus.DELETED,
            ChangeStatus.RENAMED,
            ChangeStatus.COPIED,
            ChangeStatus.TYPE_CHANGED,
        }

    @property
    def in_after(self) -> bool:
        """True si el archivo debe capturarse en la fase Después."""
        return self.status in {
            ChangeStatus.MODIFIED,
            ChangeStatus.ADDED,
            ChangeStatus.RENAMED,
            ChangeStatus.COPIED,
            ChangeStatus.TYPE_CHANGED,
        }

    @property
    def label(self) -> str:
        if self.old_path:
            return f"{self.old_path} → {self.path}"
        return self.path

    def before_label(self) -> str:
        return self.old_path or self.path
