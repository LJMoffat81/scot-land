"""ARCH-4b: Park non-official / derived Batch B layers and enforce official-only registry & proxy guards.

Usage::

    python -m layers.parked_check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from layers.registry.loader import REGISTRY_DIR, LayerEntry, load_registry
from spatial.context_tiles import _ALLOWED_HOSTS, FEATURES, RASTER

REPO_ROOT = Path(__file__).resolve().parents[2]
PARKED_YAML = Path(__file__).resolve().parent / "parked_sources.yaml"

_ALLOWED_KINDS = frozenset({"context_raster", "postgis_overlay"})
_ALLOWED_VERDICTS = frozenset({"NOT-OFFICIAL", "OFFICIAL-BUT-PROXY"})
_ALLOWED_REASONS = frozenset(
    {
        "contractor-host",
        "derived-geometry",
        "licence-unverified",
        "proxy-host-pending-gis",
    }
)
_REQUIRED_PARKED_IDS = frozenset(
    {
        "sea-12nm",
        "marine-regions",
        "scottish-zone",
        "harbours",
        "wind-plan",
        "community_ownership",
        "public_land",
        "map_builtup_mask",
    }
)
_FORBIDDEN_HOSTS = ("atkinsgeospatial.com", "postcodes.io", "martinjc")


class ParkedGuardError(Exception):
    """Raised when parked-layer manifest or official-source guard fails (``PARKED:`` prefix)."""


def load_parked_sources(path: Path | str = PARKED_YAML) -> dict[str, dict[str, str]]:
    """Load and validate ``parked_sources.yaml``."""
    if not isinstance(path, (Path, str)) or isinstance(path, bool):
        raise ParkedGuardError("PARKED: path must be a Path or str")
    p = Path(path)
    if not p.is_file():
        raise ParkedGuardError(f"PARKED: file not found: {p}")
    raw_text = p.read_text(encoding="utf-8")
    if not raw_text.strip():
        raise ParkedGuardError(f"PARKED: file is empty: {p}")
    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ParkedGuardError(f"PARKED: invalid YAML: {p}") from exc
    if not isinstance(data, dict) or set(data.keys()) != {"parked_sources"}:
        raise ParkedGuardError(
            "PARKED: root must be a mapping with key 'parked_sources'"
        )
    ps = data["parked_sources"]
    if not isinstance(ps, dict) or len(ps) == 0:
        raise ParkedGuardError(
            "PARKED: parked_sources must be a non-empty mapping"
        )
    out: dict[str, dict[str, str]] = {}
    req_keys = (
        "kind",
        "audit_verdict",
        "park_reason",
        "summary",
        "official_replacement",
    )
    for sid, entry in ps.items():
        if not isinstance(sid, str) or not sid.strip():
            raise ParkedGuardError("PARKED: source id must be a non-empty string")
        if not isinstance(entry, dict):
            raise ParkedGuardError(f"PARKED: {sid}: entry must be a mapping")
        for k in req_keys:
            val = entry.get(k)
            if not isinstance(val, str) or not val.strip():
                raise ParkedGuardError(
                    f"PARKED: {sid}: {k} must be a non-empty string"
                )
        extra = set(entry.keys()) - set(req_keys)
        if extra:
            bad_k = sorted(extra)[0]
            raise ParkedGuardError(
                f"PARKED: {sid}: unknown key {bad_k!r}"
            )
        if entry["kind"] not in _ALLOWED_KINDS:
            raise ParkedGuardError(
                f"PARKED: {sid}: invalid kind {entry['kind']!r}"
            )
        if entry["audit_verdict"] not in _ALLOWED_VERDICTS:
            raise ParkedGuardError(
                f"PARKED: {sid}: invalid audit_verdict {entry['audit_verdict']!r}"
            )
        if entry["park_reason"] not in _ALLOWED_REASONS:
            raise ParkedGuardError(
                f"PARKED: {sid}: invalid park_reason {entry['park_reason']!r}"
            )
        out[sid] = {k: entry[k].strip() for k in req_keys}

    missing = sorted(_REQUIRED_PARKED_IDS - set(out.keys()))
    if missing:
        raise ParkedGuardError(
            f"PARKED: missing required parked id {missing[0]!r}"
        )
    return out


def check_parked_guards(
    *,
    parked_path: Path | str = PARKED_YAML,
    entries: dict[str, Any] | None = None,
    raster_specs: dict[str, Any] | None = None,
    feature_specs: dict[str, Any] | None = None,
    allowed_hosts: frozenset[str] | set[str] | None = None,
) -> dict[str, Any]:
    """Verify parked sources are absent from registry & active proxy tables and no forbidden host is allowlisted."""
    parked = load_parked_sources(parked_path)
    reg = entries if entries is not None else load_registry(REGISTRY_DIR)
    rasters = RASTER if raster_specs is None else raster_specs
    feats = FEATURES if feature_specs is None else feature_specs
    hosts = _ALLOWED_HOSTS if allowed_hosts is None else allowed_hosts

    if (
        not isinstance(reg, dict)
        or not isinstance(rasters, dict)
        or not isinstance(feats, dict)
        or not isinstance(hosts, (set, frozenset))
    ):
        raise ParkedGuardError(
            "PARKED: reg, raster_specs, feature_specs must be dicts and allowed_hosts a set"
        )

    for host in sorted(hosts):
        if not isinstance(host, str):
            raise ParkedGuardError("PARKED: host in allowed_hosts must be a string")
        for forbidden in _FORBIDDEN_HOSTS:
            if forbidden in host.lower():
                raise ParkedGuardError(
                    f"PARKED: forbidden host {host!r} in allowed_hosts"
                )

    for sid, pinfo in sorted(parked.items()):
        norm_variants = {sid, sid.replace("_", "-"), sid.replace("-", "_")}
        for v in sorted(norm_variants):
            if v in reg:
                raise ParkedGuardError(
                    f"PARKED: parked source {sid!r} must not appear in registry"
                )
            if v in rasters:
                raise ParkedGuardError(
                    f"PARKED: parked source {sid!r} must not appear in RASTER"
                )
            if v in feats:
                raise ParkedGuardError(
                    f"PARKED: parked source {sid!r} must not appear in FEATURES"
                )

    for lid, entry in sorted(reg.items()):
        raw = entry.raw if isinstance(entry, LayerEntry) else entry
        if not isinstance(raw, dict):
            raise ParkedGuardError(f"PARKED: registry {lid}: entry must be a mapping")
        src = raw.get("source") or {}
        url = str(src.get("url") or "")
        for forbidden in _FORBIDDEN_HOSTS:
            if forbidden in url.lower():
                raise ParkedGuardError(
                    f"PARKED: registry {lid}: forbidden upstream host in {url!r}"
                )

    return {
        "ok": True,
        "parked_count": len(parked),
        "registry_count": len(reg),
        "active_raster_ids": sorted(rasters.keys()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--parked-file",
        type=Path,
        default=PARKED_YAML,
        help="Path to parked_sources.yaml",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        summary = check_parked_guards(parked_path=args.parked_file)
        print(json.dumps(summary, sort_keys=True))
        return 0
    except ParkedGuardError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
