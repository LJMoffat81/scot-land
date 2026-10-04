"""Split the frozen agr.yaml config into a valuation layer and a policy layer.

The version 1 maths stay where they are. This module only names the keys,
hashes each layer, and stamps a response. It does not change a figure.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from agr.areas import COUNCILS_PATH
from agr.config import CONFIG_PATH, load_config

ENGINE_VERSION = "1.0.0"
LAYERS_PATH = CONFIG_PATH.parent / "layers.yaml"
REPO_ROOT = CONFIG_PATH.parents[1]

logger = logging.getLogger(__name__)


class LayerConfigError(ValueError):
    """layers.yaml does not match the agr config it is mapping."""


def _read_spec() -> dict:
    if not LAYERS_PATH.exists():
        raise LayerConfigError(f"Missing {LAYERS_PATH.name}")
    with LAYERS_PATH.open(encoding="utf-8") as handle:
        spec = yaml.safe_load(handle)
    if not isinstance(spec, dict) or "valuation" not in spec or "policy" not in spec:
        raise LayerConfigError("layers.yaml is missing valuation or policy")
    return spec


def _mapped_paths(spec: dict) -> list[str]:
    policy = spec["policy"]
    paths = [
        *spec["valuation"]["keys"],
        *policy["keys"],
        *(policy.get("applied_by_valuation") or []),
    ]
    return [str(path) for path in paths]


def _get_path(config: dict, path: str) -> Any:
    node: Any = config
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise LayerConfigError(f"Mapped key {path} is missing from agr config")
        node = node[part]
    return node


def _place(dest: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    node = dest
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = copy.deepcopy(value)


def validate_layers(spec: dict, config: dict) -> None:
    """Raise if a key is missing, mapped twice, or a mirror disagrees."""
    paths = _mapped_paths(spec)
    seen: set[str] = set()
    duplicates: set[str] = set()
    for path in paths:
        if path in seen:
            duplicates.add(path)
        seen.add(path)
    if duplicates:
        joined = ", ".join(sorted(duplicates))
        raise LayerConfigError(f"Key mapped more than once: {joined}")

    file_config = load_config()
    for path in paths:
        _get_path(file_config, path)
        if config is not file_config:
            _get_path(config, path)

    for left, right in (spec.get("mirrors") or {}).items():
        left_value = _get_path(config, str(left))
        right_value = _get_path(config, str(right))
        if left_value != right_value:
            raise LayerConfigError(
                f"Mirror {left} disagrees with {right}: {left_value!r} != {right_value!r}"
            )


def load_layers(config: dict | None = None) -> dict:
    """Read layers.yaml and check it against agr.yaml, or against config."""
    spec = _read_spec()
    validate_layers(spec, load_config() if config is None else config)
    return spec


def split_config(config: dict) -> tuple[dict, dict]:
    """Return valuation inputs and policy inputs from the effective config."""
    spec = load_layers(config)
    valuation: dict = {}
    policy: dict = {}
    for path in spec["valuation"]["keys"]:
        _place(valuation, str(path), _get_path(config, str(path)))
    for path in spec["policy"]["keys"]:
        _place(policy, str(path), _get_path(config, str(path)))
    for path in spec["policy"].get("applied_by_valuation") or []:
        _place(policy, str(path), _get_path(config, str(path)))
    return valuation, policy


def layer_hash(inputs: dict) -> str:
    """First 12 hex characters of sha256 over canonical JSON."""
    payload = json.dumps(inputs, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


@lru_cache(maxsize=8)
def _file_sha12(path: str) -> str:
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return digest[:12]


def _file_sha12_lf(path: str) -> str:
    """Hash file content with line endings normalised to LF.

    A Windows checkout and a Unix checkout of the same commit must stamp
    the same layers.yaml identity.
    """
    raw = Path(path).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(raw).hexdigest()[:12]


def _env_commit(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    if not value or value.lower() == "unknown":
        return None
    return value


def _git_head() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        sha = (result.stdout or "").strip()
        if result.returncode == 0 and sha and sha.lower() != "unknown":
            return sha
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


@lru_cache(maxsize=1)
def _commit_ids() -> tuple[str, str]:
    """Short stamp and full sha. Both are dev-unknown when no commit is available."""
    full = None
    for name in ("GIT_COMMIT", "RAILWAY_GIT_COMMIT_SHA"):
        full = _env_commit(name)
        if full:
            break
    if full is None:
        full = _git_head()
    if not full:
        logger.warning("Engine stamp has no git commit; using dev-unknown.")
        return "dev-unknown", "dev-unknown"
    return full[:7], full


# Money inputs on the live residual path. Dates live in agr.yaml `_meta`, not in the maths.
_SCALAR_MONEY_KEYS = (
    "valuer_roll.yield_rate",
    "valuer_roll.rebuild.house_gbp_per_m2",
    "valuer_roll.rebuild.flat_gbp_per_m2",
    "valuer_roll.depreciation.average_stock_remaining_factor",
    "despeculation.farmland_market_to_productive",
    "despeculation.urban_speculation_discount",
)


def _money_input_keys(config: dict) -> list[str]:
    land = config.get("land_use_values_gbp_per_ha_2009")
    if not isinstance(land, dict) or not land:
        raise LayerConfigError("land_use_values_gbp_per_ha_2009 is missing")
    keys = list(_SCALAR_MONEY_KEYS)
    for name in land:
        if str(name).startswith("_"):
            continue
        keys.append(f"land_use_values_gbp_per_ha_2009.{name}")
    return keys


def _meta_entry(config: dict, path: str) -> dict:
    meta = config.get("_meta")
    if not isinstance(meta, dict):
        raise LayerConfigError("agr config is missing _meta")
    entry = meta.get(path)
    if not isinstance(entry, dict):
        raise LayerConfigError(f"{path} has no _meta entry")
    return entry


def _as_of(config: dict, path: str) -> str:
    as_of = _meta_entry(config, path).get("as_of")
    if not isinstance(as_of, str) or not as_of.strip():
        raise LayerConfigError(f"{path} has no _meta.as_of")
    return as_of


# Pinned sha256 of data/processed/dz2011_prices.csv (job 034). The stamp quotes the full digest.
DZ_PRICES_SHA256 = "a9f819173a438db50b10ae2bf81e1ff0b72da767714e6537822b073a438b8f62"
DZ_PRICES_PATH = Path(__file__).resolve().parents[2] / "data" / "processed" / "dz2011_prices.csv"


def _price_data() -> dict:
    """Where the town market value came from. Not a figure, and not shown on the card."""
    if not DZ_PRICES_PATH.is_file():
        raise LayerConfigError(f"Missing {DZ_PRICES_PATH.name}")
    digest = hashlib.sha256(DZ_PRICES_PATH.read_bytes()).hexdigest()
    if digest != DZ_PRICES_SHA256:
        raise LayerConfigError("dz2011_prices.csv sha256 does not match the pin")
    return {
        "source": "RoS Residential Properties Sales and Price (statistics.gov.scot, OGL)",
        "file_sha256": digest,
        "year": 2023,
        "index": "UK HPI July 2026, annual mean of sale year to 2025-04-01",
    }


def _valuation_date_fields(config: dict) -> dict:
    """Stamp fields only. rebased stays false until a later job re-indexes inputs."""
    valuation = config.get("valuation") if isinstance(config.get("valuation"), dict) else {}
    date = valuation.get("valuation_date")
    if not isinstance(date, str) or not date.strip():
        raise LayerConfigError("valuation.valuation_date is missing")
    source = _meta_entry(config, "valuation.valuation_date").get("source")
    if not isinstance(source, str) or not source.strip():
        raise LayerConfigError("valuation.valuation_date has no _meta source")
    return {
        "valuation_date": date,
        "rebased_to_valuation_date": False,
        "inputs_as_of": {path: _as_of(config, path) for path in _money_input_keys(config)},
        "price_data": _price_data(),
    }


def engine_stamp(config: dict) -> dict:
    """Identity of the engine that produced a response. Figures are not in here."""
    spec = load_layers(config)
    valuation_inputs, policy_inputs = split_config(config)
    councils = json.loads(COUNCILS_PATH.read_text(encoding="utf-8"))
    overrides = config.get("_sensitivity_overrides") or {}
    valuation_stamp = {
        "version": spec["valuation"]["version"],
        "inputs_hash": layer_hash(valuation_inputs),
    }
    valuation_stamp.update(_valuation_date_fields(config))
    return {
        "engine_version": ENGINE_VERSION,
        "valuation": valuation_stamp,
        "policy": {
            "version": spec["policy"]["version"],
            "inputs_hash": layer_hash(policy_inputs),
        },
        "config": {
            "agr_yaml_sha256": _file_sha12(str(CONFIG_PATH)),
            "layers_yaml_sha256": _file_sha12_lf(str(LAYERS_PATH)),
        },
        "data": {
            "councils_generated_at": councils.get("generated_at") or "",
            "hpi_period": councils.get("hpi_period") or "",
        },
        "commit": _commit_ids()[0],
        "commit_full": _commit_ids()[1],
        "sensitivity_overrides": dict(overrides),
    }
