"""One place for data paths (Wealth Engine, harvesters, ETL and the API).

`DATA_DIR` env var overrides the repo `data/` directory, e.g. `/app/data` in the
container. Everything else is derived from it. Relative paths in the env var
are resolved against the current working directory once, at import.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _data_dir() -> Path:
    raw = os.getenv("DATA_DIR", "").strip()
    return Path(raw).resolve() if raw else REPO_ROOT / "data"


DATA_DIR = _data_dir()
CONFIG_DIR = DATA_DIR / "config"
PROCESSED_DIR = DATA_DIR / "processed"
RAW_DIR = DATA_DIR / "raw"
