#!/usr/bin/env python3
"""Monthly fetch of the Registers of Scotland all-statistics workbook.

The workbook name changes every month. This module reads the house price
statistics page and follows the .xlsx link marked as the latest figures.
It does not store that filename.

The fetch is off unless ``--approve-download`` is passed. Nothing is
downloaded on the project owner's PC until that approval step. Downloads
go under ``data/external/ros/`` (gitignored). A 403 or a bot-check page
stops the run. Request headers are left at the library default: no
user-agent override and no retry.

Run from ``backend/``::

    python -m etl.fetch_ros_statistics --approve-download
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

STATISTICS_PAGE = (
    "https://www.ros.gov.uk/data-and-statistics/property-market-statistics/"
    "house-price-statistics"
)
LICENCE = "OGL v3"
# RoS states that these statistics are provided under the Open Government
# Licence and does not publish a different credit. This is the attribution
# the licence itself requires in that case.
ROS_ATTRIBUTION = (
    "Contains public sector information licensed under the Open Government Licence v3.0."
)
OFF_MESSAGE = (
    "RoS all-statistics fetch is off. "
    "It does not download until the project owner passes --approve-download."
)
MANIFEST_NAME = "ros_all_stats_manifest.json"

_HREF = re.compile(r"""href\s*=\s*(['"])(.*?)\1""", re.IGNORECASE)
_BOT_MARKERS = (
    "cf-browser-verification",
    "cf-challenge",
    "challenge-platform",
    "cdn-cgi/challenge",
    "just a moment",
    "attention required",
    "verify you are human",
    "enable javascript and cookies",
)


class RosFetchError(Exception):
    """A fetch that must stop with a non-zero exit and no saved data."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_out_dir() -> Path:
    return _repo_root() / "data" / "external" / "ros"


def _blocked(status: int | None, url: str, bot: bool) -> RosFetchError:
    if status == 403:
        detail = f"HTTP 403 from {url}. This is an access denial or a bot check."
    elif bot:
        detail = f"the response from {url} looks like a bot check."
    else:
        detail = f"the response from {url} was blocked."
    return RosFetchError(
        "RoS statistics fetch stopped: "
        f"{detail} No retry and no user-agent change. Nothing was saved."
    )


def _looks_like_bot(body: bytes) -> bool:
    sample = body[:8000].decode("utf-8", errors="replace").lower()
    return any(marker in sample for marker in _BOT_MARKERS)


def _get(url: str) -> tuple[str, bytes]:
    """One GET. Library default headers only. No retry."""
    try:
        resp = urllib.request.urlopen(url, timeout=60)
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp is not None else b""
        if exc.code == 403 or _looks_like_bot(body):
            raise _blocked(exc.code, url, _looks_like_bot(body)) from exc
        raise RosFetchError(
            f"RoS statistics fetch failed: HTTP {exc.code} for {url}. Nothing was saved."
        ) from exc
    except urllib.error.URLError as exc:
        raise RosFetchError(
            f"RoS statistics fetch failed: {exc.reason}. Nothing was saved."
        ) from exc
    with resp:
        body = resp.read()
        content_type = resp.headers.get("Content-Type", "")
        status = getattr(resp, "status", 200)
    if status == 403 or _looks_like_bot(body):
        raise _blocked(status, url, True)
    return content_type, body


def workbook_url(html: str, page_url: str = STATISTICS_PAGE) -> str:
    """Return the latest-figures .xlsx URL. The filename is read from the page."""
    found: list[tuple[str, int]] = []
    for match in _HREF.finditer(html):
        href = unescape(match.group(2)).strip()
        path = urlparse(href).path
        if not path.lower().split("?", 1)[0].endswith(".xlsx"):
            continue
        absolute = urljoin(page_url, href)
        prefix = html[max(0, match.start() - 180) : match.start()].lower()
        anchor_end = html.find("</a>", match.end())
        anchor = html[match.end() : anchor_end if anchor_end != -1 else match.end()]
        anchor_text = re.sub(r"<[^>]+>", " ", unescape(anchor)).lower()
        score = 0
        if "latest figures" in prefix or "latest figures" in anchor_text:
            score += 5
        if "house price statistics" in anchor_text:
            score += 1
        found.append((absolute, score))
    if not found:
        raise RosFetchError(
            "RoS statistics page has no .xlsx download link. Nothing was saved."
        )
    best = max(score for _, score in found)
    chosen = [url for url, score in found if score == best]
    if len(found) > 1 and best == 0:
        raise RosFetchError(
            "RoS statistics page has more than one .xlsx and none is marked "
            "as the latest figures. Nothing was saved."
        )
    if len(chosen) != 1:
        raise RosFetchError(
            "RoS statistics page has more than one latest .xlsx link. Nothing was saved."
        )
    return chosen[0]


def _workbook_name(source_url: str) -> str:
    name = Path(urlparse(source_url).path).name
    if not name.lower().endswith(".xlsx") or name != Path(name).name or ".." in name:
        raise RosFetchError(
            f"RoS statistics link is not a workbook filename: {source_url}. Nothing was saved."
        )
    return name


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(
    out_dir: Path,
    *,
    page_url: str = STATISTICS_PAGE,
    fetch_date: date | None = None,
) -> Path:
    """Download the workbook and write a manifest next to it. Caller must have approved."""
    _content_type, page = _get(page_url)
    if not page.strip():
        raise RosFetchError("RoS statistics page was empty. Nothing was saved.")
    html = page.decode("utf-8", errors="replace")
    source_url = workbook_url(html, page_url)
    file_type, payload = _get(source_url)
    if "html" in file_type.lower() or payload.lstrip().startswith(b"<"):
        raise _blocked(None, source_url, True)
    name = _workbook_name(source_url)
    when = fetch_date or datetime.now(timezone.utc).date()
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / name
    partial = dest.with_name(dest.name + ".part")
    partial.write_bytes(payload)
    digest = _sha256(payload)
    partial.replace(dest)
    manifest = {
        "source_url": source_url,
        "fetch_date": when.isoformat(),
        "licence": LICENCE,
        "attribution": ROS_ATTRIBUTION,
        "sha256": digest,
    }
    manifest_path = out_dir / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {dest.name} and {manifest_path.name} sha256={digest}", file=sys.stderr)
    return manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--approve-download",
        action="store_true",
        help="Project-owner approval. Without this flag nothing is downloaded.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for the workbook and manifest (default: data/external/ros).",
    )
    args = parser.parse_args(argv)
    if not args.approve_download:
        print(OFF_MESSAGE, file=sys.stderr)
        return 0
    out_dir = args.out_dir if args.out_dir is not None else default_out_dir()
    try:
        fetch(out_dir)
    except RosFetchError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
