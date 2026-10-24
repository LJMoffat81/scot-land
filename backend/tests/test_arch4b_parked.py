"""ARCH-4b: Parked non-official / derived Batch B layers and official-only proxy/registry guards."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from layers.parked_check import (
    PARKED_YAML,
    ParkedGuardError,
    check_parked_guards,
    load_parked_sources,
    main,
)
from spatial.context_tiles import (
    _ALLOWED_HOSTS,
    RASTER,
    TRANSPARENT_PNG,
    fetch_context_tile,
    raster_request_url,
)


def _valid_parked_dict() -> dict[str, dict[str, str]]:
    return {
        sid: {
            "kind": "context_raster"
            if sid
            in {
                "sea-12nm",
                "marine-regions",
                "scottish-zone",
                "harbours",
                "wind-plan",
            }
            else "postgis_overlay",
            "audit_verdict": "NOT-OFFICIAL",
            "park_reason": "contractor-host"
            if sid
            in {
                "sea-12nm",
                "marine-regions",
                "scottish-zone",
                "harbours",
                "wind-plan",
            }
            else "derived-geometry",
            "summary": f"Summary for {sid}",
            "official_replacement": f"Replacement for {sid}",
        }
        for sid in (
            "sea-12nm",
            "marine-regions",
            "scottish-zone",
            "harbours",
            "wind-plan",
            "community_ownership",
            "public_land",
            "map_builtup_mask",
        )
    }


def test_real_parked_manifest_and_guards_pass() -> None:
    parked = load_parked_sources(PARKED_YAML)
    assert len(parked) == 8
    summary = check_parked_guards()
    assert summary["ok"] is True
    assert summary["parked_count"] == 8
    assert summary["active_raster_ids"] == [
        "data-zones",
        "localities",
        "settlements",
        "urban-rural",
        "woodland",
    ]
    assert "msmap1.atkinsgeospatial.com" not in _ALLOWED_HOSTS


@pytest.mark.parametrize(
    "parked_id",
    [
        "sea-12nm",
        "marine-regions",
        "scottish-zone",
        "harbours",
        "wind-plan",
    ],
)
def test_parked_atkins_rasters_removed_and_return_transparent_png(
    parked_id: str,
) -> None:
    assert parked_id not in RASTER
    assert raster_request_url(parked_id, 6, 31, 20) is None
    assert fetch_context_tile(parked_id, 6, 31, 20) == TRANSPARENT_PNG


def test_cli_passes(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["parked_count"] == 8


def test_cli_returns_1_on_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["--parked-file", str(tmp_path / "missing.yaml")])
    assert rc == 1
    assert "PARKED: file not found:" in capsys.readouterr().err


@pytest.mark.parametrize("bad_path", [None, True, False, 123, 1.5, [], {}])
def test_load_parked_sources_rejects_bad_path_type(bad_path: Any) -> None:
    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: path must be a Path or str$",
    ):
        load_parked_sources(bad_path)


def test_load_parked_sources_rejects_missing_empty_and_invalid_yaml(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: file not found: ",
    ):
        load_parked_sources(tmp_path / "nope.yaml")

    empty = tmp_path / "empty.yaml"
    empty.write_text("   \n", encoding="utf-8")
    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: file is empty: ",
    ):
        load_parked_sources(empty)

    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("parked_sources: [unterminated\n", encoding="utf-8")
    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: invalid YAML: ",
    ):
        load_parked_sources(bad_yaml)


@pytest.mark.parametrize(
    "bad_root",
    [
        "[]\n",
        "true\n",
        "123\n",
        '"str"\n',
        "other_key: {}\n",
        "parked_sources: {}\nextra: 1\n",
    ],
)
def test_load_parked_sources_rejects_bad_root(
    tmp_path: Path, bad_root: str
) -> None:
    p = tmp_path / "p.yaml"
    p.write_text(bad_root, encoding="utf-8")
    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: root must be a mapping with key 'parked_sources'$",
    ):
        load_parked_sources(p)


@pytest.mark.parametrize("bad_ps", [None, True, 123, "x", [], {}])
def test_load_parked_sources_rejects_empty_or_non_mapping_parked_sources(
    tmp_path: Path, bad_ps: Any
) -> None:
    p = tmp_path / "p.yaml"
    p.write_text(
        yaml.safe_dump({"parked_sources": bad_ps}), encoding="utf-8"
    )
    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: parked_sources must be a non-empty mapping$",
    ):
        load_parked_sources(p)


@pytest.mark.parametrize("bad_entry", [None, True, 123, "x", []])
def test_load_parked_sources_rejects_non_mapping_entry(
    tmp_path: Path, bad_entry: Any
) -> None:
    data = _valid_parked_dict()
    data["sea-12nm"] = bad_entry  # type: ignore[assignment]
    p = tmp_path / "p.yaml"
    p.write_text(
        yaml.safe_dump({"parked_sources": data}), encoding="utf-8"
    )
    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: sea-12nm: entry must be a mapping$",
    ):
        load_parked_sources(p)


@pytest.mark.parametrize(
    "field",
    [
        "kind",
        "audit_verdict",
        "park_reason",
        "summary",
        "official_replacement",
    ],
)
@pytest.mark.parametrize("bad_val", [None, True, 123, "", "   ", [], {}])
def test_load_parked_sources_rejects_bad_field_value(
    tmp_path: Path, field: str, bad_val: Any
) -> None:
    data = _valid_parked_dict()
    data["sea-12nm"][field] = bad_val  # type: ignore[assignment]
    p = tmp_path / "p.yaml"
    p.write_text(
        yaml.safe_dump({"parked_sources": data}), encoding="utf-8"
    )
    with pytest.raises(
        ParkedGuardError,
        match=rf"^PARKED: sea-12nm: {field} must be a non-empty string$",
    ):
        load_parked_sources(p)


def test_load_parked_sources_rejects_unknown_key_and_enums_and_missing_id(
    tmp_path: Path,
) -> None:
    p = tmp_path / "p.yaml"

    data = _valid_parked_dict()
    data["sea-12nm"]["extra_field"] = "x"
    p.write_text(yaml.safe_dump({"parked_sources": data}), encoding="utf-8")
    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: sea-12nm: unknown key 'extra_field'$",
    ):
        load_parked_sources(p)

    data = _valid_parked_dict()
    data["sea-12nm"]["kind"] = "unknown_kind"
    p.write_text(yaml.safe_dump({"parked_sources": data}), encoding="utf-8")
    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: sea-12nm: invalid kind 'unknown_kind'$",
    ):
        load_parked_sources(p)

    data = _valid_parked_dict()
    data["sea-12nm"]["audit_verdict"] = "OFFICIAL"
    p.write_text(yaml.safe_dump({"parked_sources": data}), encoding="utf-8")
    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: sea-12nm: invalid audit_verdict 'OFFICIAL'$",
    ):
        load_parked_sources(p)

    data = _valid_parked_dict()
    data["sea-12nm"]["park_reason"] = "other"
    p.write_text(yaml.safe_dump({"parked_sources": data}), encoding="utf-8")
    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: sea-12nm: invalid park_reason 'other'$",
    ):
        load_parked_sources(p)

    data = _valid_parked_dict()
    del data["wind-plan"]
    p.write_text(yaml.safe_dump({"parked_sources": data}), encoding="utf-8")
    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: missing required parked id 'wind-plan'$",
    ):
        load_parked_sources(p)


def test_check_parked_guards_rejects_bad_container_types() -> None:
    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: reg, raster_specs, feature_specs must be dicts and allowed_hosts a set$",
    ):
        check_parked_guards(entries=[])  # type: ignore[arg-type]


def test_check_parked_guards_rejects_forbidden_host_and_parked_leaks() -> None:
    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: forbidden host 'msmap1\.atkinsgeospatial\.com' in allowed_hosts$",
    ):
        check_parked_guards(
            allowed_hosts=frozenset({"msmap1.atkinsgeospatial.com"})
        )

    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: parked source 'community_ownership' must not appear in registry$",
    ):
        check_parked_guards(
            entries={"community-ownership": {"source": {"url": "https://example.test"}}}
        )

    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: parked source 'sea-12nm' must not appear in RASTER$",
    ):
        check_parked_guards(raster_specs={"sea-12nm": object()})

    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: parked source 'public_land' must not appear in FEATURES$",
    ):
        check_parked_guards(feature_specs={"public-land": object()})

    with pytest.raises(
        ParkedGuardError,
        match=r"^PARKED: registry bad-layer: forbidden upstream host in 'https://api\.postcodes\.io/postcodes'$",
    ):
        check_parked_guards(
            entries={
                "bad-layer": {
                    "source": {"url": "https://api.postcodes.io/postcodes"}
                }
            }
        )
