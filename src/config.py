"""Central path configuration for InjexCore.

Single source of truth for the project root and the canonical data /
config directories. Every module derives its default I/O paths from the
constants here instead of recomputing ``Path(__file__).resolve().parents[N]``,
so the depth literal exists in exactly one place and the package stays
position-independent once installed (``pip install -e .``).
"""

from __future__ import annotations

from pathlib import Path

# ``src/config.py`` -> parents[0] == ``src``, parents[1] == repository root.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]

DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DATA_DIR: Path = DATA_DIR / "raw"
PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"
FEATURES_DIR: Path = DATA_DIR / "features"
DATASETS_DIR: Path = DATA_DIR / "datasets"

CONFIGS_DIR: Path = PROJECT_ROOT / "configs"

__all__ = [
    "PROJECT_ROOT",
    "DATA_DIR",
    "RAW_DATA_DIR",
    "PROCESSED_DATA_DIR",
    "FEATURES_DIR",
    "DATASETS_DIR",
    "CONFIGS_DIR",
]
