"""No database => explicit 503 with a reason. Never zeros, never a silent fallback."""

import socket

import pytest

from georgist import db
from georgist.aggregator import aggregator

VALID = {"lat": 55.95, "lng": -3.19, "zone_id": "S01008677"}


def _closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_health_ok_with_db_unavailable(client):
    """HEALTH-TRIM: /health is status+version only; DB/router honesty stays elsewhere."""
    from api.main import ROUTER_STATUS

    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert set(body) == {"status", "version"}
    assert db.db_status()["status"] == "unavailable"
    assert db.db_status()["reason"] == "not_configured"
    assert ROUTER_STATUS["api.wealth_routes"]["loaded"] is True


def test_wealth_is_503_without_db(client):
    r = client.get("/georgist/wealth", params=VALID)
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["error"] == "wealth_database_unavailable"
    assert detail["reason"] == "not_configured"
    assert "wealth" not in r.json()


def test_surface_layer_is_503_without_db(client):
    r = client.get("/layers/georgist/surface-rent")
    assert r.status_code == 503
    assert r.json()["detail"]["reason"] == "not_configured"


def test_unreachable_db_is_503_and_password_scrubbed(client, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"postgresql://someone:s3cr3t-pw@127.0.0.1:{_closed_port()}/nowhere")
    monkeypatch.setattr(db, "CONNECT_TIMEOUT_S", 1)
    r = client.get("/georgist/wealth", params=VALID)
    assert r.status_code == 503
    assert r.json()["detail"]["reason"] == "connection_failed"
    assert "s3cr3t-pw" not in r.text
    status = db.db_status()
    assert status["status"] == "unavailable"
    assert status["reason"] == "connection_failed"
    assert "s3cr3t-pw" not in str(status)
    h = client.get("/health")
    assert h.status_code == 200
    assert set(h.json()) == {"status", "version"}
    assert "s3cr3t-pw" not in h.text


def test_aggregator_raises_instead_of_returning_zeros():
    with pytest.raises(db.DatabaseUnavailable) as exc:
        aggregator.get_total_wealth("S01008677", 2011, 55.95, -3.19)
    assert exc.value.reason == "not_configured"


def test_missing_table_is_schema_missing(monkeypatch, client):
    import psycopg2

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, *a, **k):
            raise psycopg2.errors.UndefinedTable('relation "surface_rent_dz" does not exist')

    class FakeConn:
        def cursor(self, cursor_factory=None):
            return FakeCursor()

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setenv("DATABASE_URL", "postgresql://x@127.0.0.1/x")
    monkeypatch.setattr(db, "connect", lambda: FakeConn())
    r = client.get("/georgist/wealth", params=VALID)
    assert r.status_code == 503
    assert r.json()["detail"]["reason"] == "schema_missing"


def test_scrub_removes_passwords():
    assert "pw" not in db._scrub("postgresql://u:pw@h/db failed")
    assert "hunter2" not in db._scrub("password=hunter2 host=x")


def test_pg_vars_count_as_configured(monkeypatch):
    assert not db.database_configured()
    monkeypatch.setenv("PGHOST", "db")
    assert not db.database_configured()  # PGDATABASE also required
    monkeypatch.setenv("PGDATABASE", "scotland_wealth")
    assert db.database_configured()
