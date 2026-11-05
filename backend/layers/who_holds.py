"""M5 Who holds Scotland — council-level community ownership (charter Q4).

Reads a hash-pinned extract of official Scottish Government Community
Ownership in Scotland 2024 figures (codes, counts and hectares only).
Never reads asset names, group names or postcodes. Never emits data
below council level. No spatial join.

Privacy (charter v2 §4 rules 6 and 6a, quoted verbatim in the spec):
no natural person's name; no data below the official publication level;
no owner named. This module refuses any extract that carries a name or
postcode column.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any, Mapping

from spatial.council_names import OFFICIAL_COUNCIL_NAMES, official_council_name

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRACT_DIR = REPO_ROOT / "data" / "processed" / "gis"
EXTRACT_NAME = "community_ownership_councils_2024.csv"
EXTRACT_PATH = EXTRACT_DIR / EXTRACT_NAME

PUBLISHED_ASSET_COUNT = 853
PUBLISHED_HECTARES = 213803
VINTAGE = "2024"
LAYER_ID = "who_holds"
LEVEL = "council"

ALLOWED_FIELDS = ("la_s_code", "asset_count", "area_ha")
NAME_FIELDS = frozenset(
    {
        "group_name",
        "asset_name",
        "owner",
        "owner_name",
        "individual",
        "person",
        "postcode",
        "name",
        "contact",
        "address",
    }
)

PUBLICATION_URL = (
    "https://www.gov.scot/publications/community-ownership-in-scotland-2024/"
)
DOCUMENTS_URL = (
    "https://www.gov.scot/publications/community-ownership-in-scotland-2024/documents/"
)
LICENCE = "Open Government Licence v3.0"
CREDIT = (
    "Community Ownership in Scotland 2024. Contains public sector information "
    "licensed under the Open Government Licence v3.0. Scottish Government."
)

# Fill colours match frontend whoHoldsCividisColors(): LAND_WORTH_CIVIDIS
# indices 9, 6, 3, 0 (lightest to darkest). Display uses the frontend ramp.
BANDS: tuple[tuple[str, float | None, str, str], ...] = (
    ("ha_under_10", 10.0, "Under 10 hectares", "#fee838"),
    ("ha_10_to_100", 100.0, "10 to 100 hectares", "#a59c74"),
    ("ha_100_to_1000", 1000.0, "100 to 1,000 hectares", "#575d6d"),
    ("ha_1000_plus", None, "1,000 hectares or more", "#00224e"),
)
BAND_IDS = tuple(b[0] for b in BANDS)


class WhoHoldsError(Exception):
    """Refusal with an exact ``WHO-HOLDS: `` message."""


def _fail(reason: str) -> None:
    raise WhoHoldsError(f"WHO-HOLDS: {reason}")


def band_for_hectares(area_ha: float) -> str:
    for band_id, upper, _label, _color in BANDS:
        if upper is None or area_ha < upper:
            return band_id
    return "ha_1000_plus"


def _sha_path_for(extract: Path) -> Path:
    sibling = extract.parent / "SHA256_who_holds.txt"
    if sibling.is_file():
        return sibling
    return extract.parent / "SHA256.txt"


def _expected_sha256(extract: Path) -> str:
    sha_path = _sha_path_for(extract)
    if not sha_path.is_file():
        _fail("extract file is missing")
    first = sha_path.read_text(encoding="utf-8").splitlines()[0].strip()
    digest = first.split()[0] if first else ""
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        _fail("extract file is missing")
    return digest


def _read_extract(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        _fail("extract file is missing")
    raw = path.read_bytes()
    if not raw.strip():
        _fail("extract file is empty")
    expected = _expected_sha256(path)
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        _fail("extract checksum does not match")
    text = raw.decode("utf-8")
    reader = csv.DictReader(text.splitlines())
    fields = tuple(reader.fieldnames or [])
    if not fields:
        _fail("extract file is empty")
    lowered = {f.strip().lower() for f in fields}
    if lowered & NAME_FIELDS:
        _fail("extract must not contain owner names")
    for col in ALLOWED_FIELDS:
        if col not in fields:
            _fail(f"missing field '{col}'")
    extra = [f for f in fields if f not in ALLOWED_FIELDS]
    if extra:
        _fail(f"unexpected field '{extra[0]}'")
    return [dict(row) for row in reader]


def _parse_row(row: Mapping[str, str], seen: set[str]) -> dict[str, Any]:
    code = (row.get("la_s_code") or "").strip()
    if not code:
        _fail("blank field la_s_code")
    if code not in OFFICIAL_COUNCIL_NAMES:
        _fail(f"{code}: not an official council")
    if code in seen:
        _fail(f"{code}: listed twice")
    seen.add(code)
    count_raw = row.get("asset_count")
    if count_raw is None or not str(count_raw).strip():
        _fail(f"{code}: blank field asset_count")
    ha_raw = row.get("area_ha")
    if ha_raw is None or not str(ha_raw).strip():
        _fail(f"{code}: blank field area_ha")
    try:
        count = int(str(count_raw).strip())
    except ValueError:
        _fail(f"{code}: asset_count must be a whole number")
    if str(count) != str(count_raw).strip():
        _fail(f"{code}: asset_count must be a whole number")
    if count < 0:
        _fail(f"{code}: asset_count must not be negative")
    try:
        area_ha = float(str(ha_raw).strip())
    except ValueError:
        _fail(f"{code}: area_ha must be a number")
    if area_ha < 0:
        _fail(f"{code}: area_ha must not be negative")
    name = official_council_name(code)
    if not name:
        _fail(f"{code}: not an official council")
    return {
        "code": code,
        "name": name,
        "asset_count": count,
        "area_ha": area_ha,
        "band": band_for_hectares(area_ha),
    }


def load_councils(path: Path | None = None) -> list[dict[str, Any]]:
    rows = _read_extract(path or EXTRACT_PATH)
    if not rows:
        _fail("extract file is empty")
    seen: set[str] = set()
    councils = [_parse_row(row, seen) for row in rows]
    missing = sorted(set(OFFICIAL_COUNCIL_NAMES) - seen)
    if missing:
        _fail("extract must cover all 32 councils")
    if len(councils) != 32:
        _fail("extract must cover all 32 councils")
    total_n = sum(c["asset_count"] for c in councils)
    if total_n != PUBLISHED_ASSET_COUNT:
        _fail("asset count must equal 853")
    total_ha = sum(c["area_ha"] for c in councils)
    if round(total_ha) != PUBLISHED_HECTARES:
        _fail("hectare total must equal 213803")
    councils.sort(key=lambda c: c["code"])
    return councils


def public_payload(path: Path | None = None) -> dict[str, Any]:
    councils = load_councils(path)
    payload = {
        "layer_id": LAYER_ID,
        "level": LEVEL,
        "vintage": VINTAGE,
        "source": {
            "attribution": CREDIT,
            "credit": CREDIT,
            "licence": LICENCE,
            "publication_url": PUBLICATION_URL,
            "dataset_url": DOCUMENTS_URL,
        },
        "totals": {
            "asset_count": PUBLISHED_ASSET_COUNT,
            "area_ha": round(sum(c["area_ha"] for c in councils), 4),
        },
        "bands": [
            {"id": b[0], "label": b[2], "color": b[3]} for b in BANDS
        ],
        "councils": councils,
    }
    dumped = str(payload).lower()
    if "\u00a3" in dumped or "gbp" in dumped:
        _fail("payload must not contain a pound sign")
    for row in councils:
        for key in NAME_FIELDS:
            if key in row and key != "name":
                _fail("extract must not contain owner names")
    return payload
