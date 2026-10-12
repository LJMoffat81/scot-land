"""RoS INSPIRE Index Polygons — registration-county catalogue.

RoS publishes **33 registration counties** (not the 32 modern local authorities).
Downloads use the MapCloud download API that replaced the interactive page at
https://ros.locationcentre.co.uk/inspire/ (same product, OGL-3.0).

Pilot aliases: Edinburgh → Midlothian (MID), Fife → FFE.
"""

from __future__ import annotations

from typing import TypedDict


class County(TypedDict):
    code: str
    title: str


# Order matches the RoS download dropdown (33 registration counties).
REGISTRATION_COUNTIES: tuple[County, ...] = (
    {"code": "ABN", "title": "Aberdeen"},
    {"code": "ANG", "title": "Angus"},
    {"code": "ARG", "title": "Argyll"},
    {"code": "AYR", "title": "Ayr"},
    {"code": "BNF", "title": "Banff"},
    {"code": "BER", "title": "Berwick"},
    {"code": "BUT", "title": "Bute"},
    {"code": "CTH", "title": "Caithness"},
    {"code": "CLK", "title": "Clackmannan"},
    {"code": "DMB", "title": "Dumbarton"},
    {"code": "DMF", "title": "Dumfries"},
    {"code": "ELN", "title": "East Lothian"},
    {"code": "FFE", "title": "Fife"},
    {"code": "GLA", "title": "Glasgow"},
    {"code": "INV", "title": "Inverness"},
    {"code": "KNC", "title": "Kincardine"},
    {"code": "KNR", "title": "Kinross"},
    {"code": "KRK", "title": "Kirkcudbright"},
    {"code": "LAN", "title": "Lanark"},
    {"code": "MID", "title": "Midlothian"},
    {"code": "MOR", "title": "Moray"},
    {"code": "NRN", "title": "Nairn"},
    {"code": "OAZ", "title": "Orkney and Zetland"},
    {"code": "PBL", "title": "Peebles"},
    {"code": "PTH", "title": "Perth"},
    {"code": "REN", "title": "Renfrew"},
    {"code": "ROS", "title": "Ross and Cromarty"},
    {"code": "ROX", "title": "Roxburgh"},
    {"code": "SEL", "title": "Selkirk"},
    {"code": "STG", "title": "Stirling"},
    {"code": "STH", "title": "Sutherland"},
    {"code": "WLN", "title": "West Lothian"},
    {"code": "WGN", "title": "Wigtown"},
)

BY_CODE: dict[str, County] = {c["code"]: c for c in REGISTRATION_COUNTIES}

# Human aliases for the pilot (City of Edinburgh titles sit in Midlothian / MID).
ALIASES: dict[str, str] = {
    "edinburgh": "MID",
    "midlothian": "MID",
    "fife": "FFE",
}

# Default pilot: Edinburgh (MID) + Fife (FFE).
PILOT_CODES: tuple[str, ...] = ("MID", "FFE")

DOWNLOAD_BASE = (
    "https://ros-inspire.themapcloud.com/maps/download/ros-cp.cadastralparcel"
)
CATALOGUE_URL = "https://ros.locationcentre.co.uk/inspire/"
SERVICE_HOME = "https://ros-inspire.themapcloud.com/"


def resolve_codes(names: list[str] | None = None) -> list[str]:
    """Resolve titles/aliases/codes to uppercase county codes."""
    if not names:
        return [c["code"] for c in REGISTRATION_COUNTIES]
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        key = raw.strip()
        upper = key.upper()
        if upper in BY_CODE:
            code = upper
        else:
            code = ALIASES.get(key.lower())
        if code is None:
            raise SystemExit(
                f"Unknown RoS registration county {raw!r}. "
                f"Use a code ({', '.join(BY_CODE)}) or alias "
                f"({', '.join(sorted(ALIASES))})."
            )
        if code not in seen:
            out.append(code)
            seen.add(code)
    return out


def download_url(code: str) -> str:
    code = code.upper()
    if code not in BY_CODE:
        raise ValueError(f"Unknown county code: {code}")
    return f"{DOWNLOAD_BASE}/{code}"
