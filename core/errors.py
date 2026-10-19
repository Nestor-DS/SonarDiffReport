from __future__ import annotations


class SonarCompareError(Exception):
    """Error base de la aplicación."""


class GitError(SonarCompareError):
    """Error al ejecutar operaciones Git."""


class CaptureError(SonarCompareError):
    """Error al capturar la pantalla."""


class WordError(SonarCompareError):
    """Error al generar el documento Word."""


class UserCancelledError(SonarCompareError):
    """El usuario canceló el flujo en curso."""
