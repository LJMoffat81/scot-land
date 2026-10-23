"""Build simplified Scottish council boundary GeoJSON for point-in-polygon lookup.

Uses OS Boundary-Line ``district_borough_unitary`` filtered to Census_Code S12%
(same release pin as SRC-A Scotland extent).

Run from backend:
    python -m etl.build_boundaries
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import yaml
from shapely.geometry import mapping, shape
from shapely.ops import transform

from spatial.council_names import OFFICIAL_COUNCIL_NAMES, official_council_name

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
CACHE_DIR = REPO_ROOT / "data" / "cache"
OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "scotland_councils.geojson"
EXPECTED_COUNCILS = 32
OS_BOUNDARY_SHA256 = (
    "151b027b621ac4cdac3f7a6635cd26dd65fb3b5bf1cb8eb392cc00e1687e3bd4"
)


class CouncilsError(Exception):
    """Raised when council boundary ingest fails a hard pin."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cfg() -> dict:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        sources = yaml.safe_load(handle)
    return dict(sources["boundaries"]["councils"])


def _download_bdline(client: httpx.Client, url: str, expected_sha: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / "os_boundary_line_bdline_gb.zip"
    if cache_path.is_file() and _sha256_file(cache_path) == expected_sha:
        return cache_path
    response = client.get(url, timeout=300.0, follow_redirects=True)
    response.raise_for_status()
    cache_path.write_bytes(response.content)
    actual = _sha256_file(cache_path)
    if actual != expected_sha:
        cache_path.unlink(missing_ok=True)
        raise CouncilsError(
            f"councils: Boundary-Line sha256 mismatch: got {actual}"
        )
    return cache_path


def _load_s12_features(bdline_zip: Path) -> list[dict]:
    # Fiona is build-only; keep import lazy so light tests need not install it.
    import fiona
    from pyproj import Transformer

    path = f"/vsizip/{bdline_zip.as_posix()}/Data/bdline_gb.gpkg"
    to_wgs84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    features: list[dict] = []
    with fiona.open(path, layer="district_borough_unitary") as src:
        for feature in src:
            props = dict(feature["properties"] or {})
            code = str(props.get("Census_Code") or "")
            if not code.startswith("S12"):
                continue
            name_raw = props.get("Name") or props.get("name") or ""
            name = official_council_name(code, name_raw) or name_raw
            geom_27700 = shape(feature["geometry"])
            geom_4326 = transform(to_wgs84.transform, geom_27700)
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "hpi_code": code,
                        "boundary_code": code,
                        "name": name,
                    },
                    "geometry": geom_4326,
                }
            )
    return features


def assert_council_count(n: int, expected: int = EXPECTED_COUNCILS) -> None:
    if n != expected:
        raise CouncilsError(
            f"councils: expected {expected} Scottish councils, got {n}"
        )


def build_boundaries(
    *,
    bdline_zip: Path | None = None,
    client: httpx.Client | None = None,
) -> dict:
    cfg = _cfg()
    expected_sha = str(cfg.get("sha256") or OS_BOUNDARY_SHA256)
    if expected_sha != OS_BOUNDARY_SHA256:
        raise CouncilsError(
            f"councils: Boundary-Line sha must be {OS_BOUNDARY_SHA256}"
        )
    simplify_tolerance = float(cfg["simplify_tolerance_degrees"])

    owns_client = client is None
    http = client or httpx.Client()
    try:
        zip_path = bdline_zip or _download_bdline(
            http, cfg["source_url"], expected_sha
        )
        if _sha256_file(zip_path) != expected_sha:
            raise CouncilsError("councils: Boundary-Line sha256 mismatch")
        raw_features = _load_s12_features(zip_path)
    finally:
        if owns_client:
            http.close()

    assert_council_count(len(raw_features))
    codes = {f["properties"]["hpi_code"] for f in raw_features}
    if codes != set(OFFICIAL_COUNCIL_NAMES):
        raise CouncilsError(
            "councils: Census_Code set does not match the official 32 S12 codes"
        )

    features: list[dict] = []
    for feature in raw_features:
        geometry = feature["geometry"].simplify(
            simplify_tolerance, preserve_topology=True
        )
        features.append(
            {
                "type": "Feature",
                "properties": dict(feature["properties"]),
                "geometry": mapping(geometry),
            }
        )

    features.sort(key=lambda item: item["properties"]["name"])
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    geojson = build_boundaries()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(geojson), encoding="utf-8")
    print(f"Wrote {len(geojson['features'])} council boundaries to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
