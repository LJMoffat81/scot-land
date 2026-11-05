"""DZ-HEATMAP PR-B0: preconditions for the dz2011 registry tile source.

Two checks, both fail closed with an exact ``DZ2011-PRECHECK: REFUSED:`` message:

* ``check_dz_source(vintage)`` (offline, CI): ``sources.yaml`` pins the
  official Scottish Government ATOM zip, its sha256, product and published
  count, and the registry entry reads ``dz_boundaries`` for that vintage only.
* ``check_dz2011_rows(conn)`` (run before ``run_layer("dz2011")``):
  ``dz_boundaries`` holds exactly 6,976 vintage-2011 rows whose codes equal the
  pinned ``dz2011_keys.json`` set. If it refuses, run
  ``python -m etl.ingest_dz_boundaries --fetch --vintage 2011`` first.

Usage:
  python -m etl.check_dz2011_boundaries --source   # offline
  python -m etl.check_dz2011_boundaries --rows     # needs DATABASE_URL
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
REGISTRY_DIR = REPO_ROOT / "backend" / "layers" / "registry"
DZ2011_KEYS_PATH = REPO_ROOT / "data" / "reference" / "v14" / "dz2011_keys.json"
DZ2011_KEYS_SHA256 = "2611c9e701d9affef34680be2a0d9bbc14468ddbc5241f353819f9ee59849874"
DZ2011_EXPECTED_COUNT = 6976

PREFIX = "DZ2011-PRECHECK: REFUSED: "

OFFICIAL_SOURCES: dict[int, dict[str, Any]] = {
    2011: {
        "layer_id": "dz2011",
        "url": "https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2011.zip",
        "sha256": "846950b7dc74fdedc8a6c5c3d9fd9c5afeca3477a103505b590613bc9704bed8",
        "product": "DataZoneBdry2011",
        "expected_count": 6976,
    },
    2022: {
        "layer_id": "dz2022",
        "url": "https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2022.zip",
        "sha256": "421c648480c7d51e32934de9f1b9f6cbbf86c6d8d382aab30a7bb4d2049ef0ec",
        "product": "DataZoneBdry2022",
        "expected_count": 7392,
    },
}


class PrecheckError(RuntimeError):
    """Raised with a ``DZ2011-PRECHECK: REFUSED:`` message."""


def _refuse(field: str, expected: Any, got: Any) -> PrecheckError:
    return PrecheckError(f"{PREFIX}{field}: expected {expected}, got {got}")


def check_dz_source(
    vintage: int,
    *,
    sources_path: Path = SOURCES_PATH,
    registry_dir: Path = REGISTRY_DIR,
) -> None:
    """Refuse unless sources.yaml and the registry entry pin the official SG source."""
    if vintage not in OFFICIAL_SOURCES:
        raise _refuse("vintage", "2011 or 2022", vintage)
    want = OFFICIAL_SOURCES[vintage]
    cfg = yaml.safe_load(sources_path.read_text(encoding="utf-8")) or {}
    vintages = (cfg.get("data_zone_boundaries") or {}).get("vintages") or {}
    pinned = vintages.get(vintage)
    if not isinstance(pinned, dict):
        raise _refuse(f"sources.yaml data_zone_boundaries.vintages.{vintage}", "mapping", "absent")
    for key in ("url", "sha256", "product", "expected_count"):
        if pinned.get(key) != want[key]:
            raise _refuse(
                f"sources.yaml data_zone_boundaries.vintages.{vintage}.{key}",
                want[key],
                pinned.get(key),
            )
    layer_id = want["layer_id"]
    raw = yaml.safe_load((registry_dir / f"{layer_id}.yaml").read_text(encoding="utf-8"))
    source = raw.get("source") or {}
    expected_source = {
        "type": "postgis_table",
        "table": "dz_boundaries",
        "id_field": "code",
        "where": f"vintage = {vintage}",
    }
    for key, value in expected_source.items():
        if source.get(key) != value:
            raise _refuse(f"{layer_id} source.{key}", value, source.get(key))
    if raw.get("licence") != "OGL-3.0":
        raise _refuse(f"{layer_id} licence", "OGL-3.0", raw.get("licence"))


def load_keys(path: Path = DZ2011_KEYS_PATH, *, sha256: str = DZ2011_KEYS_SHA256) -> set[str]:
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != sha256:
        raise _refuse("dz2011_keys.json sha256", sha256, actual)
    keys = json.loads(data.decode("utf-8"))
    if (
        not isinstance(keys, list)
        or not all(isinstance(k, str) for k in keys)
        or len(set(keys)) != len(keys)
    ):
        raise _refuse("dz2011_keys.json", "unique list of str", "invalid")
    return set(keys)


def check_dz2011_rows(
    conn,
    *,
    keys_path: Path = DZ2011_KEYS_PATH,
    keys_sha256: str = DZ2011_KEYS_SHA256,
    expected_count: int = DZ2011_EXPECTED_COUNT,
) -> None:
    """Refuse unless dz_boundaries vintage 2011 == the pinned key set (count and codes)."""
    keys = load_keys(keys_path, sha256=keys_sha256)
    if len(keys) != expected_count:
        raise _refuse("dz2011_keys.json count", expected_count, len(keys))
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dz_boundaries WHERE vintage = 2011")
        count = int(cur.fetchone()[0])
        if count != expected_count:
            raise _refuse("dz_boundaries vintage=2011 count", expected_count, count)
        cur.execute("SELECT code FROM dz_boundaries WHERE vintage = 2011")
        codes = {str(row[0]) for row in cur.fetchall()}
    missing = keys - codes
    extra = codes - keys
    if missing or extra:
        raise _refuse(
            "dz_boundaries vintage=2011 codes",
            "dz2011_keys.json set",
            f"{len(missing)} missing, {len(extra)} extra",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source", action="store_true")
    mode.add_argument("--rows", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.source:
            check_dz_source(2011)
            check_dz_source(2022)
        else:
            import psycopg2

            conn = psycopg2.connect(os.environ["DATABASE_URL"])
            try:
                check_dz2011_rows(conn)
            finally:
                conn.close()
    except PrecheckError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "mode": "source" if args.source else "rows"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
