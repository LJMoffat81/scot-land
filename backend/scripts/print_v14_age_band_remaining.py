#!/usr/bin/env python3
"""Print v1.4 straight_line remaining_factor for fixed ages. Reads no prices.

Ages: 0, 10, 20, 30, 40, 50, 60, 68, 80, 100+.
Uses config keys only (surface.yaml v14.depreciation). No £ / no RoS.

Run: ``cd backend && PYTHONPATH=. python scripts/print_v14_age_band_remaining.py``
"""

from __future__ import annotations

from georgist import surface_rent as sr
from georgist import surface_v14 as v14

AGES = (0, 10, 20, 30, 40, 50, 60, 68, 80, 100)


def remaining_at_age(age: float, depreciation: dict) -> float:
    """Apply the executing v1.4 path at an explicit age (no price inputs)."""
    dep = sr.depreciation_at(depreciation, "central")
    r_b = sr.building_rate(dep)
    cap = float(dep.get("age_cap_years", 68))
    age_c = min(float(age), cap)
    max_dep = sr.max_depreciation_rate(dep)
    return max(1.0 - r_b * age_c, 1.0 - max_dep)


def main() -> int:
    cfg = sr.load_config()
    dep = v14.v14_depreciation(cfg)
    assert str(dep.get("method")) == "straight_line_v14"
    r_b = sr.building_rate(sr.depreciation_at(dep, "central"))
    cap = float(dep.get("age_cap_years", 68))
    max_dep = sr.max_depreciation_rate(sr.depreciation_at(dep, "central"))
    print("v14 remaining_factor age-band printout (no prices)")
    print(f"method={dep['method']}")
    print(f"rate_building.central={r_b}")
    print(f"age_cap_years={cap}")
    print(f"max_depreciation.central={max_dep}")
    print("formula=max(1 - rate_building*min(age,age_cap), 1 - max_depreciation)")
    print("---")
    for age in AGES:
        label = "100+" if age >= 100 else str(age)
        rem = remaining_at_age(age, dep)
        print(f"age={label}\tremaining_factor={rem:.6f}")
    # Also confirm EPC band path for 1950-1964 @ 2025 (= age_c 68)
    band_rem = sr.remaining_factor("1950-1964", 2025, dep)
    print("---")
    print(f"epc_band=1950-1964 valuation_year=2025 remaining_factor={band_rem:.6f}")
    print(f"expected=1-0.0035*68={(1 - 0.0035 * 68):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
