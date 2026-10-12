"""Town or countryside class of a 2011 data zone.

The table is the Scottish Government Urban Rural Classification 2020,
one class for the population-weighted centroid of each 2011 data zone.
Open Government Licence v3.0. Copyright Scottish Government, contains
Ordnance Survey data © Crown copyright and database right 2022.
https://www.gov.scot/publications/scottish-government-urban-rural-classification-2020/

Classes 1 to 4 take the town route. Classes 5 to 8 take the countryside
route, the same split as the 2022 point test. The class is an input beside
that point. It does not change the yearly charge.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import threading
from pathlib import Path

PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "processed"
    / "dz2011_urban_rural_2020.csv"
)
SHA256 = "0132f1137db0a8c0006afed348ba26e8f73e3b7583d20b089e80c626b4981a98"
YEAR = 2020

# Official eight-fold names, Scottish Government Urban Rural Classification 2020.
FOLD_NAMES = {
    1: "Large Urban Areas",
    2: "Other Urban Areas",
    3: "Accessible Small Towns",
    4: "Remote Small Towns",
    5: "Very Remote Small Towns",
    6: "Accessible Rural Areas",
    7: "Remote Rural Areas",
    8: "Very Remote Rural Areas",
}

_CODE = re.compile(r"^S\d{8}$")
_cache: dict[str, dict[str, int]] = {}
_lock = threading.Lock()


def route_for_fold(fold: int) -> str:
    """Town for classes 1-4. Countryside for classes 5-8."""
    if fold < 1 or fold > 8:
        raise ValueError(fold)
    return "town" if fold <= 4 else "countryside"


def _folds(path: Path | None) -> dict[str, int]:
    source = path or PATH
    key = str(source)
    with _lock:
        found = _cache.get(key)
        if found is not None:
            return found
        found = {}
        if source.is_file():
            raw = source.read_bytes()
            if path is None and hashlib.sha256(raw).hexdigest() != SHA256:
                raw = b""
            text = raw.decode("utf-8")
            for row in csv.DictReader(io.StringIO(text)):
                code = (row.get("dz2011") or "").strip()
                raw_fold = (row.get("ur8") or "").strip()
                if _CODE.match(code) is None or not raw_fold.isdigit():
                    continue
                fold = int(raw_fold)
                if fold in FOLD_NAMES:
                    found[code] = fold
        _cache[key] = found
        return found


def zone_class_for(code: str, path: Path | None = None) -> dict | None:
    """Official 2020 class for one 2011 data zone. None when the code is absent.

    The result names the route. It is not a rent.
    """
    if not isinstance(code, str) or _CODE.match(code) is None:
        return None
    fold = _folds(path).get(code)
    if fold is None:
        return None
    return {
        "fold": fold,
        "name": FOLD_NAMES[fold],
        "year": YEAR,
        "route": route_for_fold(fold),
    }
