"""Regresión: qué archivos se capturan en cada fase.

Ejecutar desde la raíz:  python tests/test_file_change.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.file_change import ChangeStatus, FileChange

EXPECTED = {
    ChangeStatus.MODIFIED: (True, True),
    ChangeStatus.ADDED: (False, True),
    ChangeStatus.DELETED: (True, False),
    ChangeStatus.RENAMED: (True, True),
    ChangeStatus.COPIED: (True, True),
    ChangeStatus.TYPE_CHANGED: (True, True),
}


def test_phase_membership() -> None:
    for status, (want_before, want_after) in EXPECTED.items():
        change = FileChange(path="f.java", status=status)
        assert change.in_before is want_before, (
            f"{status.name}: in_before={change.in_before}, esperado {want_before}"
        )
        assert change.in_after is want_after, (
            f"{status.name}: in_after={change.in_after}, esperado {want_after}"
        )


def test_labels() -> None:
    renamed = FileChange(path="new.java", status=ChangeStatus.RENAMED, old_path="old.java")
    assert renamed.label == "old.java → new.java"
    assert renamed.before_label() == "old.java"
    plain = FileChange(path="new.java", status=ChangeStatus.ADDED)
    assert plain.label == "new.java"
    assert plain.before_label() == "new.java"


if __name__ == "__main__":
    test_phase_membership()
    test_labels()
    print("test_file_change: OK")
