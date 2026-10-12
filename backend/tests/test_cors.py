from api.cors import cors_settings


def test_cors_defaults_include_localhost(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    origins, regex = cors_settings()
    assert "http://localhost:3000" in origins
    assert regex is not None


def test_cors_custom_origins(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://agr.slrg.scot,https://preview.vercel.app")
    monkeypatch.setenv("ALLOW_VERCEL_PREVIEWS", "false")
    origins, regex = cors_settings()
    assert origins == ["https://agr.slrg.scot", "https://preview.vercel.app"]
    assert regex is None
