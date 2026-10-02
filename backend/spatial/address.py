"""Find a door inside a postcode from OpenStreetMap.

The search returns a point. It does not price the land. The caller values
that point with the assessment already used for a click.
"""

from __future__ import annotations

import re
import time

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "scot-land/0.9 (https://scot-land.scot; door lookup)"
MISS = (
    "That door is not in the open address set. "
    "The map stays on the postcode centre."
)
_DOOR = re.compile(r"^[0-9]+[A-Z]?(?:[/\-][0-9]+[A-Z]?)*$")


def normalise_postcode(value: str) -> str:
    compact = "".join(value.split()).upper()
    if len(compact) < 5 or len(compact) > 7:
        raise ValueError("Invalid postcode format.")
    return compact


def display_postcode(compact: str) -> str:
    return f"{compact[:-3]} {compact[-3:]}"


def normalise_door(value: str) -> str:
    token = "".join(value.split()).upper()
    if not token or not _DOOR.fullmatch(token):
        raise ValueError("Enter a door number such as 12, 12A, or 2/1.")
    return token


def _building_number(door: str) -> str | None:
    if "/" not in door and "-" not in door:
        return None
    head = re.split(r"[/\-]", door, maxsplit=1)[0]
    return head or None


def _number_matches(door: str, found: str | None) -> bool:
    if not found:
        return False
    building = _building_number(door)
    for part in found.split(";"):
        token = "".join(part.split()).upper()
        if token == door or (building is not None and token == building):
            return True
    return False


def _street(address: dict) -> str:
    for key in ("road", "pedestrian", "footway", "residential", "path"):
        value = address.get(key)
        if value:
            return str(value)
    return ""


def select_matches(postcode: str, door: str, rows: list[dict]) -> dict:
    """Keep rows whose postcode and door agree. Do not invent a rent."""
    compact = normalise_postcode(postcode)
    door_token = normalise_door(door)
    seen: set[tuple] = set()
    matches: list[dict] = []
    for row in rows:
        address = row.get("address") or {}
        row_postcode = "".join(str(address.get("postcode") or "").split()).upper()
        if row_postcode != compact:
            continue
        housenumber = address.get("house_number") or row.get("name")
        if not _number_matches(door_token, None if housenumber is None else str(housenumber)):
            continue
        try:
            lat = round(float(row["lat"]), 6)
            lng = round(float(row["lon"]), 6)
        except (KeyError, TypeError, ValueError):
            continue
        street = _street(address)
        shown_number = str(housenumber).split(";")[0].strip()
        building = _building_number(door_token)
        number_label = (
            door_token
            if building and shown_number.upper().replace(" ", "") != door_token
            else shown_number
        )
        label = f"{number_label} {street}".strip()
        key = (round(lat, 4), round(lng, 4), street.upper(), shown_number.upper())
        if key in seen:
            continue
        seen.add(key)
        matches.append(
            {
                "lat": lat,
                "lng": lng,
                "street": street,
                "housenumber": shown_number,
                "label": label,
            }
        )
    matches.sort(key=lambda item: (item["street"], item["housenumber"]))
    status = "none" if not matches else "one" if len(matches) == 1 else "many"
    return {
        "postcode": display_postcode(compact),
        "door": door_token,
        "status": status,
        "matches": matches[:8],
        "note": MISS if status == "none" else "Door point from OpenStreetMap.",
    }


def lookup_params(postcode: str, door: str, road: str | None = None) -> dict:
    """One free-text search. A postcode parameter cannot be sent with it."""
    shown = display_postcode(normalise_postcode(postcode))
    door_token = normalise_door(door)
    text = f"{door_token} {road}, {shown}" if road else f"{door_token}, {shown}, Scotland"
    return {
        "format": "jsonv2",
        "addressdetails": 1,
        "countrycodes": "gb",
        "limit": 8,
        "q": text,
    }


def _road_at(client: httpx.Client, lat: float, lng: float) -> str | None:
    response = client.get(
        "https://nominatim.openstreetmap.org/reverse",
        params={
            "format": "jsonv2",
            "addressdetails": 1,
            "zoom": 18,
            "lat": lat,
            "lon": lng,
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return None
    address = payload.get("address") or {}
    road = address.get("road") or address.get("pedestrian") or address.get("footway")
    return str(road) if road else None


def nominatim_search(
    postcode: str,
    door: str,
    *,
    lat: float | None = None,
    lng: float | None = None,
) -> list[dict]:
    with httpx.Client(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
        road = None
        if lat is not None and lng is not None:
            road = _road_at(client, lat, lng)
            time.sleep(1.1)
        response = client.get(
            NOMINATIM_URL,
            params=lookup_params(postcode, door, road),
        )
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list):
        return []
    return payload


def search_door(
    postcode: str,
    door: str,
    *,
    rows: list[dict] | None = None,
    lat: float | None = None,
    lng: float | None = None,
) -> dict:
    found = rows if rows is not None else nominatim_search(postcode, door, lat=lat, lng=lng)
    return select_matches(postcode, door, found)
