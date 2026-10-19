from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScreenRegion:
    """Región rectangular de pantalla en píxeles físicos (coords. absolutas)."""

    left: int
    top: int
    width: int
    height: int

    def is_valid(self) -> bool:
        return self.width >= 10 and self.height >= 10

    def to_mss_dict(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }

    def to_dict(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScreenRegion | None:
        try:
            region = cls(
                left=int(data["left"]),
                top=int(data["top"]),
                width=int(data["width"]),
                height=int(data["height"]),
            )
        except (KeyError, TypeError, ValueError):
            return None
        return region if region.is_valid() else None
