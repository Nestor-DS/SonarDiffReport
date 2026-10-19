from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from core.errors import GitError
from models.file_change import ChangeStatus, FileChange

logger = logging.getLogger(__name__)

_STATUS_MAP = {
    "M": ChangeStatus.MODIFIED,
    "A": ChangeStatus.ADDED,
    "D": ChangeStatus.DELETED,
    "R": ChangeStatus.RENAMED,
    "C": ChangeStatus.COPIED,
    "T": ChangeStatus.TYPE_CHANGED,
}


class GitService:
    """Operaciones Git vía subprocess (sin dependencias externas, fácil de empaquetar)."""

    def __init__(self, git_executable: str = "git") -> None:
        self._git = git_executable

    def _run(self, repo: Path, *args: str, timeout: int = 60) -> str:
        command = [self._git, "-c", "core.quotepath=false", *args]
        try:
            result = subprocess.run(
                command,
                cwd=str(repo),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise GitError(
                "No se encontró el ejecutable de Git. Instálalo y asegúrate de que esté en el PATH."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise GitError(f"Git no respondió en {timeout}s: {' '.join(args)}") from exc

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise GitError(f"Git falló ({' '.join(args)}): {stderr or 'error desconocido'}")
        return result.stdout

    def ensure_repo(self, repo: Path) -> None:
        if not repo.exists():
            raise GitError(f"La ruta del repositorio no existe: {repo}")
        try:
            self._run(repo, "rev-parse", "--is-inside-work-tree")
        except GitError as exc:
            raise GitError(f"La ruta no es un repositorio Git válido: {repo}") from exc

    def list_branches(self, repo: Path) -> list[str]:
        """Ramas locales, p.ej. main, feature/x."""
        output = self._run(repo, "branch", "--format=%(refname:short)")
        return sorted(line.strip() for line in output.splitlines() if line.strip())

    def list_remotes(self, repo: Path) -> list[str]:
        output = self._run(repo, "remote")
        return sorted(line.strip() for line in output.splitlines() if line.strip())

    def default_remote(self, repo: Path) -> str | None:
        remotes = self.list_remotes(repo)
        if not remotes:
            return None
        return "origin" if "origin" in remotes else remotes[0]

    def list_remote_branches(self, repo: Path) -> list[str]:
        """Remote-tracking refs ya obtenidos con fetch, p.ej. origin/main.

        Usa for-each-ref para poder descartar los symrefs (origin/HEAD).
        """
        output = self._run(
            repo, "for-each-ref", "--format=%(refname:short)\t%(symref)", "refs/remotes"
        )
        names: set[str] = set()
        for line in output.splitlines():
            name, tab, symref = line.partition("\t")
            name = name.strip()
            if not name or symref.strip() or name.endswith("/HEAD"):
                continue
            names.add(name)
        return sorted(names)

    def ls_remote_heads(self, repo: Path, remote: str | None = None) -> list[str]:
        """Consulta las ramas del remoto SIN fetch (git ls-remote).

        Devuelve refs con prefijo, p.ej. origin/feature-nueva. Útil para
        ramas que aún no existen como remote-tracking local.
        """
        remote = remote or self.default_remote(repo)
        if not remote:
            raise GitError("El repositorio no tiene remotos configurados (git remote).")
        output = self._run(repo, "ls-remote", "--heads", remote, timeout=120)
        prefix = "refs/heads/"
        branches: list[str] = []
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) != 2:
                continue
            ref = parts[1].strip()
            if ref.startswith(prefix):
                branches.append(f"{remote}/{ref[len(prefix):]}")
        return sorted(branches)

    def current_branch(self, repo: Path) -> str:
        output = self._run(repo, "rev-parse", "--abbrev-ref", "HEAD")
        return output.strip()

    def local_branch_exists(self, repo: Path, name: str) -> bool:
        try:
            self._run(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}")
            return True
        except GitError:
            return False

    def branch_exists(self, repo: Path, name: str) -> bool:
        """True si el nombre resuelve: rama local, remote-tracking completo
        (origin/main) o nombre corto con remote-tracking (main → origin/main)."""
        if self.local_branch_exists(repo, name):
            return True
        try:
            self._run(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/{name}")
            return True
        except GitError:
            pass
        if "/" not in name:
            for remote in self.list_remotes(repo):
                try:
                    self._run(
                        repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}/{name}"
                    )
                    return True
                except GitError:
                    continue
        return False

    def ensure_ref(self, repo: Path, branch: str) -> None:
        """Valida que la rama exista. Si es 'remote/rama' y aún no hay
        remote-tracking local, hace fetch puntual solo de esa rama."""
        if self.branch_exists(repo, branch):
            return
        if "/" in branch:
            remote, short = branch.split("/", 1)
            if remote in self.list_remotes(repo) and short:
                logger.info("Fetch puntual de '%s' desde '%s'", short, remote)
                try:
                    self._run(
                        repo,
                        "fetch",
                        remote,
                        f"+refs/heads/{short}:refs/remotes/{remote}/{short}",
                        timeout=120,
                    )
                    return
                except GitError as exc:
                    raise GitError(
                        f"No se pudo obtener la rama '{branch}' del remoto '{remote}': {exc}"
                    ) from exc
        raise GitError(
            f"La rama '{branch}' no existe ni localmente ni como remote-tracking. "
            "Actualiza con 'git fetch' o revisa el nombre."
        )

    def checkout(self, repo: Path, branch: str) -> None:
        """Checkout de rama local o remota.

        Git resuelve los casos por sí mismo: nombre corto con solo remoto
        crea la rama de tracking; 'origin/x' hace checkout en detached HEAD
        con el contenido exacto del remote-tracking.
        """
        logger.info("Checkout de rama '%s' en %s", branch, repo)
        self._run(repo, "checkout", branch)

    def get_changed_files(self, repo: Path, base: str, compare: str) -> list[FileChange]:
        """Archivos cuyo contenido difiere entre las puntas de las dos ramas.

        Usa diff de dos puntos (base..compare = diff de árboles): es lo
        relevante para SonarQube, porque los issues dependen del contenido
        actual de cada rama. El diff de tres puntos (merge-base) serviría
        para un PR y puede quedar vacío si la rama destino es un merge.
        """
        output = self._run(repo, "diff", "--name-status", f"{base}..{compare}")
        changes: list[FileChange] = []
        for line in output.splitlines():
            line = line.rstrip("\r")
            if not line.strip():
                continue
            parts = line.split("\t")
            code = parts[0]
            kind = code[0] if code else ""
            status = _STATUS_MAP.get(kind)
            if status is None:
                logger.warning("Estado de diff no soportado, se omite: %s", line)
                continue
            try:
                if status in (ChangeStatus.RENAMED, ChangeStatus.COPIED):
                    changes.append(FileChange(path=parts[2], status=status, old_path=parts[1]))
                else:
                    changes.append(FileChange(path=parts[1], status=status))
            except IndexError:
                logger.warning("Línea de diff malformada, se omite: %s", line)
        changes.sort(key=lambda c: c.path)
        return changes
