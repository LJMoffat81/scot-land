"""M2 Idle land — council extract, privacy refusals, exact messages."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from layers.idle_land import (
    BANDS,
    EXTRACT_PATH,
    PUBLISHED_SITE_COUNT,
    PUBLISHED_HECTARES,
    IdleLandError,
    load_councils,
    public_payload,
)
from spatial.council_names import OFFICIAL_COUNCIL_NAMES

PREFIX = "IDLE-LAND: "


def _write(tmp: Path, rows: list[str], name: str = "idle_land_councils_2025.csv") -> Path:
    path = tmp / name
    path.write_text("la_s_code,site_count,area_ha,return_year\n" + "".join(rows), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp / "SHA256.txt").write_text(f"{digest}  {name}\n", encoding="utf-8")
    return path


def test_official_extract_matches_publication_totals():
    councils = load_councils(EXTRACT_PATH)
    assert len(councils) == 32
    assert {c["code"] for c in councils} == set(OFFICIAL_COUNCIL_NAMES)
    assert sum(c["site_count"] for c in councils) == PUBLISHED_SITE_COUNT
    assert round(sum(c["area_ha"] for c in councils)) == PUBLISHED_HECTARES
    payload = public_payload(EXTRACT_PATH)
    assert payload["layer_id"] == "idle_land"
    assert payload["level"] == "council"
    assert payload["vintage"] == "2025"
    assert payload["totals"]["site_count"] == 2995
    assert round(payload["totals"]["area_ha"]) == 8587
    assert [b["id"] for b in payload["bands"]] == [b[0] for b in BANDS]
    blob = str(payload).lower()
    assert "\u00a3" not in blob and "gbp" not in blob
    for row in payload["councils"]:
        assert set(row) == {"code", "name", "site_count", "area_ha", "band", "return_year"}
        assert "group_name" not in row
        assert "asset_name" not in row
        assert "postcode" not in row
        assert row["name"] == OFFICIAL_COUNCIL_NAMES[row["code"]]


def test_public_payload_uses_official_council_names_only():
    payload = public_payload(EXTRACT_PATH)
    names = {row["name"] for row in payload["councils"]}
    assert names == set(OFFICIAL_COUNCIL_NAMES.values())


def _copy_official(tmp: Path) -> Path:
    text = EXTRACT_PATH.read_text(encoding="utf-8")
    path = tmp / EXTRACT_PATH.name
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp / "SHA256.txt").write_text(f"{digest}  {EXTRACT_PATH.name}\n", encoding="utf-8")
    return path


def _raises(path: Path, reason: str) -> None:
    with pytest.raises(IdleLandError, match=f"^{PREFIX}{reason}$") as exc:
        load_councils(path)
    assert str(exc.value) == f"{PREFIX}{reason}"


def test_missing_file(tmp_path: Path):
    _raises(tmp_path / "nope.csv", "extract file is missing")


def test_empty_file(tmp_path: Path):
    path = tmp_path / "idle_land_councils_2025.csv"
    path.write_bytes(b"")
    (tmp_path / "SHA256.txt").write_text(
        f"{hashlib.sha256(b'').hexdigest()}  idle_land_councils_2025.csv\n",
        encoding="utf-8",
    )
    _raises(path, "extract file is empty")


def test_empty_rows_only_header(tmp_path: Path):
    path = _write(tmp_path, [])
    _raises(path, "extract file is empty")


def test_name_column_refused(tmp_path: Path):
    path = tmp_path / "idle_land_councils_2025.csv"
    path.write_text(
        "la_s_code,site_count,area_ha,return_year,group_name\nS12000005,3,12.0557,2024,Trust\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "extract must not contain owner names")


def test_postcode_column_refused(tmp_path: Path):
    path = tmp_path / "idle_land_councils_2025.csv"
    path.write_text(
        "la_s_code,site_count,area_ha,return_year,postcode\nS12000005,3,12.0557,2024,TD11 3AF\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "extract must not contain owner names")


def test_unexpected_field(tmp_path: Path):
    path = tmp_path / "idle_land_councils_2025.csv"
    path.write_text(
        "la_s_code,site_count,area_ha,return_year,note\nS12000005,3,12.0557,2024,x\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "unexpected field 'note'")


def test_missing_field(tmp_path: Path):
    path = tmp_path / "idle_land_councils_2025.csv"
    path.write_text("la_s_code,site_count\nS12000005,3\n", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "missing field 'area_ha'")


def test_blank_code(tmp_path: Path):
    path = _copy_official(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines(True)
    lines[1] = ",3,12.0557,2024\n"
    path.write_text("".join(lines), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "blank field la_s_code")


def test_blank_count(tmp_path: Path):
    path = _copy_official(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines(True)
    # first data row is S12000005
    lines[1] = "S12000005,,12.0557,2024\n"
    path.write_text("".join(lines), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "S12000005: blank field site_count")


def test_unknown_council(tmp_path: Path):
    path = _copy_official(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines(True)
    lines[1] = "S12999999,3,12.0557,2024\n"
    path.write_text("".join(lines), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "S12999999: not an official council")


def test_duplicate_council(tmp_path: Path):
    path = _copy_official(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines(True)
    lines[2] = lines[1]
    path.write_text("".join(lines), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "S12000005: listed twice")


def test_wrong_site_total(tmp_path: Path):
    path = _copy_official(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines(True)
    lines[1] = "S12000005,4,12.0557,2024\n"
    path.write_text("".join(lines), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "site count must equal 2995")


def test_wrong_hectare_total(tmp_path: Path):
    path = _copy_official(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines(True)
    lines[1] = "S12000005,18,100.0000,2024\n"
    path.write_text("".join(lines), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "hectare total must equal 8587")


def test_negative_count(tmp_path: Path):
    path = _copy_official(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines(True)
    lines[1] = "S12000005,-1,12.0557,2024\n"
    path.write_text("".join(lines), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "S12000005: site_count must not be negative")


def test_checksum_mismatch(tmp_path: Path):
    path = _copy_official(tmp_path)
    (tmp_path / "SHA256.txt").write_text("0" * 64 + "  idle_land_councils_2025.csv\n")
    _raises(path, "extract checksum does not match")


def test_blank_area(tmp_path: Path):
    path = _copy_official(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines(True)
    lines[1] = "S12000005,3,,2024\n"
    path.write_text("".join(lines), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "S12000005: blank field area_ha")


def test_non_numeric_count(tmp_path: Path):
    path = _copy_official(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines(True)
    lines[1] = "S12000005,three,12.0557,2024\n"
    path.write_text("".join(lines), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "S12000005: site_count must be a whole number")


def test_non_numeric_area(tmp_path: Path):
    path = _copy_official(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines(True)
    lines[1] = "S12000005,3,twelve,2024\n"
    path.write_text("".join(lines), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "S12000005: area_ha must be a number")


def test_negative_area(tmp_path: Path):
    path = _copy_official(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines(True)
    lines[1] = "S12000005,3,-1,2024\n"
    path.write_text("".join(lines), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "S12000005: area_ha must not be negative")


def test_missing_checksum_file(tmp_path: Path):
    path = tmp_path / "idle_land_councils_2025.csv"
    path.write_text(
        "la_s_code,site_count,area_ha,return_year\nS12000005,3,12.0557,2024\n",
        encoding="utf-8",
    )
    _raises(path, "extract file is missing")


def test_incomplete_councils(tmp_path: Path):
    path = _copy_official(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines(True)
    path.write_text("".join(lines[:-1]), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "extract must cover all 32 councils")


def test_official_name_lookup_fails(tmp_path: Path, monkeypatch):
    path = _copy_official(tmp_path)
    monkeypatch.setattr("layers.idle_land.official_council_name", lambda _code: None)
    _raises(path, "S12000005: not an official council")



def test_unpublished_return_year(tmp_path: Path):
    path = _copy_official(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines(True)
    lines[1] = "S12000005,3,12.0557,2019\n"
    path.write_text("".join(lines), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "SHA256.txt").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    _raises(path, "S12000005: return_year must be a published survey year")


def test_publication_rule_declared():
    from georgist.publication_rules import PUBLIC_ROUTE_RULES

    rule = PUBLIC_ROUTE_RULES["/platform/idle-land"]
    assert rule.value_basis == "none"
    assert rule.geometry_level == "zone"
    assert rule.source_granularity == "zone"


def test_payload_has_no_point_assets():
    payload = public_payload(EXTRACT_PATH)
    assert "assets" not in payload
    assert payload["level"] == "council"


def test_platform_idle_land_ok(client):
    r = client.get("/platform/idle-land")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["layer_id"] == "idle_land"
    assert body["level"] == "council"
    assert body["totals"]["site_count"] == 2995
    assert len(body["councils"]) == 32
    assert "\u00a3" not in r.text.lower()
    assert "gbp" not in r.text.lower()


def test_platform_idle_land_503_when_missing(client, monkeypatch):
    from layers.idle_land import IdleLandError

    def _boom():
        raise IdleLandError("IDLE-LAND: extract file is missing")

    monkeypatch.setattr("api.platform_routes.idle_land_payload", _boom)
    r = client.get("/platform/idle-land")
    assert r.status_code == 503, r.text
    assert r.json()["detail"] == "IDLE-LAND: extract file is missing"
    assert "features" not in r.json()
