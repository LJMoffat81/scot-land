"""Zone vintage and code rules shared by the surface modules (Data Zones convention, 2026-10-06).

`vintage` is stored as the integer 2011 or 2022, never 'DZ2011'. Codes must sit in
the official ranges: DZ2011 S01006506-S01013481 (6,976), DZ2022 S01013482-S01020873 (7,392).
"""

from __future__ import annotations

import re
from typing import Iterable

VINTAGES = (2011, 2022)
CODE_RANGES = {2011: (6506, 13481), 2022: (13482, 20873)}
_CODE_RE = re.compile(r"^S01(\d{6})$")


def vintage_int(v) -> int:
    """2011 | '2011' | 'DZ2011' -> 2011 (same for 2022). Anything else raises."""
    s = str(v).strip().upper()
    if s.startswith("DZ"):
        s = s[2:]
    try:
        n = int(float(s))
    except ValueError:
        raise ValueError(f"vintage {v!r} is not 2011 or 2022") from None
    if n not in VINTAGES:
        raise ValueError(f"vintage {v!r} is not 2011 or 2022")
    return n


def code_in_vintage(code: str, vintage) -> bool:
    m = _CODE_RE.match(str(code))
    if not m:
        return False
    lo, hi = CODE_RANGES[vintage_int(vintage)]
    return lo <= int(m.group(1)) <= hi


def validate_code(code: str, vintage) -> None:
    if not code_in_vintage(code, vintage):
        lo, hi = CODE_RANGES[vintage_int(vintage)]
        raise ValueError(f"code {code!r} is not a DZ{vintage_int(vintage)} code (S01{lo:06d}-S01{hi:06d})")


def validate_codes(codes: Iterable[str], vintage) -> None:
    bad = [c for c in codes if not code_in_vintage(c, vintage)]
    if bad:
        lo, hi = CODE_RANGES[vintage_int(vintage)]
        raise ValueError(f"{len(bad)} codes outside DZ{vintage_int(vintage)} range S01{lo:06d}-S01{hi:06d}, e.g. {bad[:3]}")


def manifest_vintage_label(vintages: Iterable) -> str:
    """Manifest `zone_vintage` text in the GIS / Data Zones manifest format, e.g. 'DZ2011;DZ2022'."""
    return ";".join(f"DZ{v}" for v in sorted({vintage_int(x) for x in vintages}))
