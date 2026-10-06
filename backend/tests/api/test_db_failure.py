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
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"]["status"] == "unavailable"
    assert body["db"]["reason"] == "not_configured"
    assert body["routers"]["api.wealth_routes"]["loaded"] is True


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
    h = client.get("/health").json()
    assert h["db"]["status"] == "unavailable"
    assert h["db"]["reason"] == "connection_failed"
    assert "s3cr3t-pw" not in str(h)


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
