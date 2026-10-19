from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from core.errors import GitError
from core.git_service import GitService
from gui.bridge import UiBridge

logger = logging.getLogger(__name__)


class BranchSearchDialog:
    """Diálogo modal para buscar ramas locales o remotas con filtro.

    - Muestra ramas locales y remote-tracking (ya obtenidas con fetch).
    - Botón "Buscar en remoto…": consulta `git ls-remote` e incluye ramas
      del remoto que aún no existan localmente (marcadas como "sin fetch").
    """

    def __init__(self, git: GitService, repo: Path, bridge: UiBridge) -> None:
        self._git = git
        self._repo = repo
        self._bridge = bridge
        self._refs: list[str] = []
        self._visible_refs: list[str] = []
        self._fetched: set[str] = set()
        self._selected: str | None = None
        self._querying = False

    def open(self, parent: tk.Tk, title: str = "Buscar rama") -> str | None:
        """Abre el diálogo modal. Devuelve la ref elegida o None si se cancela."""
        self._selected = None

        dialog = tk.Toplevel(parent)
        dialog.title(title)
        dialog.transient(parent)
        dialog.grab_set()
        dialog.minsize(480, 420)

        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # Filtro
        filter_row = ttk.Frame(frame)
        filter_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(filter_row, text="Filtro:").pack(side=tk.LEFT)
        filter_var = tk.StringVar()
        entry = ttk.Entry(filter_row, textvariable=filter_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(filter_row, text="Buscar en remoto…", command=self._query_remote).pack(
            side=tk.LEFT
        )

        # Lista
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self._listbox = tk.Listbox(
            list_frame, yscrollcommand=scrollbar.set, font=("Consolas", 10)
        )
        scrollbar.configure(command=self._listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._status_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self._status_var, foreground="#555").pack(
            anchor="w", pady=(4, 0)
        )

        # Botones
        button_row = ttk.Frame(frame)
        button_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(button_row, text="Seleccionar", command=self._on_select).pack(side=tk.LEFT)
        ttk.Button(button_row, text="Cancelar", command=dialog.destroy).pack(
            side=tk.LEFT, padx=6
        )

        filter_var.trace_add("write", lambda *_: self._refresh_list(filter_var.get()))
        self._listbox.bind("<Double-ButtonRelease-1>", lambda _e: self._on_select())
        entry.focus_set()

        self._load_local_refs(dialog)

        parent.wait_window(dialog)
        return self._selected

    # ---------------------------------------------------------------- datos

    def _load_local_refs(self, dialog: tk.Tk) -> None:
        try:
            local = self._git.list_branches(self._repo)
            remote = self._git.list_remote_branches(self._repo)
        except GitError as exc:
            self._status_var.set(f"Error consultando ramas: {exc}")
            return
        self._fetched = set(local) | set(remote)
        self._refs = sorted(local + remote)
        default = self._git.default_remote(self._repo)
        suffix = f" (remoto: {default})" if default else " (sin remotos)"
        self._status_var.set(
            f"{len(local)} locales, {len(remote)} remotas{suffix}. "
            "Usa 'Buscar en remoto…' para ramas aún no traídas."
        )
        self._refresh_list("")

    def _query_remote(self) -> None:
        if self._querying:
            return
        remote = self._git.default_remote(self._repo)
        if remote is None:
            self._status_var.set("El repositorio no tiene remotos configurados.")
            return
        self._querying = True
        self._status_var.set(f"Consultando ramas en '{remote}' (puede tardar)…")

        def worker() -> None:
            refs: list[str] | None = None
            error: str | None = None
            try:
                refs = self._git.ls_remote_heads(self._repo, remote)
            except GitError as exc:
                error = str(exc)
            self._bridge.post(self._on_remote_result, refs, error)

        threading.Thread(target=worker, daemon=True, name="ls-remote").start()

    def _on_remote_result(self, refs: list[str] | None, error: str | None) -> None:
        self._querying = False
        # Este callback puede llegar tras cerrar el diálogo
        if not self._listbox.winfo_exists():
            return
        if error is not None:
            self._status_var.set(f"Error: {error}")
            return
        assert refs is not None
        known = set(self._refs)
        new_count = 0
        for ref in refs:
            if ref not in known:
                self._refs.append(ref)
                known.add(ref)
                new_count += 1
            self._fetched.add(ref)
        self._refs.sort()
        self._status_var.set(
            f"Remoto: {len(refs)} ramas ({new_count} nuevas). "
            "Las marcadas '(sin fetch)' se obtendrán automáticamente al ejecutar."
        )
        self._refresh_list("")

    # -------------------------------------------------------------- display

    def _refresh_list(self, filter_text: str) -> None:
        needle = filter_text.strip().lower()
        self._listbox.delete(0, tk.END)
        self._visible_refs = [
            ref for ref in self._refs if not needle or needle in ref.lower()
        ]
        for ref in self._visible_refs:
            if ref in self._fetched:
                self._listbox.insert(tk.END, ref)
            else:
                self._listbox.insert(tk.END, f"{ref}    (sin fetch)")
        if self._visible_refs:
            self._listbox.selection_set(0)

    def _on_select(self) -> None:
        selection = self._listbox.curselection()
        if not selection:
            return
        self._selected = self._visible_refs[selection[0]]
        self._listbox.winfo_toplevel().destroy()
