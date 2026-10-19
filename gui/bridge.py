from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable, TypeVar

import tkinter as tk

logger = logging.getLogger(__name__)

T = TypeVar("T")


class UiBridge:
    """Puente seguro entre el hilo de trabajo y el hilo principal de Tkinter.

    Tkinter solo puede usarse desde el hilo principal; este puente encola
    llamadas y las ejecuta con ``root.after``. ``call`` bloquea al hilo de
    trabajo hasta obtener el resultado (para diálogos modales).
    """

    def __init__(self, root: tk.Misc, interval_ms: int = 50) -> None:
        self._root = root
        self._interval_ms = interval_ms
        self._queue: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self._schedule_pump()

    def _schedule_pump(self) -> None:
        try:
            self._root.after(self._interval_ms, self._pump)
        except tk.TclError:
            pass  # la ventana se cerró

    def _pump(self) -> None:
        while True:
            try:
                job = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                job()
            except Exception:
                logger.exception("Error ejecutando trabajo de UI encolado")
        self._schedule_pump()

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Ejecuta ``func`` en el hilo de Tk y devuelve su resultado (bloqueante)."""
        done = threading.Event()
        box: dict[str, Any] = {}

        def job() -> None:
            try:
                box["value"] = func(*args, **kwargs)
            except Exception as exc:
                box["error"] = exc
            finally:
                done.set()

        self._queue.put(job)
        done.wait()
        if "error" in box:
            raise box["error"]
        return box.get("value")  # type: ignore[return-value]

    def post(self, func: Callable[..., None], *args: Any, **kwargs: Any) -> None:
        """Ejecuta ``func`` en el hilo de Tk sin esperar resultado."""
        self._queue.put(lambda: func(*args, **kwargs))
