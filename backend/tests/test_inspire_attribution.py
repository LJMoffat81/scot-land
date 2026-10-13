"""Confirmed RoS/OS INSPIRE attribution wording (shapes only; OGL v3)."""

from __future__ import annotations

from layers.cadastral import (
    OGL_V3_LICENCE_PHRASE,
    OGL_V3_URL,
    format_ros_os_attribution,
    harvest_year_from_vintage,
    parcel_source_meta,
)


def test_confirmed_attribution_wording_and_harvest_year():
    assert format_ros_os_attribution(2026) == (
        "© Crown copyright. Reproduced with the permission of Registers of Scotland. "
        "Contains OS data © Crown copyright and database right 2026."
    )
    assert harvest_year_from_vintage("2026-10-12") == 2026
    assert harvest_year_from_vintage("live-WMS", fallback=2026) == 2026


def test_parcel_source_meta_uses_ogl_v3_only():
    parcel_source_meta.cache_clear()
    meta = parcel_source_meta()
    assert meta["attribution"] == format_ros_os_attribution(meta["harvest_year"])
    assert meta["licence_url"] == OGL_V3_URL
    assert meta["licence_phrase"] == OGL_V3_LICENCE_PHRASE
    assert "2017" not in meta["licence_url"]
    assert "end-user" not in meta["licence_url"].lower()
    assert meta["publication_status"] == "ok"
