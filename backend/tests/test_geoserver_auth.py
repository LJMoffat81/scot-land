"""Spatial Hub GeoServer authkey wiring (SPATIALHUB_AUTHKEY)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from etl import ingest_hla_sites as hla_ingest
from layers.hla import _unloaded_error, hla_source_meta
from spatial import geoserver_auth as gauth

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / "backend" / ".env.example"
COMPOSE_HOME = REPO_ROOT / "docker-compose.home.yml"
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"


def test_env_example_has_blank_spatialhub_authkey_placeholder():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "SPATIALHUB_AUTHKEY=" in text
    # Blank placeholder only — never a committed real key.
    for line in text.splitlines():
        if line.startswith("SPATIALHUB_AUTHKEY="):
            assert line.strip() == "SPATIALHUB_AUTHKEY="
            break
    else:
        raise AssertionError("SPATIALHUB_AUTHKEY= missing from backend/.env.example")


def test_compose_home_passes_spatialhub_authkey_from_env():
    text = COMPOSE_HOME.read_text(encoding="utf-8")
    assert "SPATIALHUB_AUTHKEY: ${SPATIALHUB_AUTHKEY:-}" in text


def test_sources_yaml_hla_declares_api_env():
    sources = yaml.safe_load(SOURCES_PATH.read_text(encoding="utf-8"))
    hla = sources["hla"]
    assert hla["api_env"] == "SPATIALHUB_AUTHKEY"
    gaps = " ".join(hla["gaps"]).lower()
    assert "not loaded yet" in gaps
    assert "spatialhub_authkey" in gaps


def test_authkey_missing_is_not_configured(monkeypatch):
    monkeypatch.delenv("SPATIALHUB_AUTHKEY", raising=False)
    assert gauth.authkey() is None
    assert gauth.is_configured() is False
    assert gauth.wfs_auth_params() == {}
    assert gauth.not_loaded_message("Housing land audit") == (
        "Housing land audit is not loaded yet"
    )


def test_authkey_blank_treated_as_missing(monkeypatch):
    monkeypatch.setenv("SPATIALHUB_AUTHKEY", "   ")
    assert gauth.authkey() is None
    assert gauth.is_configured() is False


def test_authkey_present_adds_wfs_param(monkeypatch):
    monkeypatch.setenv("SPATIALHUB_AUTHKEY", "test-key-not-real")
    assert gauth.is_configured() is True
    assert gauth.wfs_auth_params() == {"authkey": "test-key-not-real"}
    url = gauth.with_wfs_auth(
        "https://geo.spatialhub.scot/geoserver/sh_hls/wfs",
        extra_params={"service": "WFS", "request": "GetFeature"},
    )
    assert "authkey=test-key-not-real" in url
    assert "service=WFS" in url
    assert "request=GetFeature" in url


def _assert_visitor_safe(text: str) -> None:
    """Visitor / public-API prose must not teach operator setup."""
    lower = text.lower()
    assert "spatialhub_authkey" not in lower
    assert "python -m etl" not in lower
    assert "--from-wfs" not in lower
    # Bare ``.env`` only banned when paired with Spatial Hub auth setup.
    if ".env" in lower:
        assert "spatialhub" not in lower and "authkey" not in lower


def test_hla_unloaded_error_says_not_loaded_yet_without_key(monkeypatch):
    monkeypatch.delenv("SPATIALHUB_AUTHKEY", raising=False)
    msg = _unloaded_error()
    assert "not loaded yet" in msg
    _assert_visitor_safe(msg)


def test_hla_unloaded_error_with_key_stays_visitor_safe(monkeypatch):
    """Key present but PostGIS empty: still visitor copy only (no ETL hints)."""
    monkeypatch.setenv("SPATIALHUB_AUTHKEY", "test-key-not-real")
    msg = _unloaded_error()
    assert "not loaded yet" in msg
    _assert_visitor_safe(msg)


def test_hla_source_meta_reports_authkey_flag(monkeypatch):
    monkeypatch.delenv("SPATIALHUB_AUTHKEY", raising=False)
    hla_source_meta.cache_clear()
    meta = hla_source_meta()
    assert meta["api_env"] == "SPATIALHUB_AUTHKEY"
    assert meta["authkey_configured"] is False
    monkeypatch.setenv("SPATIALHUB_AUTHKEY", "test-key-not-real")
    hla_source_meta.cache_clear()
    assert hla_source_meta()["authkey_configured"] is True
    hla_source_meta.cache_clear()


def test_hla_public_unload_payloads_are_visitor_safe(monkeypatch):
    """query_point / query_bbox errors must not leak operator setup to visitors."""
    monkeypatch.delenv("SPATIALHUB_AUTHKEY", raising=False)
    monkeypatch.setattr("layers.hla.is_loaded", lambda: False)
    from layers.hla import query_bbox, query_point

    point = query_point(55.86, -4.26)
    assert point["ok"] is False
    assert "not loaded yet" in point["error"]
    _assert_visitor_safe(point["error"])

    bbox = query_bbox(55.84, -4.30, 55.88, -4.22)
    meta = bbox["meta"]
    assert meta["ok"] is False
    assert "not loaded yet" in meta["error"]
    _assert_visitor_safe(meta["error"])
    assert "authkey_configured" not in meta


def test_hla_public_gaps_strip_operator_setup(monkeypatch):
    """Loaded bbox meta.gaps keep honesty lines; drop SPATIALHUB/.env/etl setup."""
    monkeypatch.setattr("layers.hla.is_loaded", lambda: True)

    class _FakeCur:
        def execute(self, *_a, **_k):
            return None

        def fetchall(self):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    class _FakeConn:
        def cursor(self, *a, **k):
            return _FakeCur()

        def close(self):
            return None

    monkeypatch.setattr("layers.hla._connect", lambda: _FakeConn())
    from layers.hla import query_bbox

    bbox = query_bbox(55.84, -4.30, 55.88, -4.22)
    gaps = bbox["meta"].get("gaps") or []
    assert gaps, "visitor gaps should still list honest coverage limits"
    for gap in gaps:
        _assert_visitor_safe(gap)
    joined = " ".join(gaps).lower()
    assert "psga" in joined or "digimap" in joined or "scotlis" in joined


def test_ingest_from_wfs_without_key_exits_not_loaded_yet(monkeypatch):
    monkeypatch.delenv("SPATIALHUB_AUTHKEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        hla_ingest.fetch_wfs_geojson()
    assert "not loaded yet" in str(exc.value)
    assert "SPATIALHUB_AUTHKEY" in str(exc.value)


def test_ingest_from_wfs_pages_with_authkey(monkeypatch):
    monkeypatch.setenv("SPATIALHUB_AUTHKEY", "test-key-not-real")
    calls: list[str] = []

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *a, **k):
            pass

        def get(self, url):
            calls.append(url)
            assert "authkey=test-key-not-real" in url
            qs = parse_qs(urlsplit(url).query)
            start = int((qs.get("startIndex") or ["0"])[0])
            poly = {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            }
            if start == 0:
                feats = [
                    {
                        "type": "Feature",
                        "properties": {"hls_uid": f"HLS{i}"},
                        "geometry": poly,
                    }
                    for i in range(2)
                ]
                return _Resp(
                    {
                        "type": "FeatureCollection",
                        "features": feats,
                        "numberMatched": 3,
                        "numberReturned": 2,
                    }
                )
            return _Resp(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"hls_uid": "HLS2"},
                            "geometry": poly,
                        }
                    ],
                    "numberMatched": 3,
                    "numberReturned": 1,
                }
            )

        def close(self):
            return None

    monkeypatch.setattr(hla_ingest.httpx, "Client", _Client)
    payload = hla_ingest.fetch_wfs_geojson(page_size=2)
    assert len(payload["features"]) == 3
    assert len(calls) == 2
    assert all("authkey=test-key-not-real" in url for url in calls)
