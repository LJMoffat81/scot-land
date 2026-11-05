"""M6b-tiles AMENDMENT-2: national/fixture ingest provenance for tile gating.

One JSON receipt under ``LAYER_RECEIPT_DIR`` (same pattern as layer receipts).
National receipt is invalidated before any raw-table replacement. Fixture loads
always write ``path: "fixture"`` and never leave a national receipt in place.
Production ``build_tileset`` requires pins + a national receipt bound to the
current raw ingest fingerprint and a successful clipped ``run_layer`` receipt.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from georgist import cpm2016_rules as rules

LAYER_ID = "carbon-peatland"
RAW_TABLE = "carbon_peatland"
# Subdir so etl.refresh_registry's top-level *.json receipt glob ignores it.
PROVENANCE_REL = Path("cpm2016") / "carbon-peatland.provenance.json"
RECEIPT_NAME = "carbon-peatland.receipt.json"
TILE_PREFIX = "CPM2016-TILE: REFUSED: "
INGEST_PREFIX = "CPM2016-INGEST: REFUSED: "
FIXTURE_ENV = "CPM2016_ALLOW_FIXTURE_TILES"
PRODUCTION_ROOT_ENV = "CPM2016_PRODUCTION_TILES_ROOT"


class Cpm2016TileGateError(RuntimeError):
    """Production / fixture tile gate refusal."""


def _receipt_dir() -> Path:
    env = (os.environ.get("LAYER_RECEIPT_DIR") or "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data" / "processed" / "layers"


def provenance_path() -> Path:
    return _receipt_dir() / PROVENANCE_REL


def layer_receipt_path() -> Path:
    return _receipt_dir() / RECEIPT_NAME


def fixture_tiles_allowed() -> bool:
    return os.environ.get(FIXTURE_ENV, "").strip() == "1"


def production_tiles_root() -> Path | None:
    raw = (os.environ.get(PRODUCTION_ROOT_ENV) or "").strip()
    return Path(raw).resolve() if raw else None


def invalidate_national_provenance() -> None:
    """Delete any national provenance so it cannot survive a raw replace."""
    path = provenance_path()
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return
    if isinstance(data, dict) and data.get("path") == "national":
        path.unlink(missing_ok=True)
        return
    # Non-national artifacts are overwritten by the caller; still drop national.
    if isinstance(data, dict) and data.get("path") != "fixture":
        path.unlink(missing_ok=True)


def raw_fingerprint(conn) -> str:
    """Stable identity of current ``carbon_peatland`` rows."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT feature_id, importance
            FROM {RAW_TABLE}
            ORDER BY feature_id
            """
        )
        rows = cur.fetchall()
    payload = json.dumps(
        [[str(fid), int(imp)] for fid, imp in rows],
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_fixture_provenance(conn, *, rows: int) -> Path:
    """Always mark fixture; never leave a national receipt in place."""
    invalidate_national_provenance()
    path = provenance_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "path": "fixture",
        "rows": int(rows),
        "raw_fingerprint": raw_fingerprint(conn) if rows else None,
        "gpkg_sha256": None,
        "gpkg_layer": None,
        "gpkg_feature_count": None,
        "clipped_dataset_version": None,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def write_national_provenance(
    conn,
    *,
    rows: int,
    gpkg_sha256: str | None = None,
    gpkg_layer: str | None = None,
    gpkg_feature_count: int | None = None,
) -> Path:
    """Fresh national receipt after a successful national insert only."""
    path = provenance_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "path": "national",
        "rows": int(rows),
        "raw_fingerprint": raw_fingerprint(conn),
        "gpkg_sha256": gpkg_sha256
        if gpkg_sha256 is not None
        else rules.GPKG_SHA256,
        "gpkg_layer": gpkg_layer if gpkg_layer is not None else rules.GPKG_LAYER,
        "gpkg_feature_count": gpkg_feature_count
        if gpkg_feature_count is not None
        else rules.GPKG_FEATURE_COUNT,
        "clipped_dataset_version": None,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def bind_clipped_receipt(receipt: dict[str, Any]) -> None:
    """Extend national provenance with the successful clipped run_layer identity."""
    path = provenance_path()
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict) or data.get("path") != "national":
        return
    data["clipped_dataset_version"] = str(receipt.get("dataset_version") or "")
    data["clipped_before"] = receipt.get("before")
    data["clipped_after"] = receipt.get("after")
    data["clipped_outside"] = receipt.get("outside")
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def read_provenance() -> dict[str, Any] | None:
    path = provenance_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _live_dataset_version(conn) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema='layers' AND table_name=%s
            )
            """,
            (LAYER_ID,),
        )
        if not cur.fetchone()[0]:
            return None
        cur.execute(
            f'SELECT DISTINCT dataset_version FROM layers."{LAYER_ID}"'
        )
        rows = cur.fetchall()
    if len(rows) != 1:
        return None
    return str(rows[0][0])


