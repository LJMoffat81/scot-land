"""STEP8-DZ2011-KEYING: 2024 rent-route join keyed on the pinned DZ2011 key set.

Synthetic fixtures only (plus the committed public OGL code list). No scoring step runs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from georgist.surface_v14_checks import check_6_zone_range
from scripts import build_v14_check_inputs as b
from scripts.build_v14_check_inputs import CheckInputError, build_v14_check_inputs, dz2011_restrict, load_dz2011_keys

KEYS = ["S01000001", "S01000002", "S01000003", "S01000004"]
BUILDER = ["S01000001", "S01000003"]


def _tables(builder=BUILDER, ur6=KEYS) -> dict:
    zones = list(builder)
    return {
        "builder_output": {z: {"price": 1.0, "count_in_1d": 5, "unavailable": False, "model_failure": False, "hla": 1} for z in zones},
        "primary_estimates": {z: {"share": 0.3, "land_per_home": 2.0} for z in zones},
        "fitted_hedonic": {z: {"share": 0.31, "land_per_home": 2.1} for z in zones},
        "check3_plot_passes": {z: {"pass_at": 30} for z in zones},
        "check4_rent_route": {z: {"residual_land": 4.0, "capitalised_land": 4.0} for z in zones},
        "dz2022_keys": {z: {"dz2022": "S01" + z[3:].replace("0", "1", 1), "share_low": 0.2, "share_central": 0.3, "share_high": 0.4} for z in zones},
        "ur6": {z: {"ur6": 1} for z in ur6},
    }


def _refuse(msg: str, **kw) -> None:
    with pytest.raises(CheckInputError) as exc:
        build_v14_check_inputs(**kw)
    assert str(exc.value) == msg


# ---- join -----------------------------------------------------------------

def test_keyed_2024_join_restricts_ur6_and_keeps_dz2022() -> None:
    built = build_v14_check_inputs(_tables(), {"dz2011_keys": b.DZ2011_KEYS_SHA256}, mode=2024, dz2011_keys=KEYS)
    assert [z["zone"] for z in built["primary_zones"]] == BUILDER
    assert [z["zone"] for z in built["secondary_zones"]] == BUILDER
    assert built["dz2011_keys_sha256"] == b.DZ2011_KEYS_SHA256
    assert built["pins"] == {"dz2011_keys": b.DZ2011_KEYS_SHA256}
    for zone in built["primary_zones"]:
        assert zone["year"] == 2024 and zone["dz2022"] and zone["ur6"] == 1
    assert check_6_zone_range(built["primary_zones"])["pass"] is True


def test_restrict_returns_builder_only_ur6_without_mutating_input() -> None:
    tables = _tables()
    out = dz2011_restrict(tables, set(KEYS))
    assert sorted(out["ur6"]) == BUILDER
    assert sorted(tables["ur6"]) == KEYS


@pytest.mark.parametrize(
    "bad, shown",
    [("S01999999", "'S01999999'"), ("", "''"), ("S0100", "'S0100'"), (" S01000001", "' S01000001'")],
)
def test_builder_zone_not_a_key_refuses(bad: str, shown: str) -> None:
    _refuse(
        f"V14_CHECK_INPUTS: REFUSED: builder_output zone {shown}: expected DZ2011 key, got other",
        tables=_tables(builder=["S01000001", bad]), mode=2024, dz2011_keys=KEYS,
    )


@pytest.mark.parametrize(
    "ur6",
    [KEYS[:-1], [*KEYS, "S01999999"], ["S01000002", "S01000003", "S01000004"], [*KEYS[:-1], ""]],
    ids=["drop-non-builder", "extra-unknown", "drop-builder", "blank-instead"],
)
def test_ur6_not_exactly_the_key_set_refuses(ur6: list[str]) -> None:
    _refuse(
        "V14_CHECK_INPUTS: REFUSED: ur6 zones: expected the DZ2011 key set, got mismatch",
        tables=_tables(ur6=ur6), mode=2024, dz2011_keys=KEYS,
    )


@pytest.mark.parametrize("mode", [2023, None])
def test_keys_off_2024_refuse(mode) -> None:
    _refuse("V14_CHECK_INPUTS: ERROR: dz2011_keys: expected 2024 rent route, got other",
            tables=_tables(), mode=mode, dz2011_keys=KEYS)


def test_keys_on_f8_route_refuse() -> None:
    tables = _tables()
    tables["check4_f8"] = tables.pop("check4_rent_route")
    _refuse("V14_CHECK_INPUTS: ERROR: dz2011_keys: expected 2024 rent route, got other",
            tables=tables, mode=2024, dz2011_keys=KEYS)


def test_keys_with_status_s_refuse() -> None:
    _refuse("V14_CHECK_INPUTS: ERROR: dz2011_keys: expected 2024 rent route, got other",
            tables=_tables(), mode=2024, status_s={z: "estimated" for z in BUILDER}, dz2011_keys=KEYS)


def test_dz2022_guard_unchanged_on_keyed_path() -> None:
    tables = _tables()
    tables["dz2022_keys"].pop("S01000003")
    _refuse("dz2022_keys zones do not match the builder output", tables=tables, mode=2024, dz2011_keys=KEYS)
    tables = _tables()
    del tables["dz2022_keys"]["S01000003"]["share_high"]
    _refuse("missing fields: primary S01000003: share_high; secondary S01000003: share_high",
            tables=tables, mode=2024, dz2011_keys=KEYS)


def test_check6_still_requires_dz2022() -> None:
    with pytest.raises(ValueError, match="^check 6 requires dz2022$"):
        check_6_zone_range([{"zone": "S01000001", "share_low": 0.1, "share_central": 0.2, "share_high": 0.3}])


def test_legacy_path_without_keys_unchanged() -> None:
    _refuse("ur6 zones do not match the builder output", tables=_tables(), mode=2024)
    built = build_v14_check_inputs(_tables(ur6=BUILDER), mode=2024)
    assert "dz2011_keys_sha256" not in built and [z["zone"] for z in built["primary_zones"]] == BUILDER


# ---- key file ---------------------------------------------------------------

def test_committed_key_file_pinned_and_shaped() -> None:
    raw = b.DZ2011_KEYS_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == b.DZ2011_KEYS_SHA256 == (
        "2611c9e701d9affef34680be2a0d9bbc14468ddbc5241f353819f9ee59849874"
    )
    keys = load_dz2011_keys()
    assert len(keys) == b.DZ2011_KEY_COUNT == 6976
    assert keys[0] == "S01006506" and keys[-1] == "S01013481"


def test_missing_key_file_refuses(tmp_path: Path) -> None:
    gone = tmp_path / "absent.json"
    with pytest.raises(CheckInputError) as exc:
        load_dz2011_keys(gone)
    assert str(exc.value) == f"B6: ERROR: file: expected {gone}, got absent"


def test_tampered_key_file_refuses_on_sha(tmp_path: Path) -> None:
    bad = tmp_path / "k.json"
    bad.write_bytes(b.DZ2011_KEYS_PATH.read_bytes() + b"\n")
    got = hashlib.sha256(bad.read_bytes()).hexdigest()
    with pytest.raises(CheckInputError) as exc:
        load_dz2011_keys(bad)
    assert str(exc.value) == (
        f"V14_CHECK_INPUTS: REFUSED: dz2011_keys sha256: expected {b.DZ2011_KEYS_SHA256}, got {got}"
    )


def _real_keys() -> list[str]:
    return json.loads(b.DZ2011_KEYS_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda k: k[:-1],
        lambda k: list(reversed(k)),
        lambda k: [k[0], *k[:-1]],
        lambda k: ["", *k[1:]],
        lambda k: ["S0100", *k[1:]],
        lambda k: [" S0100650", *k[1:]],
        lambda k: [1, *k[1:]],
        lambda k: {"keys": k},
        lambda k: 5,
    ],
    ids=["short", "unsorted", "duplicate", "blank", "short-code", "padded", "non-str", "not-list", "scalar"],
)
def test_key_file_shape_refused_even_when_sha_matches(tmp_path, monkeypatch, mutate) -> None:
    bad = tmp_path / "k.json"
    bad.write_text(json.dumps(mutate(_real_keys())), encoding="utf-8")
    monkeypatch.setattr(b, "DZ2011_KEYS_SHA256", hashlib.sha256(bad.read_bytes()).hexdigest())
    with pytest.raises(CheckInputError) as exc:
        load_dz2011_keys(bad)
    assert str(exc.value) == "V14_CHECK_INPUTS: REFUSED: dz2011_keys: expected 6976 sorted unique codes, got other"


# ---- CLI (refuses before any source is read or joined) ----------------------

def _cli(tmp_path, capsys, monkeypatch, extra: list[str]) -> str:
    calls = []
    monkeypatch.setattr(b, "join_sources", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(b, "read_s2_s3", lambda *a, **k: calls.append(1))
    rc = b.main(["--out", str(tmp_path / "o.json"), *extra])
    assert rc == 1 and calls == [] and not (tmp_path / "o.json").exists()
    return capsys.readouterr().err


GOOD_PIN = f"dz2011_keys={'2611c9e701d9affef34680be2a0d9bbc14468ddbc5241f353819f9ee59849874'}"


def test_cli_keys_on_2023_refuse(tmp_path, capsys, monkeypatch) -> None:
    err = _cli(tmp_path, capsys, monkeypatch, ["--year", "2023", "--dz2011-keys", str(b.DZ2011_KEYS_PATH), "--pin", GOOD_PIN])
    assert err == "V14_CHECK_INPUTS: ERROR: dz2011_keys: expected 2024 rent route, got other\n"


def test_cli_keys_with_f8_refuse(tmp_path, capsys, monkeypatch) -> None:
    f8 = tmp_path / "f8.json"
    f8.write_text("{}")
    err = _cli(tmp_path, capsys, monkeypatch,
               ["--year", "2024", "--check4-f8", str(f8), "--dz2011-keys", str(b.DZ2011_KEYS_PATH), "--pin", GOOD_PIN])
    assert err == "V14_CHECK_INPUTS: ERROR: dz2011_keys: expected 2024 rent route, got other\n"


def test_cli_keys_without_pin_refuse(tmp_path, capsys, monkeypatch) -> None:
    err = _cli(tmp_path, capsys, monkeypatch, ["--year", "2024", "--dz2011-keys", str(b.DZ2011_KEYS_PATH)])
    assert err == "inputs without a pinned sha: dz2011_keys\n"


def test_cli_keys_wrong_pin_refuse(tmp_path, capsys, monkeypatch) -> None:
    err = _cli(tmp_path, capsys, monkeypatch,
               ["--year", "2024", "--dz2011-keys", str(b.DZ2011_KEYS_PATH), "--pin", "dz2011_keys=" + "0" * 64])
    assert err == f"dz2011_keys pin {'0' * 64} != {b.DZ2011_KEYS_SHA256}\n"


def test_cli_keys_missing_file_refuse(tmp_path, capsys, monkeypatch) -> None:
    gone = tmp_path / "none.json"
    err = _cli(tmp_path, capsys, monkeypatch, ["--year", "2024", "--dz2011-keys", str(gone), "--pin", GOOD_PIN])
    assert err == f"B6: ERROR: file: expected {gone}, got absent\n"


def test_cli_keyed_2024_end_to_end_join(tmp_path, capsys, monkeypatch) -> None:
    """Positive CLI path: sources stubbed (synthetic), the real join runs with the committed keys."""
    keys = _real_keys()
    builder = keys[:2]
    monkeypatch.setattr(b, "assert_pinned", lambda *a, **k: None)
    monkeypatch.setattr(b, "read_s2_s3", lambda *a, **k: _tables(builder=builder, ur6=keys))
    monkeypatch.setattr(b, "assert_frozen_coefficients", lambda *a, **k: {})
    monkeypatch.setattr(b, "apply_2024_coefficients", lambda *a, **k: None)
    out = tmp_path / "o.json"
    flags: list[str] = []
    for name in b.SOURCES:
        stub = tmp_path / f"{name}.json"
        stub.write_text("{}")
        flags += [f"--{name.replace('_', '-')}", str(stub)]
    rc = b.main(["--out", str(out), "--year", "2024", "--hedonic-coefs", "h", "--lock", "l", *flags,
                 "--dz2011-keys", str(b.DZ2011_KEYS_PATH), "--pin", GOOD_PIN])
    assert rc == 0, capsys.readouterr().err
    built = json.loads(out.read_text())
    assert built["dz2011_keys_sha256"] == b.DZ2011_KEYS_SHA256
    assert [z["zone"] for z in built["primary_zones"]] == builder
