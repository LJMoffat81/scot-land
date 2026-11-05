"""DZ-HEATMAP PR-A — status-category layer on real DZ2011 codes (no value layer).

Synthetic statuses only; Data Zone codes are the real pinned DZ2011 key list
(codes only, OGL v3). Every fixture carries estimate_year 0, so it can never be
served by the shipped config (estimate_year 2024). ON-path tests write their own
config with estimate_year 0; ``test_synthetic_fixture_never_served_by_real_year``
proves the real year refuses them. Each refusal test changes exactly one input.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from georgist import dz_heatmap as dz

REPO = Path(__file__).resolve().parents[3]
KEYS_FILE = REPO / "data" / "reference" / "v14" / "dz2011_keys.json"
KEYS = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
FIXTURE_YEAR = 0
SHIPPED = yaml.safe_load((REPO / "data" / "config" / "dz_heatmap.yaml").read_text(encoding="utf-8"))["dz_heatmap"]


def _status_doc(year: int = FIXTURE_YEAR) -> dict:
    zones = [{"zone": code, "status": dz.STATUS_IDS[i % 5]} for i, code in enumerate(KEYS)]
    return {"estimate_year": year, "data_zone_vintage": "DZ2011", "zones": zones}


def _cfg(status_path: Path, **over) -> dict:
    block = copy.deepcopy(SHIPPED)
    tmp = status_path.parent
    year = over.get("estimate_year", FIXTURE_YEAR)
    block.update(enabled=True, estimate_year=year, status_path=str(status_path),
                 gate_record_path=str(tmp / "report.json"),
                 lock_path=str(tmp / f"score_{year}.lock"),
                 lock_sha256=None)
    block["vintages"]["DZ2011"]["keys_path"] = str(KEYS_FILE)
    for k in [k for k in over if k in dz.VINTAGE_KEYS]:
        block["vintages"]["DZ2011"][k] = over.pop(k)
    block.update(over)
    return {"dz_heatmap": block}


def _report(year: int = FIXTURE_YEAR, primary=True, status="scored") -> dict:
    """Synthetic gate record in the rerun_v14_score report format (no values)."""
    return {f"score_{year}": {}, "checks": {"status": status, "full": True, "primary_gating_pass": primary}}


def _write_gate(env, report=None, lock_over=None, year: int = FIXTURE_YEAR):
    """Gate record + write_holdout_lock-format lock tying it to the status file.

    Lock filename follows the config estimate_year (path-match rule). The
    ``year`` argument is the score_<year> key written into the lock payload.
    """
    rec = env["tmp"] / "report.json"
    cur = yaml.safe_load(env["cfg"].read_text(encoding="utf-8"))["dz_heatmap"]
    cfg_year = cur["estimate_year"]
    lock = env["tmp"] / f"score_{cfg_year}.lock"
    rec.write_text(json.dumps(_report(year) if report is None else report), encoding="utf-8")
    payload = {
        "label": "seen, not out-of-sample", f"score_{year}": True,
        "report_sha256": hashlib.sha256(rec.read_bytes()).hexdigest(),
        dz.LOCK_OUTPUTS_KEY: {"dz_status.json": hashlib.sha256(env["status"].read_bytes()).hexdigest()},
    }
    payload.update(lock_over or {})
    lock.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    # Pin the lock bytes; keep estimate_year as already configured.
    _write_cfg(
        env,
        estimate_year=cfg_year,
        lock_path=str(lock),
        lock_sha256=hashlib.sha256(lock.read_bytes()).hexdigest(),
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    """All inputs ON with synthetic statuses; each test turns exactly one input off."""
    status = tmp_path / "dz_status.json"
    cfg = tmp_path / "dz_heatmap.yaml"
    surface = tmp_path / "surface.yaml"
    status.write_text(json.dumps(_status_doc()), encoding="utf-8")
    cfg.write_text(yaml.safe_dump(_cfg(status), allow_unicode=True), encoding="utf-8")
    surface.write_text("surface:\n  v14:\n    gbp_display: false\n", encoding="utf-8")
    monkeypatch.setattr(dz, "CONFIG_PATH", cfg)
    monkeypatch.setattr(dz, "SURFACE_CONFIG_PATH", surface)
    e = {"status": status, "cfg": cfg, "surface": surface, "tmp": tmp_path}
    _write_gate(e)
    return e


def _write_cfg(env, **over):
    env["cfg"].write_text(yaml.safe_dump(_cfg(env["status"], **over), allow_unicode=True), encoding="utf-8")


def _write_status(env, doc):
    env["status"].write_text(json.dumps(doc), encoding="utf-8")
    _write_gate(env)  # keep the lock tied, so only the file contract is under test


def _reason(env) -> str:
    return dz.served_state()["reason"]


def _client():
    from api.main import create_app, registered_routes
    app = create_app()
    # 404 tests are only meaningful if the route is mounted.
    assert ("GET", "/platform/dz-status") in registered_routes(app)
    return TestClient(app)


# ---------- shipped state ----------

def test_shipped_flag_is_off():
    assert SHIPPED["enabled"] is False


def test_shipped_config_is_valid_and_pins_real_keys():
    cfg = dz.load_config(REPO / "data" / "config" / "dz_heatmap.yaml")
    assert cfg["estimate_year"] == 2024
    assert cfg["data_zone_vintage"] == "DZ2011"
    assert cfg["lock_path"] == "data/processed/dz_heatmap/score_2024.lock"
    assert cfg["lock_sha256"] is None  # switch-on PR sets the pin; null keeps serving refused
    v = cfg["vintages"]["DZ2011"]
    assert v["keys_path"] == "data/reference/v14/dz2011_keys.json"
    assert v["keys_sha256"] == hashlib.sha256(KEYS_FILE.read_bytes()).hexdigest()
    assert v["keys_sha256"] == "2611c9e701d9affef34680be2a0d9bbc14468ddbc5241f353819f9ee59849874"
    assert v["url"].startswith("https://maps.gov.scot/")
    assert cfg["licence"] == "Open Government Licence v3.0"
    assert cfg["vintages"]["DZ2022"]["keys_path"] is None  # no pinned DZ2022 key set in the repo


LOCKED_LABELS = [
    ("estimated", "Estimate available"),
    ("unavailable", "No estimate: data not available"),
    ("model_failure", "No estimate: our method doesn't work well here"),
    ("no_cell", "No estimate: too few similar sales"),
    ("not_scored", "No estimate: outside the areas we estimate"),
]


def test_shipped_labels_and_key_title_locked():
    assert [(c["id"], c["label"]) for c in SHIPPED["categories"]] == LOCKED_LABELS
    assert SHIPPED["key_title"] == "Estimate status"


def test_credit_matches_vintage(env):
    body = _client().get("/platform/dz-status").json()
    assert body["source"]["credit"] == "Scottish Government, Data Zone Boundaries 2011, Open Government Licence v3.0"
    cfg = dz.load_config()
    assert dz.vintage_entry(cfg, "DZ2011")["credit"] == body["source"]["credit"]
    assert SHIPPED["vintages"]["DZ2022"]["credit"] == "Scottish Government, Data Zone Boundaries 2022, Open Government Licence v3.0"


def test_vintage_note_per_vintage(env):
    body = _client().get("/platform/dz-status").json()
    assert body["vintage_note"] == "Uses 2011 local areas (data zones)"
    assert SHIPPED["vintages"]["DZ2011"]["vintage_note"] == "Uses 2011 local areas (data zones)"
    assert SHIPPED["vintages"]["DZ2022"]["vintage_note"] is None


def test_vintage_without_credit_refuses(env):
    _write_cfg(env, credit="")
    assert _reason(env) == "dz_heatmap vintage DZ2011 has no credit"


def test_unknown_vintage_refuses(env):
    _write_cfg(env, data_zone_vintage="DZ2001")
    assert _reason(env) == "dz_heatmap vintage 'DZ2001' has no pinned key set"


def test_dz2022_without_pinned_keys_refuses(env):
    _write_cfg(env, data_zone_vintage="DZ2022")
    assert _reason(env) == "dz_heatmap vintage 'DZ2022' has no pinned key set"


def test_year_2023_refused_with_flag_on(env):
    _write_cfg(env, estimate_year=2023)
    _write_gate(env, report=_report(2023), year=2023)
    assert _reason(env) == "dz_heatmap.estimate_year 2023 is never served"
    assert _client().get("/platform/dz-status").status_code == 404


# ---------- gate record + lock (fail closed) ----------

def test_gate_missing_refuses(env):
    (env["tmp"] / "report.json").unlink()
    assert _reason(env) == f"gate record for {FIXTURE_YEAR} missing"


def test_gate_fail_refuses(env):
    _write_gate(env, report=_report(primary=False))
    assert _reason(env) == f"gate record for {FIXTURE_YEAR} is not PASS"


def test_gate_not_run_refuses(env):
    _write_gate(env, report=_report(primary="NOT_RUN"))
    assert _reason(env) == f"gate record for {FIXTURE_YEAR} is NOT_RUN"


def test_gate_other_year_refuses(env):
    _write_gate(env, report=_report(2024))
    assert _reason(env) == "year mismatch: gate record 2024 vs lock 0; gate record 2024 vs status file 0"


# Three values, so a single change breaks two pairs; each pair is covered twice and named exactly.
def test_year_mismatch_gate_vs_lock_and_file(env):
    """Gate record year differs (pairs gate-lock, gate-file)."""
    _write_gate(env, report=_report(7), lock_over={"score_0": True})
    assert _reason(env) == "year mismatch: gate record 7 vs lock 0; gate record 7 vs status file 0"


def test_year_mismatch_lock_vs_gate_and_file(env):
    """Lock year differs (pairs gate-lock, lock-file)."""
    _write_gate(env, lock_over={"score_0": False, "score_7": True})
    assert _reason(env) == "year mismatch: gate record 0 vs lock 7; lock 7 vs status file 0"


def test_year_mismatch_file_vs_gate_and_lock(env):
    """Status file estimate_year differs (pairs lock-file, gate-file); config follows the file."""
    _write_cfg(env, estimate_year=7)
    _write_status(env, _status_doc(7))
    _write_gate(env)
    assert _reason(env) == "year mismatch: lock 0 vs status file 7; gate record 0 vs status file 7"


def test_lock_without_single_score_year_refuses(env):
    _write_gate(env, lock_over={"score_0": False})
    assert _reason(env) == f"locked run lock is not for {FIXTURE_YEAR}"


def test_gate_two_score_years_refuses(env):
    rep = _report()
    rep["score_7"] = {}
    _write_gate(env, report=rep)
    assert _reason(env) == f"gate record for {FIXTURE_YEAR} missing"


def test_gate_record_not_locked_refuses(env):
    _write_gate(env, lock_over={"report_sha256": "0" * 64})
    assert _reason(env) == "gate record sha256 does not match locked run lock"


def test_lock_missing_refuses(env):
    (env["tmp"] / f"score_{FIXTURE_YEAR}.lock").unlink()
    assert _reason(env) == "locked run lock missing"


def test_status_sha_not_in_lock_refuses(env):
    _write_gate(env, lock_over={dz.LOCK_OUTPUTS_KEY: {"dz_status.json": "0" * 64}})
    assert _reason(env) == "status file sha256 not in locked run lock"


def test_shipped_route_is_absent():
    r = _client().get("/platform/dz-status")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}


def test_real_gbp_display_is_off():
    assert dz.gbp_display_off(REPO / "data" / "config" / "surface.yaml") is True


def test_real_keys_load():
    keys = dz.load_keys(dz.load_config(REPO / "data" / "config" / "dz_heatmap.yaml"), REPO)
    assert len(keys) == 6976 and keys == frozenset(KEYS)


def test_synthetic_fixture_never_served_by_real_year(env):
    _write_cfg(env, estimate_year=2024)
    assert _reason(env) == "status file estimate_year 0 is not 2024"
    assert _client().get("/platform/dz-status").status_code == 404


# ---------- ON path ----------

def test_on_payload_exact(env):
    r = _client().get("/platform/dz-status")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"layer_id", "data_zone_vintage", "estimate_year", "key_title", "categories", "source", "vintage_note", "zones"}
    assert body["key_title"] == "Estimate status"
    assert body["layer_id"] == "dz_status"
    assert body["data_zone_vintage"] == "DZ2011"
    assert [c["id"] for c in body["categories"]] == list(dz.STATUS_IDS)
    assert [(c["id"], c["label"]) for c in body["categories"]] == LOCKED_LABELS
    assert set(body["source"]) == {"credit", "licence", "attribution"}
    assert len(body["zones"]) == 6976
    assert [z["code"] for z in body["zones"]] == KEYS
    assert all(set(z) == {"code", "status"} for z in body["zones"])


def test_on_status_follows_file(env):
    doc = _status_doc()
    for row in doc["zones"]:
        row["status"] = "no_cell"
    doc["zones"][0]["status"] = "estimated"
    _write_status(env, doc)
    zones = _client().get("/platform/dz-status").json()["zones"]
    assert zones[0] == {"code": KEYS[0], "status": "estimated"}
    assert {z["status"] for z in zones[1:]} == {"no_cell"}


def _all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_keys(v)


@pytest.mark.parametrize("on", [True, False])
def test_no_pound_or_value_fields(env, on):
    if not on:
        _write_cfg(env, enabled=False)
    r = _client().get("/platform/dz-status")
    assert dz.POUND not in r.text and "GBP" not in r.text
    banned = {"value", "price", "rent", "band", "rank", "drc", "area", "uncertain", "gbp"}
    for key in _all_keys(r.json()):
        assert not any(b in key.lower() for b in banned), key


# ---------- served-state refusals (one trigger each, exact reason) ----------

def test_flag_off(env):
    _write_cfg(env, enabled=False)
    assert _reason(env) == "dz_heatmap flag off"


def test_gbp_display_true_refuses(env):
    env["surface"].write_text("surface:\n  v14:\n    gbp_display: true\n", encoding="utf-8")
    assert _reason(env) == "gbp_display is not off"


def test_gbp_display_missing_refuses(env):
    env["surface"].write_text("surface: {}\n", encoding="utf-8")
    assert _reason(env) == "gbp_display is not off"


def test_surface_config_missing_refuses(env):
    env["surface"].unlink()
    assert _reason(env) == "gbp_display is not off"


CONFIG_REFUSALS = [
    ("enabled", "yes", "dz_heatmap.enabled must be true or false"),
    ("estimate_year", "2024", "dz_heatmap.estimate_year must be an integer"),
    ("estimate_year", True, "dz_heatmap.estimate_year must be an integer"),
    ("keys_sha256", "A" * 64, "dz_heatmap.keys_sha256 must be 64 lowercase hex"),
    ("categories", [{"id": "estimated"}], "dz_heatmap.categories must be a list of {id, label}"),
    ("categories", [{"id": i, "label": "x"} for i in reversed(dz.STATUS_IDS)], "dz_heatmap.categories do not match contract status ids"),
    ("categories", [{"id": i, "label": "x"} for i in dz.STATUS_IDS[:4]], "dz_heatmap.categories do not match contract status ids"),
    ("categories", [{"id": i, "label": dz.POUND + " x"} for i in dz.STATUS_IDS], "dz_heatmap label contains a pound sign"),
    ("vintages", {"DZ2011": {"keys_path": "x", "credit": "x"}}, "dz_heatmap.vintages keys do not match contract"),
    ("url", "https://example.com/dz.zip", "dz_heatmap.source must be an official Scottish Government URL"),
    ("keys_sha256", "0" * 64, "DZ2011 keys sha256 does not match config"),
    ("key_title", "", "dz_heatmap.key_title must be a non-empty string"),
    ("vintage_note", 1, "dz_heatmap vintage DZ2011 vintage_note must be a string or null"),
]


@pytest.mark.parametrize("key,val,msg", CONFIG_REFUSALS)
def test_config_refusals(env, key, val, msg):
    _write_cfg(env, **{key: val})
    assert _reason(env) == msg
    assert _client().get("/platform/dz-status").status_code == 404


def test_config_extra_key_refuses(env):
    _write_cfg(env, gbp_display=True)
    assert _reason(env) == "dz_heatmap config keys do not match contract"


def test_config_not_mapping_refuses(env):
    env["cfg"].write_text("dz_heatmap: [1]\n", encoding="utf-8")
    assert _reason(env) == "dz_heatmap config must be a mapping"


def test_config_unreadable_refuses(env):
    env["cfg"].unlink()
    assert _reason(env) == "dz_heatmap config unreadable"


def test_keys_file_missing_refuses(env):
    _write_cfg(env, keys_path=str(env["tmp"] / "nope.json"))
    assert _reason(env) == "DZ2011 keys file missing"


def _fake_keys(env, keys) -> str:
    p = env["tmp"] / "keys.json"
    p.write_text(json.dumps(keys), encoding="utf-8")
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_keys_duplicate_refuses(env):
    sha = _fake_keys(env, KEYS + KEYS[:1])
    _write_cfg(env, keys_path=str(env["tmp"] / "keys.json"), keys_sha256=sha)
    assert _reason(env) == "DZ2011 keys must be a list of unique codes"


def test_coverage_is_the_pinned_key_set_not_a_count(env):
    # A pinned 6975-code set: the 6976-row file now has an extra zone and refuses.
    sha = _fake_keys(env, KEYS[1:])
    _write_cfg(env, keys_path=str(env["tmp"] / "keys.json"), keys_sha256=sha)
    assert _reason(env) == f"status file zone {KEYS[0]!r} is not a DZ2011 code"


def test_keys_non_scottish_code_refuses(env):
    sha = _fake_keys(env, ["E01000001"] + KEYS[1:])
    _write_cfg(env, keys_path=str(env["tmp"] / "keys.json"), keys_sha256=sha)
    assert _reason(env) == "DZ2011 keys must be Scottish Data Zone codes"


def _doc(**over):
    d = _status_doc()
    d.update(over)
    return d


def _row(i, **over):
    d = _status_doc()
    d["zones"][i] = {**d["zones"][i], **over}
    return d


STATUS_REFUSALS = {
    "missing": (None, "status file missing"),
    "not_json": ("{nope", "status file is not valid JSON"),
    "not_utf8": (b"\xff\xfe", "status file is not valid JSON"),
    "not_object": ([], "status file must be a JSON object"),
    "extra_key_value": (_doc(values=[1]), "status file has extra key: values"),
    "extra_key_rank": (_doc(rank_metric="P_C"), "status file has extra key: rank_metric"),
    "missing_key": ({"estimate_year": 0, "zones": []}, "status file keys do not match contract"),
    "year_str": (_doc(estimate_year="0"), "status file estimate_year must be an integer"),
    "year_bool": (_doc(estimate_year=False), "status file estimate_year must be an integer"),
    "year_wrong": (_doc(estimate_year=2023), "status file estimate_year 2023 is not 0"),
    "vintage": (_doc(data_zone_vintage="DZ2022"), "status file data_zone_vintage is not DZ2011"),
    "zones_not_list": (_doc(zones={}), "status file zones must be a list"),
    "row_not_object": (_doc(zones=["S01006506"]), "status file zone row must be an object"),
    "row_rank": (_row(0, rank_P_C=1), "status file zone row has extra key: rank_P_C"),
    "row_band": (_row(0, band=3), "status file zone row has extra key: band"),
    "row_value": (_row(0, measured_rent=1.0), "status file zone row has extra key: measured_rent"),
    "row_missing_status": (_doc(zones=[{"zone": KEYS[0]}]), "status file zone row keys do not match contract"),
    "extra_zone": (_doc(zones=_status_doc()["zones"] + [{"zone": "S01099999", "status": "estimated"}]), "status file zone 'S01099999' is not a DZ2011 code"),
    "dz2022_code": (_row(0, zone="S01013482"), "status file zone 'S01013482' is not a DZ2011 code"),
    "english_code": (_row(0, zone="E01000001"), "status file zone 'E01000001' is not a DZ2011 code"),
    "int_code": (_row(0, zone=6506), "status file zone 6506 is not a DZ2011 code"),
    "duplicate": (_row(1, zone=KEYS[0]), f"status file zone {KEYS[0]} is duplicated"),
    "unknown_status": (_row(0, status="excluded"), f"status file zone {KEYS[0]} has unknown status 'excluded'"),
    "null_status": (_row(0, status=None), f"status file zone {KEYS[0]} has unknown status None"),
    "missing_zone": (_doc(zones=_status_doc()["zones"][1:]), f"status file missing zone {KEYS[0]} (1 missing)"),
}


@pytest.mark.parametrize("name", list(STATUS_REFUSALS))
def test_status_refusals(env, name):
    doc, msg = STATUS_REFUSALS[name]
    if doc is None:
        env["status"].unlink()
    elif isinstance(doc, bytes):
        env["status"].write_bytes(doc)
    elif isinstance(doc, str):
        env["status"].write_text(doc, encoding="utf-8")
    else:
        _write_status(env, doc)
    assert _reason(env) == msg
    assert _client().get("/platform/dz-status").status_code == 404


def test_refusal_never_served_in_body(env):
    _write_status(env, _doc(data_zone_vintage="DZ2022"))
    r = _client().get("/platform/dz-status")
    assert r.json() == {"detail": "Not Found"}


def test_refusal_reason_logged(env, caplog):
    _write_cfg(env, enabled=False)
    with caplog.at_level("WARNING", logger="georgist.dz_heatmap"):
        assert dz.public_status_payload() is None
    assert "dz_heatmap status layer off: dz_heatmap flag off" in caplog.text


# ---------- isolation: files only, no DB, no surface model ----------

def test_module_imports_no_db_or_surface():
    tree = ast.parse(Path(dz.__file__).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names |= {f"{node.module}.{a.name}" for a in node.names}
    assert not any(n.startswith(("georgist.db", "georgist.surface", "psycopg", "sqlalchemy")) for n in names)
    src = Path(dz.__file__).read_text(encoding="utf-8").lower()
    assert "select " not in src and "surface_rent" not in src


def test_db_blocked_during_served_state(env, monkeypatch):
    from georgist import db

    def boom(*a, **k):
        raise AssertionError("DB touched")

    for name in ("connect", "cursor", "connection_kwargs"):
        monkeypatch.setattr(db, name, boom)
    assert dz.served_state()["on"] is True


def test_publication_rule_declares_no_values():
    from georgist.publication_rules import PUBLIC_ROUTE_RULES
    rule = PUBLIC_ROUTE_RULES["/platform/dz-status"]
    assert (rule.geometry_level, rule.source_granularity, rule.value_basis) == ("zone", "zone", "none")
    assert rule.carries_values is False


def test_lock_two_score_years_refuses(env):
    _write_gate(env, lock_over={"score_7": True})
    assert _reason(env) == f"locked run lock is not for {FIXTURE_YEAR}"


# ---------- LOCK-OUTPUTS consumer guards ----------

def test_lock_pin_missing_refuses(env):
    _write_cfg(env, lock_sha256=None)
    assert _reason(env) == "dz_heatmap.lock_sha256 pin missing"


def test_lock_edited_refuses_against_pin(env):
    lock = env["tmp"] / f"score_{FIXTURE_YEAR}.lock"
    pin = hashlib.sha256(lock.read_bytes()).hexdigest()
    _write_cfg(env, lock_path=str(lock), lock_sha256=pin)
    lock.write_bytes(lock.read_bytes() + b"\n")
    assert _reason(env) == "locked run lock sha256 does not match pin"


def test_lock_path_mismatch_refuses(env):
    lock = env["tmp"] / f"score_{FIXTURE_YEAR}.lock"
    pin = hashlib.sha256(lock.read_bytes()).hexdigest()
    _write_cfg(env, lock_path=str(env["tmp"] / "holdout_2023.lock"), lock_sha256=pin)
    assert _reason(env) == "locked run lock path does not match config"


def test_outputs_sha256_missing_refuses(env):
    lock = env["tmp"] / f"score_{FIXTURE_YEAR}.lock"
    payload = json.loads(lock.read_text(encoding="utf-8"))
    del payload[dz.LOCK_OUTPUTS_KEY]
    lock.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    _write_cfg(env, lock_path=str(lock),
               lock_sha256=hashlib.sha256(lock.read_bytes()).hexdigest())
    assert _reason(env) == "locked run lock outputs_sha256 missing"


def test_tombstone_path_never_served(env):
    """SYNTHETIC. Consumer serves only score_<year>.lock, never a tombstone."""
    tomb = env["tmp"] / f"score_{FIXTURE_YEAR}.tombstone"
    tomb.write_text('{"score_2024_started": true}\n', encoding="utf-8")
    pin = hashlib.sha256(tomb.read_bytes()).hexdigest()
    _write_cfg(env, lock_path=str(tomb), lock_sha256=pin)
    assert _reason(env) == "locked run lock path does not match config"
