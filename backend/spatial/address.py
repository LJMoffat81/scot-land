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


_WORDS = re.compile(r"^[a-z]+\.[a-z]+\.[a-z]+$", re.IGNORECASE)
_POSTCODE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}$")
_TITLE = re.compile(r"^SCT0*(\d{1,10})$")
_SCOTLAND = (54.4, -8.2, 61.0, 0.2)  # south, west, north, east
TITLE_MISS = (
    "That title is not in the open cadastral set. "
    "Search its address or click the land. "
    "The official title sheet stays on ScotLIS."
)
PLACE_MISS = "No place matched in Scotland. Try a postcode, or click the map."


def normalise_title(value: str) -> str | None:
    """Land-register label SCT plus 10 digits. SCT7431917 and SCT0007431917 agree."""
    compact = "".join(value.split()).upper()
    match = _TITLE.fullmatch(compact)
    if not match:
        return None
    return "SCT" + match.group(1).zfill(10)


def looks_like_postcode(value: str) -> bool:
    compact = "".join(value.split()).upper()
    return _POSTCODE.fullmatch(compact) is not None


def _in_scotland(row: dict) -> bool:
    address = row.get("address") or {}
    state = str(address.get("state") or "").lower()
    # Nominatim names the country "Scotland" or "Alba / Scotland".
    code = str(address.get("ISO3166-2-lvl4") or "")
    if code and code != "GB-SCT":
        return False
    if state and "scotland" not in state and "alba" not in state:
        return False
    try:
        lat = float(row["lat"])
        lng = float(row["lon"])
    except (KeyError, TypeError, ValueError):
        return False
    south, west, north, east = _SCOTLAND
    return south <= lat <= north and west <= lng <= east


def _place_label(row: dict) -> str:
    name = str(row.get("display_name") or row.get("name") or "").strip()
    for suffix in (", United Kingdom", ", UK"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    return name


def select_places(rows: list[dict]) -> dict:
    """Address or place hits. No rent, and nothing outside Scotland."""
    seen: set[tuple] = set()
    matches: list[dict] = []
    for row in rows:
        if not _in_scotland(row):
            continue
        try:
            lat = round(float(row["lat"]), 6)
            lng = round(float(row["lon"]), 6)
        except (KeyError, TypeError, ValueError):
            continue
        label = _place_label(row)
        if not label:
            continue
        key = (round(lat, 4), round(lng, 4), label.upper())
        if key in seen:
            continue
        seen.add(key)
        matches.append({"lat": lat, "lng": lng, "label": label})
    matches = matches[:6]
    if not matches:
        return {"kind": "none", "matches": [], "note": PLACE_MISS}
    if len(matches) == 1:
        one = matches[0]
        return {"kind": "point", "lat": one["lat"], "lng": one["lng"], "label": one["label"]}
    return {
        "kind": "places",
        "matches": matches,
        "note": "Choose a place. The rent is the parcel at that point.",
    }


def place_search_params(text: str) -> dict:
    return {
        "format": "jsonv2",
        "addressdetails": 1,
        "countrycodes": "gb",
        "limit": 6,
        "bounded": 1,
        "viewbox": "-8.2,61.0,0.2,54.4",
        "q": text,
    }


def nominatim_places(text: str) -> list[dict]:
    with httpx.Client(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
        response = client.get(NOMINATIM_URL, params=place_search_params(text))
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list):
        return []
    return payload


def search_place(text: str, *, rows: list[dict] | None = None) -> dict:
    """One search: words, title number, postcode, or an address or place."""
    query = " ".join(text.split())
    if len(query) < 2:
        raise ValueError("Enter a postcode, an address, or a title number.")
    words = query[1:] if query.startswith("/") else query
    if _WORDS.fullmatch(words):
        return {"kind": "words", "words": words}
    title = normalise_title(query)
    if title:
        from spatial.parcels import lookup_parcel_by_title

        found = lookup_parcel_by_title(title)
        if not found:
            return {"kind": "title_miss", "label": title, "note": TITLE_MISS}
        return {
            "kind": "point",
            "lat": found["lat"],
            "lng": found["lng"],
            "label": found["label"],
        }
    if looks_like_postcode(query):
        compact = normalise_postcode(query)
        return {"kind": "postcode", "postcode": display_postcode(compact)}
    if len(query) < 3:
        raise ValueError("Enter a postcode, an address, or a title number.")
    found_rows = rows if rows is not None else nominatim_places(query)
    return select_places(found_rows)


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
