"""Official Scottish local authority (council area) names.

Canonical list: National Records of Scotland / Scottish Government 32 council
areas (same strings as ``datazones.zone_spine.la_name``). Place-card and map
lookups must use these names — never UK HPI “City of Glasgow”-style aliases.
"""

from __future__ import annotations

# S12 code → official council area name (exactly 32).
OFFICIAL_COUNCIL_NAMES: dict[str, str] = {
    "S12000005": "Clackmannanshire",
    "S12000006": "Dumfries and Galloway",
    "S12000008": "East Ayrshire",
    "S12000010": "East Lothian",
    "S12000011": "East Renfrewshire",
    "S12000013": "Na h-Eileanan Siar",
    "S12000014": "Falkirk",
    "S12000017": "Highland",
    "S12000018": "Inverclyde",
    "S12000019": "Midlothian",
    "S12000020": "Moray",
    "S12000021": "North Ayrshire",
    "S12000023": "Orkney Islands",
    "S12000026": "Scottish Borders",
    "S12000027": "Shetland Islands",
    "S12000028": "South Ayrshire",
    "S12000029": "South Lanarkshire",
    "S12000030": "Stirling",
    "S12000033": "Aberdeen City",
    "S12000034": "Aberdeenshire",
    "S12000035": "Argyll and Bute",
    "S12000036": "City of Edinburgh",
    "S12000038": "Renfrewshire",
    "S12000039": "West Dunbartonshire",
    "S12000040": "West Lothian",
    "S12000041": "Angus",
    "S12000042": "Dundee City",
    "S12000045": "East Dunbartonshire",
    "S12000047": "Fife",
    "S12000048": "Perth and Kinross",
    "S12000049": "Glasgow City",
    "S12000050": "North Lanarkshire",
}

# Historic / HPI / typo aliases → official display name.
_COUNCIL_NAME_ALIASES: dict[str, str] = {
    "City of Aberdeen": "Aberdeen City",
    "City of Dundee": "Dundee City",
    "City of Glasgow": "Glasgow City",
    "City of Ediburgh": "City of Edinburgh",  # known misspelling
    "Edinburgh City": "City of Edinburgh",
    "Eilean Siar": "Na h-Eileanan Siar",
    "Western Isles": "Na h-Eileanan Siar",
}


def official_council_name(code: str | None, name: str | None = None) -> str | None:
    """Return the official council name for a code, or canonicalise a free-text name."""
    if code:
        keyed = OFFICIAL_COUNCIL_NAMES.get(code.strip())
        if keyed:
            return keyed
    if not name:
        return None
    text = name.strip()
    if text in OFFICIAL_COUNCIL_NAMES.values():
        return text
    return _COUNCIL_NAME_ALIASES.get(text, text)


def assert_official_council_set(names: set[str]) -> None:
    """Raise AssertionError unless ``names`` is exactly the official 32."""
    expected = set(OFFICIAL_COUNCIL_NAMES.values())
    if names != expected:
        missing = sorted(expected - names)
        extra = sorted(names - expected)
        raise AssertionError(
            f"Council names must match the official 32. "
            f"missing={missing!r} extra={extra!r}"
        )
