"""Live LayersPanel-bound catalog layers must each have a UI toggle.

Ledger-mapped layers (ledger_role / ui_surface=ledger) feed the Natural capital
ledger or Data section — they must not require a layers-pop-out toggle.
"""

from __future__ import annotations

import json
from pathlib import Path

from layers.platform import platform_catalog

REPO_ROOT = Path(__file__).resolve().parents[2]
TOGGLES_PATH = REPO_ROOT / "frontend" / "lib" / "catalogUiToggles.json"


def _requires_layers_panel_toggle(row: dict) -> bool:
    if row.get("status") != "live":
        return False
    if row.get("ledger_role") or row.get("ui_surface") == "ledger":
        return False
    return True


def test_live_catalog_layers_have_ui_toggles():
    doc = json.loads(TOGGLES_PATH.read_text(encoding="utf-8"))
    toggle_ids = set(doc["uiToggleIds"])
    assert toggle_ids, "catalogUiToggles.json uiToggleIds must not be empty"

    panel_live_ids = {
        row["id"]
        for row in platform_catalog()["layers"]
        if _requires_layers_panel_toggle(row)
    }
    missing = sorted(panel_live_ids - toggle_ids)
    assert not missing, (
        "live LayersPanel catalog layer(s) have no UI toggle in "
        f"frontend/lib/catalogUiToggles.json: {missing}"
    )


def test_ui_toggles_are_known_catalog_ids():
    """Extra toggles are OK only if they still name a catalog layer (any status)."""
    doc = json.loads(TOGGLES_PATH.read_text(encoding="utf-8"))
    toggle_ids = set(doc["uiToggleIds"])
    catalog_ids = {row["id"] for row in platform_catalog()["layers"]}
    unknown = sorted(toggle_ids - catalog_ids)
    assert not unknown, f"UI toggles reference unknown catalog ids: {unknown}"


def test_withheld_public_agr_layers_still_toggled():
    """agr_value / cell_grid stay in the panel as honest unavailable toggles."""
    doc = json.loads(TOGGLES_PATH.read_text(encoding="utf-8"))
    toggle_ids = set(doc["uiToggleIds"])
    for layer_id in ("agr_value", "cell_grid"):
        assert layer_id in toggle_ids


def test_ledger_mapped_live_layers_skip_panel_toggles():
    """New ledger-frame / ledger-row layers must not appear in LayersPanel toggles."""
    doc = json.loads(TOGGLES_PATH.read_text(encoding="utf-8"))
    toggle_ids = set(doc["uiToggleIds"])
    ledger_live = [
        row
        for row in platform_catalog()["layers"]
        if row.get("status") == "live"
        and (row.get("ledger_role") or row.get("ui_surface") == "ledger")
    ]
    assert ledger_live, "expected at least one ledger-mapped live catalog layer"
    leaked = sorted(row["id"] for row in ledger_live if row["id"] in toggle_ids)
    assert not leaked, (
        "ledger-mapped live layers must not have LayersPanel toggles: "
        f"{leaked}"
    )
