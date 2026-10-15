"""Find a door inside a postcode from OpenStreetMap.

The search returns a point. It does not price the land. The caller values
that point with the assessment already used for a click.

Nominatim (public) is rate-limited: we cache results (~24h), serialise
outbound calls to at most one per second, retry on HTTP 429 (honouring
Retry-After), and surface exhaustion as NominatimUnavailable (→ HTTP 503).
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
# Nominatim usage policy requires an identifying User-Agent with contact.
USER_AGENT = (
    "scot-land/0.9 (https://scot-land.scot; place search; "
    "contact: hello@scot-land.scot)"
)
MISS = (
    "That door is not in the open address set. "
    "The map stays on the postcode centre."
)
_DOOR = re.compile(r"^[0-9]+[A-Z]?(?:[/\-][0-9]+[A-Z]?)*$")

logger = logging.getLogger(__name__)

# In-process result cache (search URL key → (expires_monotonic, payload)).
_CACHE_TTL_S = 24 * 60 * 60
_cache: dict[str, tuple[float, list[dict]]] = {}
_cache_lock = threading.Lock()

# One Nominatim HTTP call at a time, and at most one per second.
_rate_lock = threading.Lock()
_last_call_monotonic = 0.0
_MIN_INTERVAL_S = 1.0

_MAX_ATTEMPTS = 4

# Cheap seed for common Scottish place names (skip Nominatim on exact match).
# Centroids are approximate public city centres — display only, no rent.
_COMMON_SCOTTISH_PLACES: dict[str, dict[str, Any]] = {
    "edinburgh": {
        "lat": 55.9533,
        "lng": -3.1883,
        "label": "Edinburgh, Scotland",
    },
    "glasgow": {
        "lat": 55.8642,
        "lng": -4.2518,
        "label": "Glasgow, Scotland",
    },
    "aberdeen": {
        "lat": 57.1497,
        "lng": -2.0943,
        "label": "Aberdeen, Scotland",
    },
    "dundee": {
        "lat": 56.4620,
        "lng": -2.9707,
        "label": "Dundee, Scotland",
    },
    "inverness": {
        "lat": 57.4778,
        "lng": -4.2247,
        "label": "Inverness, Scotland",
    },
    "stirling": {
        "lat": 56.1165,
        "lng": -3.9369,
        "label": "Stirling, Scotland",
    },
    "perth": {
        "lat": 56.3950,
        "lng": -3.4308,
        "label": "Perth, Scotland",
    },
    "paisley": {
        "lat": 55.8456,
        "lng": -4.4235,
        "label": "Paisley, Scotland",
    },
    "falkirk": {
        "lat": 56.0019,
        "lng": -3.7839,
        "label": "Falkirk, Scotland",
    },
    "dumfries": {
        "lat": 55.0700,
        "lng": -3.6050,
        "label": "Dumfries, Scotland",
    },
}


class NominatimUnavailable(Exception):
    """Nominatim exhausted retries or stayed rate-limited — answer HTTP 503."""


def _cache_get(key: str) -> list[dict] | None:
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if not hit:
            return None
        expires, payload = hit
        if expires <= now:
            del _cache[key]
            return None
        return payload


def _cache_put(key: str, payload: list[dict]) -> None:
    with _cache_lock:
        _cache[key] = (time.monotonic() + _CACHE_TTL_S, payload)


def clear_nominatim_cache() -> None:
    """Test helper — drop the in-process Nominatim cache."""
    with _cache_lock:
        _cache.clear()


def _parse_retry_after(header: str | None) -> float | None:
    if not header:
        return None
    text = header.strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        return None


def _wait_for_rate_slot() -> None:
    """Hold the rate lock until a Nominatim slot is free (≥1s since last call)."""
    global _last_call_monotonic
    with _rate_lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL_S - (now - _last_call_monotonic)
        if wait > 0:
            time.sleep(wait)
        _last_call_monotonic = time.monotonic()


def _nominatim_get(
    client: httpx.Client,
    url: str,
    params: dict[str, Any],
) -> list[dict]:
    """GET Nominatim with throttle, cache, and 429 backoff. Raises NominatimUnavailable."""
    cache_key = f"{url}?{sorted(params.items())}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        _wait_for_rate_slot()
        try:
            response = client.get(url, params=params)
        except httpx.HTTPError as exc:
            last_exc = exc
            time.sleep(min(8.0, 2.0**attempt))
            continue

        if response.status_code == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            delay = retry_after if retry_after is not None else min(8.0, 2.0**attempt)
            logger.info(
                "Nominatim 429 (attempt %s/%s); sleeping %.1fs",
                attempt + 1,
                _MAX_ATTEMPTS,
                delay,
            )
            time.sleep(delay)
            last_exc = httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=response.request,
                response=response,
            )
            continue

        if response.status_code >= 500:
            last_exc = httpx.HTTPStatusError(
                f"Nominatim {response.status_code}",
                request=response.request,
                response=response,
            )
            time.sleep(min(8.0, 2.0**attempt))
            continue

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise NominatimUnavailable("Place search is busy. Try again in a moment.") from exc

        payload = response.json()
        if not isinstance(payload, list):
            # Reverse geocode returns a dict — callers that need it use a dedicated path.
            if isinstance(payload, dict):
                rows: list[dict] = [payload]
            else:
                rows = []
        else:
            rows = payload
        _cache_put(cache_key, rows)
        return rows

    raise NominatimUnavailable(
        "Place search is busy. Try again in a moment."
    ) from last_exc


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
    rows = _nominatim_get(
        client,
        NOMINATIM_REVERSE_URL,
        {
            "format": "jsonv2",
            "addressdetails": 1,
            "zoom": 18,
            "lat": lat,
            "lon": lng,
        },
    )
    if not rows:
        return None
    payload = rows[0]
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
        return _nominatim_get(
            client,
            NOMINATIM_URL,
            lookup_params(postcode, door, road),
        )


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


def _common_place_hit(text: str) -> dict | None:
    key = " ".join(text.split()).casefold()
    hit = _COMMON_SCOTTISH_PLACES.get(key)
    if not hit:
        return None
    return {
        "kind": "point",
        "lat": hit["lat"],
        "lng": hit["lng"],
        "label": hit["label"],
    }


def nominatim_places(text: str) -> list[dict]:
    with httpx.Client(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
        return _nominatim_get(client, NOMINATIM_URL, place_search_params(text))


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
    if rows is None:
        common = _common_place_hit(query)
        if common is not None:
            return common
        found_rows = nominatim_places(query)
    else:
        found_rows = rows
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