def assert_production_tile_gate(conn) -> None:
    """Refuse production carbon-peatland tiles without usable pins + bound provenance."""
    if rules.GPKG_SHA256 is None or rules.GPKG_SHA256 == "":
        raise Cpm2016TileGateError(
            f"{INGEST_PREFIX}GPKG_SHA256: expected pinned sha256, got None"
        )
    if rules.GPKG_LAYER is None or rules.GPKG_LAYER == "":
        raise Cpm2016TileGateError(
            f"{INGEST_PREFIX}GPKG_LAYER: expected pinned inner layer name, got None"
        )
    if rules.GPKG_FEATURE_COUNT is None or (
        not isinstance(rules.GPKG_FEATURE_COUNT, int)
        or rules.GPKG_FEATURE_COUNT <= 0
    ):
        raise Cpm2016TileGateError(
            f"{INGEST_PREFIX}GPKG_FEATURE_COUNT: expected pinned integer, got None"
        )

    prov = read_provenance()
    if prov is None:
        raise Cpm2016TileGateError(
            f"{TILE_PREFIX}provenance: expected national validated receipt, got absent"
        )
    path = prov.get("path")
    if path != "national":
        raise Cpm2016TileGateError(
            f"{TILE_PREFIX}provenance: expected path national, got {path}"
        )
    if (
        prov.get("gpkg_sha256") != rules.GPKG_SHA256
        or prov.get("gpkg_layer") != rules.GPKG_LAYER
        or prov.get("gpkg_feature_count") != rules.GPKG_FEATURE_COUNT
    ):
        raise Cpm2016TileGateError(
            f"{TILE_PREFIX}provenance: expected pins matching module, got mismatch"
        )

    try:
        live_fp = raw_fingerprint(conn)
    except Exception as exc:  # noqa: BLE001 — missing table = unbound
        raise Cpm2016TileGateError(
            f"{TILE_PREFIX}provenance: expected bound current ingest+clipped receipt, got stale"
        ) from exc
    if prov.get("raw_fingerprint") != live_fp:
        raise Cpm2016TileGateError(
            f"{TILE_PREFIX}provenance: expected bound current ingest+clipped receipt, got stale"
        )

    live_version = _live_dataset_version(conn)
    clipped_version = prov.get("clipped_dataset_version")
    if (
        not clipped_version
        or live_version is None
        or str(clipped_version) != str(live_version)
    ):
        raise Cpm2016TileGateError(
            f"{TILE_PREFIX}provenance: expected bound current ingest+clipped receipt, got stale"
        )
    # Layer receipt from run_layer must exist for the same dataset_version.
    receipt_file = layer_receipt_path()
    if not receipt_file.is_file():
        raise Cpm2016TileGateError(
            f"{TILE_PREFIX}provenance: expected bound current ingest+clipped receipt, got stale"
        )
    try:
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Cpm2016TileGateError(
            f"{TILE_PREFIX}provenance: expected bound current ingest+clipped receipt, got stale"
        ) from exc
    if str(receipt.get("dataset_version") or "") != str(live_version):
        raise Cpm2016TileGateError(
            f"{TILE_PREFIX}provenance: expected bound current ingest+clipped receipt, got stale"
        )


def assert_fixture_output_confined(tiles_dir: Path) -> None:
    """Fixture mode may not write to / publish via the production tiles root."""
    prod = production_tiles_root()
    if prod is None:
        return
    resolved = tiles_dir.resolve()
    prod_resolved = prod.resolve()
    if resolved == prod_resolved or str(resolved).startswith(
        str(prod_resolved) + os.sep
    ):
        raise Cpm2016TileGateError(
            f"{TILE_PREFIX}fixture mode: production tiles root or publisher forbidden"
        )
