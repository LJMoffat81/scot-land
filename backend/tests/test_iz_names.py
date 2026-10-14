"""Official Intermediate Zone 2022 name lookup (NRS/SG, OGL v3)."""

from __future__ import annotations

from layers.iz_names import iz_name
from layers import platform as platform_mod


def test_iz2022_names_for_eh1_and_ph22_postcode_zones():
    """Spec: EH1 1YZ (S02001622 / 2022 S02002727) and PH22 1RN (S02001983 / S02003284)."""
    assert iz_name("S02002727", 2022) == "Old Town, Princes Street and Leith Street"
    assert iz_name("S02003284", 2022) == "Badenoch and Strathspey Central"
    # 2011 codes named in the brief still resolve when vintage=2011 is asked.
    assert iz_name("S02001622", 2011) == "Old Town, Princes Street and Leith Street"
    assert iz_name("S02001983", 2011) == "Badenoch and Strathspey Central"


def test_intermediate_zone_never_no_data_when_code_known(monkeypatch):
    class _Cur:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *args, **kwargs):
            return None

        def fetchone(self):
            return {"iz_code": "S02002727"}

    import georgist.db as gdb

    monkeypatch.setattr(gdb, "cursor", lambda: _Cur())

    out = platform_mod._intermediate_zone_for(
        {"code": "S01014713", "vintage": 2022, "status": "ok"}
    )
    assert out["status"] == "ok"
    assert out["code"] == "S02002727"
    assert out["name"] == "Old Town, Princes Street and Leith Street"
    assert out.get("note") in (None, "")
    assert "No data" not in (out.get("name") or "")


def test_intermediate_zone_name_not_loaded_yet_when_name_missing(monkeypatch):
    class _Cur:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *args, **kwargs):
            return None

        def fetchone(self):
            return {"iz_code": "S02999999"}

    import georgist.db as gdb

    monkeypatch.setattr(gdb, "cursor", lambda: _Cur())
    monkeypatch.setattr(platform_mod, "iz_name", lambda code, vintage: None)

    out = platform_mod._intermediate_zone_for(
        {"code": "S01014713", "vintage": 2022, "status": "ok"}
    )
    assert out["status"] == "ok"
    assert out["code"] == "S02999999"
    assert out["name"] is None
    assert out["note"] == "name not loaded yet"
    assert "No data" not in (out.get("note") or "")
