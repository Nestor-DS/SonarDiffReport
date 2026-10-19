from __future__ import annotations

import logging
import threading
from pathlib import Path

import mss
from PIL import Image
from pynput import keyboard

from core.errors import CaptureError, UserCancelledError
from models.screen_region import ScreenRegion

logger = logging.getLogger(__name__)


class ScreenshotService:
    """Captura de una región fija de pantalla con hotkey global de confirmación."""

    def __init__(self, hotkey: keyboard.Key = keyboard.Key.f9) -> None:
        self._hotkey = hotkey

    def capture_region(self, region: ScreenRegion) -> Image.Image:
        if not region.is_valid():
            raise CaptureError(
                f"Región inválida ({region.width}x{region.height}); selecciona al menos 10x10 píxeles."
            )
        try:
            with mss.mss() as sct:
                raw = sct.grab(region.to_mss_dict())
                image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                return image
        except mss.exception.ScreenShotError as exc:
            raise CaptureError(f"No se pudo capturar la región {region}: {exc}") from exc

    def wait_and_capture(
        self,
        region: ScreenRegion,
        cancel_event: threading.Event | None = None,
    ) -> Image.Image:
        """Bloquea hasta que se pulse la hotkey (F9) y captura la región."""
        self._wait_for_hotkey(cancel_event)
        return self.capture_region(region)

    def _wait_for_hotkey(self, cancel_event: threading.Event | None) -> None:
        pressed = threading.Event()

        def on_press(key: object) -> bool | None:
            if key == self._hotkey:
                pressed.set()
                return False  # detiene el listener
            return None

        listener = keyboard.Listener(on_press=on_press)
        listener.start()
        try:
            while not pressed.wait(0.1):
                if cancel_event is not None and cancel_event.is_set():
                    raise UserCancelledError("Captura cancelada por el usuario.")
                if not listener.running:
                    raise CaptureError("El listener de hotkeys se detuvo inesperadamente.")
        finally:
            listener.stop()
            listener.join(timeout=2)

    @staticmethod
    def save_image(image: Image.Image, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            image.save(path, format="PNG")
        except OSError as exc:
            raise CaptureError(f"No se pudo guardar la captura en {path}: {exc}") from exc
        return path
