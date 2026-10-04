"""Council home-plot sensitivity ratios from the P0-2 combined-sensitivity table.

wide_range is true when the ratio is above 1.5. The ratios are the published
4 Oct 2026 table, not recomputed here.
"""

from __future__ import annotations

# council code -> mc_p90 / central home-plot ratio
WIDE_RANGE_RATIO: dict[str, float] = {
    "S12000034": 1.354,
    "S12000041": 1.525,
    "S12000035": 1.413,
    "S12000033": 2.13,
    "S12000042": 2.105,
    "S12000036": 1.299,
    "S12000049": 1.487,
    "S12000005": 1.521,
    "S12000006": 1.487,
    "S12000008": 2.09,
    "S12000045": 1.257,
    "S12000010": 1.246,
    "S12000011": 1.24,
    "S12000014": 1.486,
    "S12000047": 1.459,
    "S12000017": 1.259,
    "S12000018": 2.241,
    "S12000019": 1.253,
    "S12000020": 1.348,
    "S12000013": 2.232,
    "S12000021": 2.044,
    "S12000050": 1.602,
    "S12000023": 1.327,
    "S12000048": 1.317,
    "S12000038": 1.536,
    "S12000026": 1.407,
    "S12000027": 1.551,
    "S12000028": 1.496,
    "S12000029": 1.43,
    "S12000030": 1.298,
    "S12000039": 2.161,
    "S12000040": 1.307,
}


def wide_range_for(council_code: str) -> tuple[bool, float]:
    ratio = WIDE_RANGE_RATIO[council_code]
    return ratio > 1.5, ratio
