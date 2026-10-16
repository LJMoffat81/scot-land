"""Monthly RoS all-statistics fetch: mocked page and response, including a 403."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import urllib.error
from datetime import date, datetime, timezone
from email.message import Message
from pathlib import Path

import pytest

from etl import fetch_ros_statistics as ros

REPO = Path(__file__).resolve().parents[3]
PAGE = ros.STATISTICS_PAGE
WORKBOOK_HREF = "/media/stats/ros_all_stats_March_2031.xlsx"
WORKBOOK_URL = "https://www.ros.gov.uk" + WORKBOOK_HREF
PAYLOAD = b"PK\x03\x04ros-statistics-fixture-not-a-price-cell"


def _page(*anchors: str) -> str:
    body = "\n".join(anchors)
    return (
        "<html><body><h1>House price statistics</h1>"
        "<h2>Download our statistics</h2>"
        f"{body}</body></html>"
    )


LATEST = (
    '<p>Latest figures: <a href="{href}">House price statistics: March 2031 (XLSX)</a></p>'
).format(href=WORKBOOK_HREF)
OLDER = (
    "<p>Previous release: "
    '<a href="/media/stats/ros_all_stats_January_2030.xlsx">January 2030</a></p>'
    + ("\n" * 30)
)


class _Response:
    def __init__(self, body: bytes, content_type: str = "application/octet-stream", status: int = 200):
        self._body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _route(pages: dict[str, object]):
    calls: list[str] = []

    def urlopen(url, timeout=60):
        assert isinstance(url, str)
        calls.append(url)
        item = pages[url]
        if isinstance(item, Exception):
            raise item
        return item

    return calls, urlopen


def _http_error(url: str, code: int, body: bytes = b"") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "error", Message(), io.BytesIO(body))


def test_source_does_not_bake_in_the_current_workbook_name():
    text = Path(ros.__file__).read_text(encoding="utf-8")
    assert "ros_all_stats_August_2026.xlsx" not in text
    assert "August_2026" not in text
    assert "User-Agent" not in text
    assert "add_header" not in text
    assert "headers=" not in text


def test_off_by_default_does_not_download(monkeypatch, tmp_path, capsys):
    def urlopen(*args, **kwargs):
        raise AssertionError("fetch must stay off without approval")

    monkeypatch.setattr(ros.urllib.request, "urlopen", urlopen)
    assert ros.main(["--out-dir", str(tmp_path)]) == 0
    assert "off" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_mocked_page_writes_manifest(monkeypatch, tmp_path, capsys):
    html = _page(OLDER, LATEST).encode()
    calls, urlopen = _route(
        {
            PAGE: _Response(html, "text/html; charset=utf-8"),
            WORKBOOK_URL: _Response(PAYLOAD),
        }
    )
    monkeypatch.setattr(ros.urllib.request, "urlopen", urlopen)
    assert ros.main(["--approve-download", "--out-dir", str(tmp_path)]) == 0
    assert calls == [PAGE, WORKBOOK_URL]
    saved = tmp_path / "ros_all_stats_March_2031.xlsx"
    assert saved.read_bytes() == PAYLOAD
    manifest = json.loads((tmp_path / ros.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest == {
        "source_url": WORKBOOK_URL,
        "fetch_date": datetime.now(timezone.utc).date().isoformat(),
        "licence": "OGL v3",
        "attribution": ros.ROS_ATTRIBUTION,
        "sha256": hashlib.sha256(PAYLOAD).hexdigest(),
    }
    assert ros.ROS_ATTRIBUTION == (
        "Contains public sector information licensed under the Open Government Licence v3.0."
    )
    assert "sha256=" in capsys.readouterr().err
    assert not list(tmp_path.glob("*.part"))


def test_fetch_date_is_the_supplied_day(monkeypatch, tmp_path):
    calls, urlopen = _route(
        {
            PAGE: _Response(_page(LATEST).encode(), "text/html"),
            WORKBOOK_URL: _Response(PAYLOAD),
        }
    )
    monkeypatch.setattr(ros.urllib.request, "urlopen", urlopen)
    ros.fetch(tmp_path, fetch_date=date(2026, 10, 16))
    manifest = json.loads((tmp_path / ros.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["fetch_date"] == "2026-10-16"
    assert manifest["licence"] == "OGL v3"


def test_relative_latest_link_beats_an_older_workbook():
    html = _page(OLDER, LATEST)
    assert ros.workbook_url(html, PAGE) == WORKBOOK_URL


def test_page_without_a_workbook_link_fails():
    with pytest.raises(ros.RosFetchError, match="no .xlsx"):
        ros.workbook_url("<html><body>Download our statistics</body></html>", PAGE)


def test_403_on_the_statistics_page_fails_once(monkeypatch, tmp_path, capsys):
    calls, urlopen = _route({PAGE: _http_error(PAGE, 403, b"Forbidden")})
    monkeypatch.setattr(ros.urllib.request, "urlopen", urlopen)
    assert ros.main(["--approve-download", "--out-dir", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "HTTP 403" in err
    assert "Nothing was saved" in err
    assert calls == [PAGE]
    assert list(tmp_path.iterdir()) == []


def test_403_on_the_workbook_fails_without_a_retry(monkeypatch, tmp_path, capsys):
    calls, urlopen = _route(
        {
            PAGE: _Response(_page(LATEST).encode(), "text/html"),
            WORKBOOK_URL: _http_error(WORKBOOK_URL, 403, b"Forbidden"),
        }
    )
    monkeypatch.setattr(ros.urllib.request, "urlopen", urlopen)
    assert ros.main(["--approve-download", "--out-dir", str(tmp_path)]) == 1
    assert calls == [PAGE, WORKBOOK_URL]
    assert "HTTP 403" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_bot_check_page_fails(monkeypatch, tmp_path, capsys):
    challenge = b"<html><title>Just a moment...</title><p>cf-browser-verification</p></html>"
    calls, urlopen = _route({PAGE: _Response(challenge, "text/html", status=200)})
    monkeypatch.setattr(ros.urllib.request, "urlopen", urlopen)
    assert ros.main(["--approve-download", "--out-dir", str(tmp_path)]) == 1
    assert "bot check" in capsys.readouterr().err
    assert calls == [PAGE]
    assert list(tmp_path.iterdir()) == []


def test_workbook_and_manifest_stay_out_of_git():
    sample = "data/external/ros/ros_all_stats_March_2031.xlsx"
    manifest = "data/external/ros/ros_all_stats_manifest.json"
    for path in (sample, manifest):
        result = subprocess.run(
            ["git", "check-ignore", path],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, path
