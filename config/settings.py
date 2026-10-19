from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from models.screen_region import ScreenRegion

logger = logging.getLogger(__name__)

APP_DIR_NAME = "sonar_compare"
CONFIG_FILE_NAME = "config.json"


def default_config_dir() -> Path:
    return Path.home() / f".{APP_DIR_NAME}"


@dataclass
class AppSettings:
    """Preferencias persistidas entre sesiones."""

    repo_path: str = ""
    base_branch: str = ""
    compare_branch: str = ""
    output_path: str = ""
    use_same_region: bool = True
    region_before: ScreenRegion | None = None
    region_after: ScreenRegion | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["region_before"] = self.region_before.to_dict() if self.region_before else None
        data["region_after"] = self.region_after.to_dict() if self.region_after else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppSettings:
        region_before = None
        region_after = None
        if isinstance(data.get("region_before"), dict):
            region_before = ScreenRegion.from_dict(data["region_before"])
        if isinstance(data.get("region_after"), dict):
            region_after = ScreenRegion.from_dict(data["region_after"])
        return cls(
            repo_path=str(data.get("repo_path", "")),
            base_branch=str(data.get("base_branch", "")),
            compare_branch=str(data.get("compare_branch", "")),
            output_path=str(data.get("output_path", "")),
            use_same_region=bool(data.get("use_same_region", True)),
            region_before=region_before,
            region_after=region_after,
        )


def load_settings(path: Path | None = None) -> AppSettings:
    path = path or default_config_dir() / CONFIG_FILE_NAME
    if not path.exists():
        return AppSettings()
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("El archivo de configuración no es un objeto JSON")
        return AppSettings.from_dict(data)
    except (OSError, ValueError, json.JSONDecodeError):
        logger.warning("No se pudo leer la configuración en %s; se usarán valores por defecto", path)
        return AppSettings()


def save_settings(settings: AppSettings, path: Path | None = None) -> None:
    path = path or default_config_dir() / CONFIG_FILE_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Escritura atómica para no corromper la config si el proceso muere a mitad
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(settings.to_dict(), fh, indent=2, ensure_ascii=False)
            os.replace(tmp_name, path)
        except OSError:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise
    except OSError:
        logger.exception("No se pudo guardar la configuración en %s", path)
