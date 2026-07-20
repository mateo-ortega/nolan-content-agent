"""Helpers de paths compartidos. Centraliza override de DB para tests E2E."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "NOLAN_PROJECT_ROOT",
    Path(__file__).parent.parent,
))


def pieces_db_path() -> Path:
    """Path a memory/pieces.sqlite respetando NOLAN_PIECES_DB_OVERRIDE."""
    override = os.environ.get("NOLAN_PIECES_DB_OVERRIDE")
    if override:
        return Path(override)
    return PROJECT_ROOT / "memory" / "pieces.sqlite"
