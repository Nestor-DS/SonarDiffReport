from __future__ import annotations

import logging
import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from core.errors import GitError, SonarCompareError, UserCancelledError
from core.git_service import GitService
from core.screenshot_service import ScreenshotService
from core.word_service import WordService
from models.comparison import ComparisonEntry
from models.file_change import FileChange
from models.screen_region import ScreenRegion

logger = logging.getLogger(__name__)


@dataclass
class ComparisonRequest:
    """Parámetros completos de una ejecución del flujo Antes/Después."""

    repo_path: Path
    base_branch: str
    compare_branch: str
    output_path: Path
    region_before: ScreenRegion
    region_after: ScreenRegion | None = None
    use_same_region: bool = True


class WorkflowUi(Protocol):
    """Contrato que la GUI implementa para interactuar con el flujo en background."""

    def info(self, message: str) -> None: ...

    def confirm(self, message: str) -> bool: ...

    def select_region(self, prompt: str) -> ScreenRegion: ...

    def update_progress(self, message: str) -> None: ...


class ComparisonService:
    """Orquesta el flujo completo: diff → fase Antes → fase Después → Word."""

    def __init__(
        self,
        git: GitService,
        screenshots: ScreenshotService,
        word: WordService,
    ) -> None:
        self._git = git
        self._screenshots = screenshots
        self._word = word
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self, request: ComparisonRequest, ui: WorkflowUi) -> Path:
        self._cancel.clear()
        repo = request.repo_path

        self._git.ensure_repo(repo)
        for branch in (request.base_branch, request.compare_branch):
            # Si es una rama remota aún no traída, hace fetch puntual
            self._git.ensure_ref(repo, branch)

        changes = self._git.get_changed_files(repo, request.base_branch, request.compare_branch)
        if not changes:
            raise SonarCompareError(
                "No hay archivos cambiados entre las ramas seleccionadas."
            )

        ui.update_progress(f"Archivos cambiados encontrados: {len(changes)}")
        original_branch = self._git.current_branch(repo)
        region_after = request.region_after
        work_dir = Path(tempfile.mkdtemp(prefix="sonar_compare_"))
        captures_before: dict[str, Path] = {}
        captures_after: dict[str, Path] = {}

        try:
            self._phase_before(request, changes, ui, captures_before, work_dir)

            if not request.use_same_region and region_after is None:
                ui.update_progress("Selecciona la región para la fase DESPUÉS…")
                region_after = ui.select_region(
                    "Selecciona la región para la fase Después y pulsa ESC para cancelar."
                )
            if region_after is None:
                region_after = request.region_before

            self._phase_after(request, changes, ui, captures_after, work_dir, region_after)

            entries = [
                ComparisonEntry(
                    change=change,
                    before_image=captures_before.get(change.path),
                    after_image=captures_after.get(change.path),
                )
                for change in changes
            ]
            ui.update_progress("Generando documento Word…")
            output = self._word.generate(
                request.output_path,
                request.base_branch,
                request.compare_branch,
                entries,
                str(repo),
            )
            ui.update_progress(f"Documento generado: {output}")
            return output
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
            self._restore_branch(repo, original_branch, ui)

    # ------------------------------------------------------------------ fases

    def _phase_before(
        self,
        request: ComparisonRequest,
        changes: list[FileChange],
        ui: WorkflowUi,
        captures: dict[str, Path],
        work_dir: Path,
    ) -> None:
        files = [c for c in changes if c.in_before]
        if not files:
            return
        branch = request.base_branch
        if not ui.confirm(
            f"Se cambiará a la rama '{branch}' para la fase ANTES.\n"
            "¿Continuar?"
        ):
            raise UserCancelledError("Fase Antes cancelada por el usuario.")

        self._git.checkout(request.repo_path, branch)
        ui.update_progress(
            f"Fase ANTES ({branch}): {len(files)} archivo(s). "
            "Abre cada archivo en Eclipse/Sonar y pulsa F9 para capturar."
        )
        total = len(files)
        for index, change in enumerate(files, 1):
            self._raise_if_cancelled()
            ui.update_progress(f"[Antes {index}/{total}] {change.before_label()}")
            image = self._screenshots.wait_and_capture(request.region_before, self._cancel)
            captures[change.path] = self._screenshots.save_image(
                image, work_dir / f"before_{index:03d}.png"
            )

    def _phase_after(
        self,
        request: ComparisonRequest,
        changes: list[FileChange],
        ui: WorkflowUi,
        captures: dict[str, Path],
        work_dir: Path,
        region: ScreenRegion,
    ) -> None:
        files = [c for c in changes if c.in_after]
        if not files:
            return
        branch = request.compare_branch
        if not ui.confirm(
            f"Se cambiará a la rama '{branch}' para la fase DESPUÉS.\n"
            "¿Continuar?"
        ):
            raise UserCancelledError("Fase Después cancelada por el usuario.")

        self._git.checkout(request.repo_path, branch)
        ui.update_progress(
            f"Fase DESPUÉS ({branch}): {len(files)} archivo(s). "
            "Abre cada archivo en Eclipse/Sonar y pulsa F9 para capturar."
        )
        total = len(files)
        for index, change in enumerate(files, 1):
            self._raise_if_cancelled()
            ui.update_progress(f"[Después {index}/{total}] {change.path}")
            image = self._screenshots.wait_and_capture(region, self._cancel)
            captures[change.path] = self._screenshots.save_image(
                image, work_dir / f"after_{index:03d}.png"
            )

    # ----------------------------------------------------------------- varios

    def _restore_branch(self, repo: Path, original_branch: str, ui: WorkflowUi) -> None:
        if not original_branch or original_branch == "HEAD":
            logger.warning("No se puede restaurar la rama original (HEAD detached o vacía).")
            return
        try:
            current = self._git.current_branch(repo)
            if current != original_branch:
                self._git.checkout(repo, original_branch)
                ui.update_progress(f"Rama original restaurada: {original_branch}")
        except GitError as exc:
            logger.warning("No se pudo restaurar la rama '%s': %s", original_branch, exc)
            ui.update_progress(
                f"Aviso: no se pudo restaurar la rama '{original_branch}' automáticamente."
            )

    def _raise_if_cancelled(self) -> None:
        if self._cancel.is_set():
            raise UserCancelledError("Flujo cancelado por el usuario.")
