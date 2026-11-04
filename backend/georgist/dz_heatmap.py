"""DZ-HEATMAP PR-A — Data Zone status-category layer contract (no value layer).

Serves one status category per Data Zone (estimated / unavailable /
model_failure / no_cell / not_scored). No band, rank, value, price, rent or pound
field exists in the input file or the payload. Config-driven from
``data/config/dz_heatmap.yaml``; zone codes come from the pinned key set of the
file's ``data_zone_vintage`` (DZ2011: ``data/reference/v14/dz2011_keys.json``).

Fails closed. Served only when ALL hold (server-side): the flag is on;
``gbp_display`` is false; estimate_year is not 2023; the vintage has a pinned key
set and a credit; the status file covers exactly that key set; the year's gate
record (the ``rerun_v14_score`` report JSON) exists and is PASS; and the locked
run's lock (``write_holdout_lock`` JSON) carries that report's sha256 and lists
the status file's sha256. Otherwise 404. Reasons are logged, never served.
Reads files only: no DB, no surface model.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "data" / "config" / "dz_heatmap.yaml"
SURFACE_CONFIG_PATH = ROOT / "data" / "config" / "surface.yaml"

STATUS_IDS = ("estimated", "unavailable", "model_failure", "no_cell", "not_scored")
NEVER_SERVED_YEAR = 2023
CODE_RE = re.compile(r"S01\d{6}")
CONFIG_KEYS = frozenset({
    "enabled", "layer_id", "data_zone_vintage", "estimate_year", "status_path",
    "gate_record_path", "lock_path", "key_title", "categories", "vintages",
    "licence", "attribution",
})
VINTAGE_KEYS = frozenset({"keys_path", "keys_sha256", "url", "credit", "vintage_note"})
# BLOCKER (pending ruling): write_holdout_lock has no output-sha field today.
LOCK_OUTPUTS_KEY = "outputs_sha256"
FILE_KEYS = frozenset({"estimate_year", "data_zone_vintage", "zones"})
ZONE_KEYS = frozenset({"zone", "status"})

POUND = "\u00a3"

log = logging.getLogger(__name__)


class DzHeatmapRefused(ValueError):
    """The status layer refuses to serve; the message names the one trigger."""


def _refuse(msg: str) -> None:
    raise DzHeatmapRefused(msg)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_config(path: Path | None = None) -> dict[str, Any]:
    p = path or CONFIG_PATH
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        _refuse("dz_heatmap config unreadable")
    block = data.get("dz_heatmap") if isinstance(data, Mapping) else None
    if not isinstance(block, Mapping):
        _refuse("dz_heatmap config must be a mapping")
    if set(block) != CONFIG_KEYS:
        _refuse("dz_heatmap config keys do not match contract")
    if not isinstance(block["enabled"], bool):
        _refuse("dz_heatmap.enabled must be true or false")
    year = block["estimate_year"]
    if isinstance(year, bool) or not isinstance(year, int):
        _refuse("dz_heatmap.estimate_year must be an integer")
    if year == NEVER_SERVED_YEAR:
        _refuse("dz_heatmap.estimate_year 2023 is never served")
    if not isinstance(block["key_title"], str) or not block["key_title"].strip():
        _refuse("dz_heatmap.key_title must be a non-empty string")
    cats = block["categories"]
    if not isinstance(cats, list) or not all(
        isinstance(c, Mapping) and set(c) == {"id", "label"}
        and isinstance(c["label"], str) and c["label"].strip() for c in cats
    ):
        _refuse("dz_heatmap.categories must be a list of {id, label}")
    if tuple(c["id"] for c in cats) != STATUS_IDS:
        _refuse("dz_heatmap.categories do not match contract status ids")
    vints = block["vintages"]
    if not isinstance(vints, Mapping) or not all(
        isinstance(v, Mapping) and set(v) == VINTAGE_KEYS for v in vints.values()
    ):
        _refuse("dz_heatmap.vintages keys do not match contract")
    for name, v in vints.items():
        if not isinstance(v["credit"], str) or not v["credit"].strip():
            _refuse(f"dz_heatmap vintage {name} has no credit")
        if v["vintage_note"] is not None and not isinstance(v["vintage_note"], str):
            _refuse(f"dz_heatmap vintage {name} vintage_note must be a string or null")
        if v["keys_sha256"] is not None and not (
            isinstance(v["keys_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", v["keys_sha256"])
        ):
            _refuse("dz_heatmap.keys_sha256 must be 64 lowercase hex")
        if v["url"] is not None and not str(v["url"]).startswith("https://maps.gov.scot/"):
            _refuse("dz_heatmap.source must be an official Scottish Government URL")
    vintage_entry(block, block["data_zone_vintage"])
    texts = [c["label"] for c in cats] + [block["key_title"]] + [
        str(v[k]) for v in vints.values() for k in ("credit", "vintage_note")
    ]
    if any(POUND in t for t in texts):
        _refuse("dz_heatmap label contains a pound sign")
    return dict(block)


def vintage_entry(cfg: Mapping[str, Any], vintage: Any) -> Mapping[str, Any]:
    """The pinned entry for a vintage (credit checked in load_config); refuses one with no pinned key set."""
    v = cfg["vintages"].get(vintage) if isinstance(vintage, str) else None
    if v is None:
        _refuse(f"dz_heatmap vintage {vintage!r} has no pinned key set")
    if v["keys_path"] is None or v["keys_sha256"] is None:
        _refuse(f"dz_heatmap vintage {vintage!r} has no pinned key set")
    return v


def gbp_display_off(path: Path | None = None) -> bool:
    """True only when surface.yaml sets gbp_display to exactly false."""
    p = path or SURFACE_CONFIG_PATH
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return False
    m = re.search(r"^\s*gbp_display:\s*(\S+)", text, re.MULTILINE)
    return bool(m) and m.group(1) == "false"


def load_keys(cfg: Mapping[str, Any], root: Path | None = None) -> frozenset[str]:
    vintage = cfg["data_zone_vintage"]
    v = vintage_entry(cfg, vintage)
    p = (root or ROOT) / v["keys_path"]
    if not p.is_file():
        _refuse(f"{vintage} keys file missing")
    if _sha(p) != v["keys_sha256"]:
        _refuse(f"{vintage} keys sha256 does not match config")
    keys = json.loads(p.read_bytes().decode("utf-8"))
    if not isinstance(keys, list) or not keys or len(set(keys)) != len(keys):
        _refuse(f"{vintage} keys must be a list of unique codes")
    if not all(isinstance(k, str) and CODE_RE.fullmatch(k) for k in keys):
        _refuse(f"{vintage} keys must be Scottish Data Zone codes")
    return frozenset(keys)


def load_status(path: Path, cfg: Mapping[str, Any], keys: frozenset[str]) -> dict[str, str]:
    """zone -> status from the status file. Status codes only; refuses anything else."""
    vintage = cfg["data_zone_vintage"]
    if not path.is_file():
        _refuse("status file missing")
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _refuse("status file is not valid JSON")
    if not isinstance(data, dict):
        _refuse("status file must be a JSON object")
    extra = sorted(set(data) - FILE_KEYS)
    if extra:
        _refuse(f"status file has extra key: {extra[0]}")
    if set(data) != FILE_KEYS:
        _refuse("status file keys do not match contract")
    year = data["estimate_year"]
    if isinstance(year, bool) or not isinstance(year, int):
        _refuse("status file estimate_year must be an integer")
    if year != cfg["estimate_year"]:
        _refuse(f"status file estimate_year {year} is not {cfg['estimate_year']}")
    if data["data_zone_vintage"] != vintage:
        _refuse(f"status file data_zone_vintage is not {vintage}")
    rows = data["zones"]
    if not isinstance(rows, list):
        _refuse("status file zones must be a list")
    out: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            _refuse("status file zone row must be an object")
        extra = sorted(set(row) - ZONE_KEYS)
        if extra:
            _refuse(f"status file zone row has extra key: {extra[0]}")
        if set(row) != ZONE_KEYS:
            _refuse("status file zone row keys do not match contract")
        code, status = row["zone"], row["status"]
        if not isinstance(code, str) or code not in keys:
            _refuse(f"status file zone {code!r} is not a {vintage} code")
        if code in out:
            _refuse(f"status file zone {code} is duplicated")
        if status not in STATUS_IDS:
            _refuse(f"status file zone {code} has unknown status {status!r}")
        out[code] = status
    if set(out) != keys:
        missing = sorted(keys - set(out))
        _refuse(f"status file missing zone {missing[0]} ({len(missing)} missing)")
    return out


def _score_years(doc: Mapping[str, Any], ok) -> list[int]:
    return sorted(int(k[6:]) for k, v in doc.items() if re.fullmatch(r"score_\d+", k) and ok(v))


def check_gate(cfg: Mapping[str, Any], status_path: Path, root: Path | None = None) -> None:
    """Gate record (rerun_v14_score report) PASS, tied by the run lock to the status file.

    The gate record's year, the lock's year and the status file's estimate_year
    must all be equal; every mismatched pair is named in the refusal.
    """
    year = cfg["estimate_year"]  # == status file estimate_year (checked in load_status)
    record = (root or ROOT) / cfg["gate_record_path"]
    if not record.is_file():
        _refuse(f"gate record for {year} missing")
    try:
        report = json.loads(record.read_text(encoding="utf-8"))
        checks = report["checks"]
        gate_years = _score_years(report, lambda v: isinstance(v, Mapping))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        _refuse(f"gate record for {year} missing")
    if not isinstance(checks, Mapping) or len(gate_years) != 1:
        _refuse(f"gate record for {year} missing")
    if checks.get("status") != "scored" or checks.get("primary_gating_pass") == "NOT_RUN":
        _refuse(f"gate record for {year} is NOT_RUN")
    if checks.get("primary_gating_pass") is not True:
        _refuse(f"gate record for {year} is not PASS")
    lock = (root or ROOT) / cfg["lock_path"]
    try:
        locked = json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _refuse("locked run lock missing")
    lock_years = _score_years(locked, lambda v: v is True) if isinstance(locked, Mapping) else []
    if len(lock_years) != 1:
        _refuse(f"locked run lock is not for {year}")
    g, l, f = gate_years[0], lock_years[0], year
    pairs = []
    if g != l:
        pairs.append(f"gate record {g} vs lock {l}")
    if l != f:
        pairs.append(f"lock {l} vs status file {f}")
    if g != f:
        pairs.append(f"gate record {g} vs status file {f}")
    if pairs:
        _refuse("year mismatch: " + "; ".join(pairs))
    if locked.get("report_sha256") != _sha(record):
        _refuse("gate record sha256 does not match locked run lock")
    outputs = locked.get(LOCK_OUTPUTS_KEY)
    if not isinstance(outputs, Mapping) or _sha(status_path) not in outputs.values():
        _refuse("status file sha256 not in locked run lock")


def served_state(config_path: Path | None = None, root: Path | None = None) -> dict[str, Any]:
    """{'on': bool, 'reason': str, ...}. Order: config, flag, gbp_display, keys, file, gate."""
    try:
        cfg = load_config(config_path)
    except DzHeatmapRefused as exc:
        return {"on": False, "reason": str(exc)}
    if not cfg["enabled"]:
        return {"on": False, "reason": "dz_heatmap flag off"}
    if not gbp_display_off():
        return {"on": False, "reason": "gbp_display is not off"}
    try:
        keys = load_keys(cfg, root)
        status_path = (root or ROOT) / cfg["status_path"]
        status = load_status(status_path, cfg, keys)
        check_gate(cfg, status_path, root)
    except DzHeatmapRefused as exc:
        return {"on": False, "reason": str(exc)}
    return {"on": True, "reason": "ok", "cfg": cfg, "status": status}


def public_status_payload(config_path: Path | None = None, root: Path | None = None) -> dict[str, Any] | None:
    state = served_state(config_path, root)
    if not state["on"]:
        log.warning("dz_heatmap status layer off: %s", state["reason"])
        return None
    cfg, status = state["cfg"], state["status"]
    vintage = cfg["data_zone_vintage"]
    v = vintage_entry(cfg, vintage)
    return {
        "layer_id": cfg["layer_id"],
        "data_zone_vintage": vintage,
        "estimate_year": cfg["estimate_year"],
        "key_title": cfg["key_title"],
        "categories": [{"id": c["id"], "label": c["label"]} for c in cfg["categories"]],
        "source": {"credit": v["credit"], "licence": cfg["licence"], "attribution": cfg["attribution"]},
        "vintage_note": v["vintage_note"],
        "zones": [{"code": code, "status": status[code]} for code in sorted(status)],
    }
