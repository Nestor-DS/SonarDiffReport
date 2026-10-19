from __future__ import annotations

import logging
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from config.settings import AppSettings, load_settings, save_settings
from core.comparison_service import ComparisonRequest, ComparisonService, WorkflowUi
from core.errors import SonarCompareError, UserCancelledError
from core.git_service import GitService
from core.screenshot_service import ScreenshotService
from core.word_service import WordService
from gui.bridge import UiBridge
from gui.branch_search_dialog import BranchSearchDialog
from gui.region_selector import RegionSelector
from models.screen_region import ScreenRegion

logger = logging.getLogger(__name__)

_STATUS_MAX_LINES = 200


class MainWindow:
    """Ventana principal: configuración del análisis y lanzamiento del flujo."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._settings = load_settings()
        self._bridge = UiBridge(root)
        self._git = GitService()
        self._service = ComparisonService(self._git, ScreenshotService(), WordService())

        self._region_before: ScreenRegion | None = self._settings.region_before
        self._region_after: ScreenRegion | None = self._settings.region_after

        root.title("SonarDiffReport — Comparación de issues entre ramas")
        root.minsize(720, 580)
        self._build_widgets()
        self._load_settings_into_ui()

    # ------------------------------------------------------------------ UI

    def _build_widgets(self) -> None:
        pad = {"padx": 10, "pady": 4}
        main = ttk.Frame(self._root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        # Repositorio
        ttk.Label(main, text="Repositorio Git:").grid(row=0, column=0, sticky="w", **pad)
        self._repo_var = tk.StringVar()
        ttk.Entry(main, textvariable=self._repo_var, width=70).grid(
            row=0, column=1, sticky="we", **pad
        )
        ttk.Button(main, text="Examinar…", command=self._browse_repo).grid(row=0, column=2, **pad)

        # Ramas
        ttk.Label(main, text="Rama base (Antes):").grid(row=1, column=0, sticky="w", **pad)
        self._base_var = tk.StringVar()
        self._base_combo = ttk.Combobox(main, textvariable=self._base_var, width=40)
        self._base_combo.grid(row=1, column=1, sticky="we", **pad)
        ttk.Button(
            main, text="Buscar…", command=lambda: self._search_branch(self._base_var)
        ).grid(row=1, column=2, **pad)

        ttk.Label(main, text="Rama a comparar (Después):").grid(row=2, column=0, sticky="w", **pad)
        self._compare_var = tk.StringVar()
        self._compare_combo = ttk.Combobox(main, textvariable=self._compare_var, width=40)
        self._compare_combo.grid(row=2, column=1, sticky="we", **pad)
        ttk.Button(
            main, text="Buscar…", command=lambda: self._search_branch(self._compare_var)
        ).grid(row=2, column=2, **pad)

        branch_buttons = ttk.Frame(main)
        branch_buttons.grid(row=3, column=1, sticky="w", **pad)
        ttk.Button(branch_buttons, text="Listar ramas locales", command=self._list_branches).pack(
            side=tk.LEFT
        )
        ttk.Button(
            branch_buttons, text="Listar local + remoto", command=self._list_all_branches
        ).pack(side=tk.LEFT, padx=(8, 0))

        # Salida
        ttk.Label(main, text="Documento Word de salida:").grid(row=4, column=0, sticky="w", **pad)
        self._output_var = tk.StringVar()
        ttk.Entry(main, textvariable=self._output_var, width=70).grid(
            row=4, column=1, sticky="we", **pad
        )
        ttk.Button(main, text="Examinar…", command=self._browse_output).grid(row=4, column=2, **pad)

        # Regiones
        region_frame = ttk.LabelFrame(main, text="Región de captura de pantalla", padding=10)
        region_frame.grid(row=5, column=0, columnspan=3, sticky="we", **pad)

        self._same_region_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            region_frame,
            text="Usar misma región para Antes y Después",
            variable=self._same_region_var,
            command=self._toggle_region_after,
        ).grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Button(
            region_frame, text="Seleccionar región (Antes)…", command=self._select_region_before
        ).grid(row=1, column=0, sticky="w", **pad)
        self._region_before_label = ttk.Label(region_frame, text="(sin definir)")
        self._region_before_label.grid(row=1, column=1, sticky="w", **pad)

        self._after_button = ttk.Button(
            region_frame, text="Seleccionar región (Después)…", command=self._select_region_after
        )
        self._after_button.grid(row=2, column=0, sticky="w", **pad)
        self._region_after_label = ttk.Label(region_frame, text="(usará la misma que Antes)")
        self._region_after_label.grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(
            region_frame,
            text="Hotkey de captura: F9 (global, pulses cuando el archivo correcto esté a la vista)",
            foreground="#555",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))

        # Acciones
        action_frame = ttk.Frame(main)
        action_frame.grid(row=6, column=0, columnspan=3, sticky="we", **pad)
        self._generate_btn = ttk.Button(
            action_frame, text="Generar comparación", command=self._on_generate
        )
        self._generate_btn.pack(side=tk.LEFT)
        self._cancel_btn = ttk.Button(
            action_frame, text="Cancelar", command=self._on_cancel, state=tk.DISABLED
        )
        self._cancel_btn.pack(side=tk.LEFT, padx=8)

        # Estado
        ttk.Label(main, text="Progreso:").grid(row=7, column=0, sticky="nw", **pad)
        self._status_text = tk.Text(main, height=12, state=tk.DISABLED, wrap=tk.WORD)
        self._status_text.grid(row=8, column=0, columnspan=3, sticky="nsew", **pad)

        main.columnconfigure(1, weight=1)
        main.rowconfigure(8, weight=1)

    def _load_settings_into_ui(self) -> None:
        self._repo_var.set(self._settings.repo_path)
        self._base_var.set(self._settings.base_branch)
        self._compare_var.set(self._settings.compare_branch)
        self._output_var.set(self._settings.output_path)
        self._same_region_var.set(self._settings.use_same_region)
        self._refresh_region_labels()
        self._toggle_region_after()

    # ----------------------------------------------------------- acciones UI

    def _browse_repo(self) -> None:
        initial = self._repo_var.get().strip() or None
        selected = filedialog.askdirectory(title="Seleccionar repositorio Git", initialdir=initial)
        if selected:
            self._repo_var.set(selected)

    def _browse_output(self) -> None:
        initial = self._output_var.get().strip() or None
        selected = filedialog.asksaveasfilename(
            title="Guardar documento Word como…",
            defaultextension=".docx",
            filetypes=[("Documento Word", "*.docx")],
            initialfile=Path(initial).name if initial else "comparacion_sonar.docx",
            initialdir=str(Path(initial).parent) if initial else None,
        )
        if selected:
            self._output_var.set(selected)

    def _list_branches(self) -> None:
        self._fill_branch_combos(include_remote=False)

    def _list_all_branches(self) -> None:
        self._fill_branch_combos(include_remote=True)

    def _fill_branch_combos(self, include_remote: bool) -> None:
        repo = self._require_repo_path(quiet=True)
        if repo is None:
            return
        try:
            branches = self._git.list_branches(repo)
            label = f"locales ({len(branches)})"
            if include_remote:
                remote = self._git.list_remote_branches(repo)
                branches = sorted(branches + remote)
                label = f"locales + remotas ({len(branches)})"
        except SonarCompareError as exc:
            messagebox.showerror("Error Git", str(exc))
            return
        if not branches:
            messagebox.showinfo("Ramas", "No hay ramas en este repositorio.")
            return
        self._base_combo["values"] = branches
        self._compare_combo["values"] = branches
        self._log(f"Ramas {label}: {', '.join(branches)}")

    def _search_branch(self, target: tk.StringVar) -> None:
        repo = self._require_repo_path()
        if repo is None:
            return
        dialog = BranchSearchDialog(self._git, repo, self._bridge)
        selected = dialog.open(self._root, "Buscar rama (local o remota)")
        if selected:
            target.set(selected)
            self._log(f"Rama seleccionada: {selected}")

    def _select_region_before(self) -> None:
        try:
            self._region_before = RegionSelector().select(
                self._root, "Arrastra la región para ANTES. ESC para cancelar."
            )
        except UserCancelledError:
            return
        self._refresh_region_labels()

    def _select_region_after(self) -> None:
        try:
            self._region_after = RegionSelector().select(
                self._root, "Arrastra la región para DESPUÉS. ESC para cancelar."
            )
        except UserCancelledError:
            return
        self._refresh_region_labels()

    def _toggle_region_after(self) -> None:
        state = tk.NORMAL if not self._same_region_var.get() else tk.DISABLED
        self._after_button.configure(state=state)

    def _refresh_region_labels(self) -> None:
        before = self._region_before
        self._region_before_label.configure(
            text=f"{before.width}×{before.height} px en ({before.left},{before.top})"
            if before
            else "(sin definir)"
        )
        after = self._region_after
        if self._same_region_var.get():
            self._region_after_label.configure(text="(usará la misma que Antes)")
        else:
            self._region_after_label.configure(
                text=f"{after.width}×{after.height} px en ({after.left},{after.top})"
                if after
                else "(se preguntará al terminar la fase Antes)"
            )

    # ------------------------------------------------------------ generación

    def _on_generate(self) -> None:
        request = self._build_request()
        if request is None:
            return
        self._save_settings_from_ui()
        self._set_running(True)
        self._log("— Nueva ejecución —")

        def worker() -> None:
            try:
                output = self._service.run(request, _WorkflowUiAdapter(self))
                self._bridge.post(self._on_finished, output, None)
            except Exception as exc:  # el resultado se muestra en el hilo principal
                logger.exception("La comparación falló")
                self._bridge.post(self._on_finished, None, exc)

        threading.Thread(target=worker, daemon=True, name="comparison-worker").start()

    def _on_finished(self, output: Path | None, error: Exception | None) -> None:
        self._set_running(False)
        if error is None and output is not None:
            self._log(f"Documento generado: {output}")
            messagebox.showinfo("Completado", f"Documento generado:\n{output}")
        elif isinstance(error, UserCancelledError):
            self._log("Ejecución cancelada por el usuario.")
            messagebox.showinfo("Cancelado", "La ejecución se canceló. La rama original se restauró.")
        else:
            message = str(error) or error.__class__.__name__
            self._log(f"ERROR: {message}")
            messagebox.showerror("Error", message)

    def _on_cancel(self) -> None:
        self._log("Cancelación solicitada…")
        self._service.cancel()

    def _set_running(self, running: bool) -> None:
        self._generate_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        self._cancel_btn.configure(state=tk.NORMAL if running else tk.DISABLED)

    def _build_request(self) -> ComparisonRequest | None:
        repo = self._require_repo_path()
        if repo is None:
            return None

        base = self._base_var.get().strip()
        compare = self._compare_var.get().strip()
        if not base or not compare:
            messagebox.showwarning("Faltan datos", "Indica la rama base y la rama a comparar.")
            return None
        if base == compare:
            messagebox.showwarning("Ramas iguales", "Las dos ramas deben ser distintas.")
            return None

        output_raw = self._output_var.get().strip()
        if not output_raw:
            messagebox.showwarning("Faltan datos", "Indica la ruta del documento Word de salida.")
            return None
        if not output_raw.lower().endswith(".docx"):
            output_raw += ".docx"
        output = Path(output_raw)

        if self._region_before is None or not self._region_before.is_valid():
            messagebox.showwarning(
                "Región no definida",
                "Selecciona la región de captura para la fase Antes.",
            )
            return None

        use_same = self._same_region_var.get()
        region_after = self._region_after if not use_same else None
        if not use_same and region_after is not None and not region_after.is_valid():
            messagebox.showwarning(
                "Región no válida",
                "La región de Después no es válida; selecciónala de nuevo.",
            )
            return None

        return ComparisonRequest(
            repo_path=repo,
            base_branch=base,
            compare_branch=compare,
            output_path=output,
            region_before=self._region_before,
            region_after=region_after,
            use_same_region=use_same,
        )

    def _require_repo_path(self, quiet: bool = False) -> Path | None:
        raw = self._repo_var.get().strip()
        if not raw:
            if not quiet:
                messagebox.showwarning("Faltan datos", "Selecciona la ruta del repositorio Git.")
            return None
        repo = Path(raw)
        try:
            self._git.ensure_repo(repo)
        except SonarCompareError as exc:
            if not quiet:
                messagebox.showerror("Repositorio inválido", str(exc))
            return None
        return repo

    def _save_settings_from_ui(self) -> None:
        settings = AppSettings(
            repo_path=self._repo_var.get().strip(),
            base_branch=self._base_var.get().strip(),
            compare_branch=self._compare_var.get().strip(),
            output_path=self._output_var.get().strip(),
            use_same_region=self._same_region_var.get(),
            region_before=self._region_before,
            region_after=self._region_after,
        )
        save_settings(settings)

    # -------------------------------------------------------------- utilidades

    def _log(self, message: str) -> None:
        self._status_text.configure(state=tk.NORMAL)
        self._status_text.insert(tk.END, message + "\n")
        # Limitar el historial mostrado
        line_count = int(self._status_text.index("end-1c").split(".")[0])
        if line_count > _STATUS_MAX_LINES:
            self._status_text.delete("1.0", f"{line_count - _STATUS_MAX_LINES}.0")
        self._status_text.see(tk.END)
        self._status_text.configure(state=tk.DISABLED)


class _WorkflowUiAdapter:
    """Adapta MainWindow al protocolo WorkflowUi usando el puente de Tk."""

    def __init__(self, window: MainWindow) -> None:
        self._window = window

    def info(self, message: str) -> None:
        self._window._bridge.call(messagebox.showinfo, "Información", message)

    def confirm(self, message: str) -> bool:
        return bool(
            self._window._bridge.call(messagebox.askyesno, "Confirmación", message)
        )

    def select_region(self, prompt: str) -> ScreenRegion:
        def do_select() -> ScreenRegion:
            return RegionSelector().select(self._window._root, prompt)

        return self._window._bridge.call(do_select)

    def update_progress(self, message: str) -> None:
        self._window._bridge.post(self._window._log, message)
