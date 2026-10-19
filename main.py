from __future__ import annotations

import logging
import multiprocessing
import sys


def _enable_windows_dpi_awareness() -> None:
    """Sin esto, a >100% de escalado las coordenaciones de Tk y las de la
    captura (píxeles físicos) no coinciden y la región saldría desplazada."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        logging.getLogger(__name__).debug("No se pudo activar DPI awareness", exc_info=True)


def main() -> int:
    multiprocessing.freeze_support()  # necesario cuando se empaqueta con PyInstaller
    _enable_windows_dpi_awareness()

    from utils.logger import setup_logging

    log_file = setup_logging()
    logger = logging.getLogger("main")
    logger.info("SonarDiffReport arrancado (log: %s)", log_file)

    import tkinter as tk

    from gui.main_window import MainWindow

    root = tk.Tk()
    MainWindow(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
