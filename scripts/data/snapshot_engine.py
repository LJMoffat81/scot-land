"""Write the current /square and /postcode JSON for the engine-layers freeze.

Run from the repo before any layer-stamp change. Figures are whatever origin/main
returns, including a cadastral area when the parcel service answers.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# A developer key would put words into the snapshot that CI cannot repeat.
os.environ.pop("W3W_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402

HANDOFF_CSV = (
    REPO.parent / "scot-land-handoff" / "fixtures" / "qa-live-snapshot" / "figures.csv"
)
SQUARE_PATH = BACKEND / "tests" / "fixtures" / "engine_snapshot_main.json"
POSTCODE_PATH = BACKEND / "tests" / "fixtures" / "postcode_snapshot_main.json"

FIXED_POINTS = (
    ("glasgow", 55.8642, -4.2518),
    ("wick", 58.4390, -3.0930),
    ("cairngorms", 57.08, -3.65),
    ("aberdeenshire", 57.35, -2.40),
)
POSTCODES = (
    "AB10 1AQ",
    "DG1 2BD",
    "EH1 1YZ",
    "G1 1BL",
    "G2 1DY",
    "HS1 2BG",
    "IV1 1JJ",
    "KW1 4AA",
    "TD14 5AA",
    "ZE1 0LL",
)
PER_SQM_FIELDS = {"site_capital_market_per_sqm_gbp"}


def _client() -> TestClient:
    return TestClient(app)


def _square(client: TestClient, lat: float, lng: float) -> dict:
    response = client.get(
        "/square",
        params={"lat": lat, "lng": lng, "scenario": "full_agr"},
    )
    if response.status_code != 200:
        raise SystemExit(f"/square {lat},{lng} failed: {response.status_code} {response.text}")
    return response.json()


def _postcode(client: TestClient, postcode: str) -> dict:
    response = client.get(f"/postcode/{postcode}", params={"scenario": "full_agr"})
    if response.status_code != 200:
        raise SystemExit(
            f"/postcode {postcode} failed: {response.status_code} {response.text}"
        )
    return response.json()


def _drop_outlines(body: dict) -> None:
    # The parcel polygon is an RoS title outline. Keep the agr figures, not the outline.
    body.pop("parcel", None)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_snapshots() -> tuple[dict, dict]:
    councils = json.loads((REPO / "data" / "processed" / "councils.json").read_text(encoding="utf-8"))
    client = _client()
    points = []
    for council in councils["councils"]:
        lat = float(council["centroid"]["lat"])
        lng = float(council["centroid"]["lng"])
        points.append(
            {
                "kind": "council",
                "code": council["code"],
                "name": council["name"],
                "lat": lat,
                "lng": lng,
                "response": _square(client, lat, lng),
            }
        )
    for name, lat, lng in FIXED_POINTS:
        points.append(
            {
                "kind": "fixed",
                "name": name,
                "lat": lat,
                "lng": lng,
                "response": _square(client, lat, lng),
            }
        )
    for point in points:
        _drop_outlines(point["response"])
    postcodes = {postcode: _postcode(client, postcode) for postcode in POSTCODES}
    for body in postcodes.values():
        _drop_outlines(body)
    square_payload = {"scenario": "full_agr", "points": points}
    postcode_payload = {"scenario": "full_agr", "postcodes": postcodes}
    _write(SQUARE_PATH, square_payload)
    _write(POSTCODE_PATH, postcode_payload)
    return square_payload, postcode_payload


def _blank(cell: str | None) -> bool:
    return cell is None or str(cell).strip() == ""


def _same(field: str, live: str, ours) -> tuple[bool, str]:
    if _blank(live):
        if ours is None:
            return True, "absent"
        return False, f"live blank, ours {ours!r}"
    if ours is None:
        return False, f"live {live}, ours absent"
    if field in PER_SQM_FIELDS:
        ok = round(float(ours), 4) == round(float(live), 4)
    else:
        ok = round(float(ours), 2) == round(float(live), 2)
    return ok, f"live {live}, ours {ours}"


def compare_qa_csv(postcode_payload: dict, csv_path: Path = HANDOFF_CSV) -> list[str]:
    """Return a line for each postcode field that disagrees with QA's live snapshot."""
    if not csv_path.exists():
        raise SystemExit(f"Missing QA snapshot {csv_path}")
    problems: list[str] = []
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(row for row in handle if not row.startswith("#")))
    by_compact = {
        postcode.replace(" ", "").upper(): body
        for postcode, body in postcode_payload["postcodes"].items()
    }
    for row in rows:
        compact = row["postcode"].replace(" ", "").upper()
        body = by_compact.get(compact)
        if body is None:
            problems.append(f"{compact}: missing from snapshot")
            continue
        agr = body.get("agr") or {}
        for field, live in row.items():
            if field == "postcode":
                continue
            ok, detail = _same(field, live, agr.get(field))
            if not ok:
                problems.append(f"{compact} {field}: {detail}")
    return problems


def main() -> None:
    _, postcodes = build_snapshots()
    problems = compare_qa_csv(postcodes)
    print(f"Wrote {SQUARE_PATH}")
    print(f"Wrote {POSTCODE_PATH}")
    if problems:
        print("QA live snapshot differs:")
        for line in problems:
            print(f"  {line}")
        raise SystemExit(1)
    print("QA live snapshot matches all 10 postcodes to the penny.")


if __name__ == "__main__":
    main()
