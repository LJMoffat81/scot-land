"""National open-layer statistics for the public preview API.

These endpoints were documented from the grok.com / X session in
docs/OPEN_LAYERS.md. They query the same public FeatureServers as the map
overlays. Figures are survey/overlay totals, not a rates bill or title.
"""

from __future__ import annotations

from typing import Any

import httpx

from layers.council_metrics import build_council_metrics_geojson
from layers.platform import platform_catalog
from layers.public_land import ATTRIBUTION as PUBLIC_ATTRIBUTION
from layers.public_land import BODIES, DASHBOARD_URL, FEATURE_URL as PUBLIC_URL
from layers.vdl import ATTRIBUTION as VDL_ATTRIBUTION
from layers.vdl import FEATURE_URL as VDL_URL
from layers.vdl import REGISTER_URL
from layers.vdl import by_council_hectares

TIMEOUT = 12.0


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT)


def _stats(
    url: str,
    group_field: str,
    count_field: str,
    sum_field: str,
    sum_name: str = "total",
) -> list[dict[str, Any]]:
    params = {
        "where": "1=1",
        "groupByFieldsForStatistics": group_field,
        "outStatistics": (
            f'[{{"statisticType":"count","onStatisticField":"{count_field}",'
            f'"outStatisticFieldName":"n"}},'
            f'{{"statisticType":"sum","onStatisticField":"{sum_field}",'
            f'"outStatisticFieldName":"{sum_name}"}}]'
        ),
        "f": "json",
    }
    with _client() as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    rows = []
    for feat in payload.get("features") or []:
        attrs = feat.get("attributes") or {}
        rows.append(attrs)
    return rows


def public_land_json() -> dict[str, Any]:
    try:
        rows = _stats(PUBLIC_URL, "Organisation", "OBJECTID", "Area_Ha", "ha")
    except (httpx.HTTPError, ValueError) as exc:
        return {"ok": False, "error": str(exc), "bodies": []}
    bodies = []
    total_ha = 0.0
    for row in rows:
        ha = float(row.get("ha") or 0)
        total_ha += ha
        bodies.append(
            {
                "organisation": row.get("Organisation"),
                "parcels": int(row.get("n") or 0),
                "hectares": round(ha, 1),
            }
        )
    bodies.sort(key=lambda b: b["hectares"], reverse=True)
    return {
        "ok": True,
        "note": (
            "Five national bodies only, non-exhaustive. Not local-authority land. "
            "Not a legal title."
        ),
        "bodiesExpected": list(BODIES),
        "bodies": bodies,
        "totalHectares": round(total_ha, 1),
        "source": PUBLIC_ATTRIBUTION,
        "map_url": DASHBOARD_URL,
    }


def vdl_json() -> dict[str, Any]:
    try:
        rows = _stats(VDL_URL, "owner_1", "FID", "Shape__Area", "sqm")
    except (httpx.HTTPError, ValueError) as exc:
        return {"ok": False, "error": str(exc), "byOwnerClass": []}
    classes = []
    total_ha = 0.0
    for row in rows:
        ha = float(row.get("sqm") or 0) / 10_000.0
        total_ha += ha
        classes.append(
            {
                "ownerClass": row.get("owner_1"),
                "sites": int(row.get("n") or 0),
                "hectares": round(ha, 2),
            }
        )
    classes.sort(key=lambda c: c["hectares"], reverse=True)
    return {
        "ok": True,
        "note": "SVDLS owner class is a survey field, not a title.",
        "byOwnerClass": classes,
        "totalHectares": round(total_ha, 2),
        "source": VDL_ATTRIBUTION,
        "register_url": REGISTER_URL,
    }


def vdl_councils_json(scenario: str = "full_agr") -> dict[str, Any]:
    vacant = by_council_hectares()
    geo = build_council_metrics_geojson(scenario)
    councils = []
    for feat in geo.get("features") or []:
        props = feat.get("properties") or {}
        code = str(props.get("code") or "")
        vdl = vacant.get(code) or {"vacantHa": 0.0, "vacantSites": 0}
        rent = float(props.get("site_rental_per_sqm_gbp") or 0)
        vacant_ha = float(vdl["vacantHa"])
        vacant_agr = round(vacant_ha * 10_000.0 * rent, 0)
        councils.append(
            {
                "code": code,
                "name": props.get("name"),
                "vacantHa": vacant_ha,
                "vacantSites": vdl["vacantSites"],
                "siteRentalPerSqmGbp": rent,
                "vacantFullAgrGbp": vacant_agr,
            }
        )
    councils.sort(key=lambda c: c["vacantFullAgrGbp"], reverse=True)
    return {
        "ok": True,
        "scenario": scenario,
        "note": (
            "Illustrative residual on SVDLS hectares using council-flat rent per m². "
            "Not a bill."
        ),
        "councils": councils,
        "source": VDL_ATTRIBUTION,
    }


def roll_json(scenario: str = "full_agr") -> dict[str, Any]:
    vacant = by_council_hectares()
    geo = build_council_metrics_geojson(scenario)
    rows = []
    for feat in geo.get("features") or []:
        props = dict(feat.get("properties") or {})
        code = str(props.get("code") or "")
        vdl = vacant.get(code) or {"vacantHa": 0.0, "vacantSites": 0}
        rent = float(props.get("site_rental_per_sqm_gbp") or 0)
        vacant_ha = float(vdl["vacantHa"])
        props["vacantHa"] = vacant_ha
        props["vacantSites"] = vdl["vacantSites"]
        props["vacantFullAgrGbp"] = round(vacant_ha * 10_000.0 * rent, 0)
        rows.append(props)
    rows.sort(key=lambda r: r.get("name") or "")
    return {
        "ok": True,
        "scenario": scenario,
        "count": len(rows),
        "councils": rows,
        "note": (
            "32-council AGR roll with SVDLS vacant hectares and illustrative residual. "
            "Research estimate, not a rates bill."
        ),
    }


def catalog_json() -> dict[str, Any]:
    return platform_catalog()
