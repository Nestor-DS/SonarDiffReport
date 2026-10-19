from __future__ import annotations

import tkinter as tk

from core.errors import UserCancelledError
from models.screen_region import ScreenRegion


class RegionSelector:
    """Overlay a pantalla completa para arrastrar y definir una región."""

    MIN_SIZE = 10
    _OUTLINE = "#FF3B30"
    _FILL = "#FF3B30"

    def __init__(self) -> None:
        self._result: ScreenRegion | None = None
        self._start_x = 0
        self._start_y = 0
        self._rect_id: int | None = None

    def select(self, root: tk.Tk, prompt: str = "") -> ScreenRegion:
        """Muestra el selector modal. Lanza UserCancelledError si se pulsa ESC."""
        self._result = None

        overlay = tk.Toplevel(root)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", 0.35)
        overlay.configure(cursor="crosshair", bg="#000000")

        vx = overlay.winfo_vrootx()
        vy = overlay.winfo_vrooty()
        vw = overlay.winfo_vrootwidth()
        vh = overlay.winfo_vrootheight()
        overlay.geometry(f"{vw}x{vh}+{vx}+{vy}")

        canvas = tk.Canvas(overlay, bg="#000000", highlightthickness=0, cursor="crosshair")
        canvas.pack(fill=tk.BOTH, expand=True)

        if prompt:
            label = tk.Label(
                overlay,
                text=prompt,
                bg="#1c1c1e",
                fg="white",
                font=("Segoe UI", 12, "bold"),
                padx=12,
                pady=8,
            )
            label.place(relx=0.5, rely=0.02, anchor="n")

        def on_press(event: tk.Event) -> None:
            self._start_x, self._start_y = event.x, event.y
            self._rect_id = canvas.create_rectangle(
                event.x, event.y, event.x, event.y,
                outline=self._OUTLINE, width=2,
            )

        def on_drag(event: tk.Event) -> None:
            if self._rect_id is not None:
                canvas.coords(self._rect_id, self._start_x, self._start_y, event.x, event.y)

        def on_release(event: tk.Event) -> None:
            left = min(self._start_x, event.x)
            top = min(self._start_y, event.y)
            width = abs(event.x - self._start_x)
            height = abs(event.y - self._start_y)
            if width < self.MIN_SIZE or height < self.MIN_SIZE:
                return  # arrastre demasiado pequeño: se ignora
            self._result = ScreenRegion(
                left=vx + left, top=vy + top, width=width, height=height
            )
            overlay.destroy()

        def on_escape(_event: tk.Event) -> None:
            overlay.destroy()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        overlay.bind("<Escape>", on_escape)

        overlay.focus_force()
        root.wait_window(overlay)

        if self._result is None:
            raise UserCancelledError("Selección de región cancelada.")
        return self._result
