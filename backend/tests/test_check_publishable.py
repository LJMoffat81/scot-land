"""scripts/check_publishable.py: the public-repo guard catches what it must, passes clean data."""

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[2] / "scripts" / "check_publishable.py"


def _guard():
    spec = importlib.util.spec_from_file_location("check_publishable", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _repo(tmp_path, files: dict[str, str]):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", "."], check=True)


def _problems(tmp_path):
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        g = _guard()
        return g.check(g.tracked())
    finally:
        os.chdir(cwd)


def test_clean_repo_passes(tmp_path):
    _repo(tmp_path, {
        "data/processed/x/manifest.csv": "file,publish_level\nok.csv,public_zone\n",
        "data/processed/x/ok.csv": "code,vintage,streetlight_share,n_res_uprn,share_res_uprn_in_parcels,"
                                   "res_uprn_exceeds_dwellings\nS01006506,2011,0.1,3,0.5,False\n",
        "etl/gis/build_dz_detached_plot_bands.py": "# code may name it\n",
    })
    assert _problems(tmp_path) == []


@pytest.mark.parametrize("files, needle", [
    ({"data/processed/x/manifest.csv": "file,publish_level\ns.csv,internal\n",
      "data/processed/x/s.csv": "code\n"}, "publish_level=internal"),
    ({"etl/gis/raw/download.zip": "x"}, "raw/ folder"),
    ({"data/processed/x/a.csv": "\ufeffcode,Postcode\n"}, "Postcode"),
    ({"data/processed/x/a.csv": "id,UPRN\n"}, "UPRN"),
    ({"data/processed/x/a.tsv": "id\taddress_line1\n"}, "address_line1"),
    ({"data/spatial_hub/parcels.txt": "x"}, "Spatial Hub"),
    ({"data/processed/gis/svdls_sites.gpkg": "x"}, "GeoPackage"),
    ({"data/processed/gis/hls_sites.gpkg": "x"}, "GeoPackage"),
    ({"data/processed/gis/internal/dz_svdls_rollup_with_inspire.csv": "code\n"}, "internal/ folder"),
    ({"data/processed/gis/dz_svdls_rollup_with_inspire.csv": "code\n"}, "INSPIRE"),
    ({"data/processed/gis/manifest.csv": "file,publish_level\nany_name.csv,internal\n",
      "data/processed/gis/any_name.csv": "code,vintage\n"}, "publish_level=internal"),
    ({"frontend/public/tiles/parcels.pmtiles": "x"}, "tile"),
    ({"data/processed/gis/parcel_outlines.geojson": "{}"}, "parcel"),
    ({"data/processed/x/a.csv": "code,res_uprn\n"}, "res_uprn"),
])
def test_guard_fails(tmp_path, files, needle):
    problems = _problems(tmp_path) if _repo(tmp_path, files) is None else None
    assert any(needle in p for p in problems), problems


def test_publish_level_decides_not_the_file_name(tmp_path):
    """dz_detached_plot_bands.csv is public_zone (Laurie's ruling: RoS INSPIRE is OGL v3): it passes."""
    _repo(tmp_path, {
        "data/processed/gis/manifest.csv": "file,publish_level\ndz_detached_plot_bands.csv,public_zone\n",
        "data/processed/gis/dz_detached_plot_bands.csv": "code,vintage,all_ages_share_lt005\nS01006506,2011,0.1\n",
    })
    assert _problems(tmp_path) == []


def test_this_repo_passes():
    root = GUARD.parents[1]
    if not (root / ".git").exists():
        pytest.skip("not a git checkout")
    r = subprocess.run(["python3", str(GUARD)], cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_extra_and_unknown_manifest_columns_are_tolerated(tmp_path):
    _repo(tmp_path, {
        "data/processed/gis/manifest.csv": "file,publish_level,source_year,anything_new\nz.csv,public_zone,,x\n",
        "data/processed/gis/z.csv": "code,vintage,job_access\nS01006506,2011,1.0\n",
    })
    assert _problems(tmp_path) == []


def test_guard_catches_ungated_preview_routes(tmp_path):
    """Preview routes (*-panel / *-card) must gate via if (!internalUiEnabled()) notFound()."""
    problems = _problems(tmp_path) if _repo(tmp_path, {
        "frontend/app/tax-scenario-panel/page.tsx": "export default function Page() { return null }\n",
    }) is None else None
    assert any("tax-scenario-panel" in p and "gated" in p for p in problems), problems

    _repo(tmp_path / "gated", {
        "frontend/app/tax-scenario-panel/layout.tsx": (
            'import { notFound } from "next/navigation";\n'
            'import { internalUiEnabled } from "@/lib/internalUi";\n'
            "export default function L({ children }) {\n"
            "  if (!internalUiEnabled()) notFound();\n"
            "  return children;\n"
            "}\n"
        ),
        "frontend/app/tax-scenario-panel/page.tsx": "export default function Page() { return null }\n",
        "frontend/app/ledger-panel/layout.tsx": (
            'import { notFound } from "next/navigation";\n'
            'import { internalUiEnabled } from "@/lib/internalUi";\n'
            "export default function L({ children }) {\n"
            "  if (!internalUiEnabled()) notFound();\n"
            "  return children;\n"
            "}\n"
        ),
        "frontend/app/ledger-panel/page.tsx": "export default function Page() { return null }\n",
        "frontend/app/place-card/layout.tsx": (
            'import { notFound } from "next/navigation";\n'
            'import { internalUiEnabled } from "@/lib/internalUi";\n'
            "export default function L({ children }) {\n"
            "  if (!internalUiEnabled()) notFound();\n"
            "  return children;\n"
            "}\n"
        ),
        "frontend/app/place-card/page.tsx": "export default function Page() { return null }\n",
    })
    assert _problems(tmp_path / "gated") == []


def test_guard_discovers_preview_routes_without_fixed_list(tmp_path):
    """A new *-panel route is discovered automatically (no PREVIEW_APP_ROUTES allow-list)."""
    problems = _problems(tmp_path) if _repo(tmp_path, {
        "frontend/app/new-tools-panel/page.tsx": "export default function Page() { return null }\n",
    }) is None else None
    assert any("new-tools-panel" in p and "gated" in p for p in problems), problems


def test_guard_rejects_layout_that_only_mentions_gate_words(tmp_path):
    """Commenting the identifiers is not a gate — must call if (!internalUiEnabled()) notFound()."""
    problems = _problems(tmp_path) if _repo(tmp_path, {
        "frontend/app/ledger-panel/layout.tsx": (
            "// TODO: use internalUiEnabled and notFound\n"
            "export default function L({ children }) { return children; }\n"
        ),
        "frontend/app/ledger-panel/page.tsx": "export default function Page() { return null }\n",
    }) is None else None
    assert any("ledger-panel" in p and "gated" in p for p in problems), problems


def test_guard_rejects_commented_out_fake_gate(tmp_path):
    """A commented-out if (!internalUiEnabled()) notFound() must not count as gated."""
    problems = _problems(tmp_path) if _repo(tmp_path, {
        "frontend/app/ledger-panel/layout.tsx": (
            'import { notFound } from "next/navigation";\n'
            'import { internalUiEnabled } from "@/lib/internalUi";\n'
            "export default function L({ children }) {\n"
            "  // if (!internalUiEnabled()) notFound();\n"
            "  return children;\n"
            "}\n"
        ),
        "frontend/app/ledger-panel/page.tsx": "export default function Page() { return null }\n",
    }) is None else None
    assert any("ledger-panel" in p and "gated" in p for p in problems), problems

    problems_block = _problems(tmp_path / "block") if _repo(tmp_path / "block", {
        "frontend/app/tools-panel/layout.tsx": (
            'import { notFound } from "next/navigation";\n'
            'import { internalUiEnabled } from "@/lib/internalUi";\n'
            "export default function L({ children }) {\n"
            "  /* if (!internalUiEnabled()) notFound(); */\n"
            "  return children;\n"
            "}\n"
        ),
        "frontend/app/tools-panel/page.tsx": "export default function Page() { return null }\n",
    }) is None else None
    assert any("tools-panel" in p and "gated" in p for p in problems_block), problems_block


def test_guard_catches_internal_component_route_without_panel_suffix(tmp_path):
    """A page importing Internal* is a preview even when the route does not end in -panel/-card."""
    problems = _problems(tmp_path) if _repo(tmp_path, {
        "frontend/app/secret-tools/page.tsx": (
            'import InternalTaxScenarioView from "@/components/InternalTaxScenarioView";\n'
            "export default function Page() { return <InternalTaxScenarioView zones={[]} scenarioId=\"S2\" />; }\n"
        ),
    }) is None else None
    assert any("secret-tools" in p and "gated" in p for p in problems), problems


def test_guard_forbids_public_agr_property_columns(tmp_path):
    """Tracked tabular data must not ship forbidden modelled AGR £ property names."""
    g = _guard()
    assert "annual_ground_rent_plot_gbp" in g.FORBIDDEN_PUBLIC_AGR_PROPERTIES
    assert "siteRentalPerSqmGbp" in g.FORBIDDEN_PUBLIC_AGR_PROPERTIES
    assert "vacantFullAgrGbp" in g.FORBIDDEN_PUBLIC_AGR_PROPERTIES
    for prop in sorted(g.FORBIDDEN_PUBLIC_AGR_PROPERTIES):
        problems = _problems(tmp_path / prop) if _repo(tmp_path / prop, {
            "data/processed/x/a.csv": f"code,{prop}\nS01006506,1\n",
        }) is None else None
        assert any("forbidden public AGR" in p and prop in p for p in problems), (prop, problems)


@pytest.mark.parametrize("relpath", [
    "data/processed/x/a.json",
    "data/processed/x/a.geojson",
    "frontend/public/a.json",
    "frontend/public/layer.geojson",
])
def test_guard_forbids_public_agr_keys_in_json_geojson(tmp_path, relpath):
    """Tracked JSON/GeoJSON under data/processed and frontend/public must not ship AGR £ keys."""
    g = _guard()
    for prop in ("siteRentalPerSqmGbp", "vacant_full_agr_gbp"):
        problems = _problems(tmp_path / prop) if _repo(tmp_path / prop, {
            relpath: (
                '{"type":"FeatureCollection","features":[{"type":"Feature",'
                f'"properties":{{"code":"S12000049","{prop}":1}},"geometry":null}}]}}'
            ),
        }) is None else None
        assert any("forbidden public AGR" in p and prop in p for p in problems), (prop, problems)


def test_guard_json_scan_skips_code_outside_data_prefixes(tmp_path):
    """Code JSON outside data/processed and frontend/public may name forbidden keys."""
    _repo(tmp_path, {
        "frontend/lib/catalogUiToggles.json": '{"siteRentalPerSqmGbp": true}\n',
        "backend/tests/fixtures/x.json": '{"vacantFullAgrGbp": 1}\n',
    })
    assert _problems(tmp_path) == []


def test_guard_methods_internal_report_may_hold_forbidden_money_keys(tmp_path):
    """Additive: methods_code_*/**/report.json with publish_level=internal may carry £ keys."""
    g = _guard()
    assert "scotland_total_central_gbp_before" in g.FORBIDDEN_PUBLIC_AGR_PROPERTIES
    assert "scotland_total_central_gbp_after" in g.FORBIDDEN_PUBLIC_AGR_PROPERTIES
    _repo(tmp_path, {
        "data/processed/methods_code_1/pr1/report.json": (
            '{"publish_level":"internal",'
            '"scotland_total_central_gbp_before":1,'
            '"scotland_total_central_gbp_after":2}\n'
        ),
    })
    assert _problems(tmp_path) == []


def test_guard_methods_report_without_internal_level_still_forbidden(tmp_path):
    """Carve-out requires publish_level=internal — missing level stays blocked."""
    problems = _problems(tmp_path) if _repo(tmp_path, {
        "data/processed/methods_code_1/pr1/report.json": (
            '{"scotland_total_central_gbp_before":1}\n'
        ),
    }) is None else None
    assert any("scotland_total_central_gbp_before" in p for p in problems), problems


def test_guard_methods_money_keys_still_forbidden_outside_methods_path(tmp_path):
    """New methods £ keys remain forbidden on ordinary public processed JSON."""
    problems = _problems(tmp_path) if _repo(tmp_path, {
        "data/processed/other/a.json": '{"scotland_total_central_gbp_after":1}\n',
    }) is None else None
    assert any("scotland_total_central_gbp_after" in p for p in problems), problems


def test_forbidden_public_agr_properties_match_publication_rules():
    """stdlib guard list stays in lock-step with georgist.publication_rules."""
    from georgist.publication_rules import FORBIDDEN_PUBLIC_AGR_PROPERTIES as runtime

    g = _guard()
    assert g.FORBIDDEN_PUBLIC_AGR_PROPERTIES == runtime
    assert "siteRentalPerSqmGbp" in runtime
    assert "vacantFullAgrGbp" in runtime
    assert "scotland_total_central_gbp_before" in runtime
    assert "scotland_total_central_gbp_after" in runtime


def test_guard_forbids_model_fill_dz2022_in_public_json(tmp_path):
    """Additive coverage: DZ2022 fill token must not appear in public JSON keys or values."""
    g = _guard()
    assert "model_fill_dz2022" in g.FORBIDDEN_PUBLIC_FILL_TOKENS
    problems = _problems(tmp_path) if _repo(tmp_path, {
        "frontend/public/leak.geojson": (
            '{"type":"FeatureCollection","features":[{"type":"Feature",'
            '"properties":{"model_fill_dz2022":1},"geometry":null}]}'
        ),
    }) is None else None
    assert any("model_fill_dz2022" in p for p in problems), problems

    problems_val = _problems(tmp_path / "val") if _repo(tmp_path / "val", {
        "frontend/public/tags.json": (
            '{"proxy_tags":["research_estimate","model_fill_dz2022"]}\n'
        ),
    }) is None else None
    assert any("model_fill_dz2022" in p and "value" in p for p in problems_val), problems_val


def test_guard_forbids_banned_public_route_wording(tmp_path):
    """Additive: £0 / market+proxy / nested prose banned on public route sources."""
    g = _guard()
    assert "£0" in g.FORBIDDEN_PUBLIC_ROUTE_PHRASES
    assert "market+proxy" in g.FORBIDDEN_PUBLIC_ROUTE_PHRASES
    assert ".env" in g.FORBIDDEN_PUBLIC_ROUTE_PHRASES
    assert "nested" in g.FORBIDDEN_PUBLIC_ROUTE_PROSE_WORDS

    problems = _problems(tmp_path) if _repo(tmp_path, {
        "frontend/app/developers/page.tsx": (
            'export default function Page() {\n'
            '  return <p>Constraints are £0 and headline is market+proxy with nested 1a. '
            'Set .env for the key.</p>;\n'
            '}\n'
        ),
    }) is None else None
    assert any("£0" in p for p in problems), problems
    assert any("market+proxy" in p for p in problems), problems
    assert any("nested" in p for p in problems), problems
    assert any(".env" in p for p in problems), problems

    # Machine boolean key ``nested`` alone is allowed (not visitor prose).
    clean = _problems(tmp_path / "ok") if _repo(tmp_path / "ok", {
        "backend/layers/ledger.py": (
            'CONSTRAINT_RULE = "Constraint: changes best use, adds no value"\n'
            'ROW = {"id": "1a", "nested": True, "tag": "already_included"}\n'
        ),
    }) is None else None
    assert not any("forbidden public-route wording" in p for p in clean), clean
