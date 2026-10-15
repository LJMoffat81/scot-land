"""Invariants for data/reference/council_neighbours_2022.csv (NEIGHBOURS-2022).

Pairs are stored one-way only (council_a < council_b). See
data/reference/README_council_neighbours_2022.md.
"""

from __future__ import annotations

import csv
from pathlib import Path

from spatial.council_names import OFFICIAL_COUNCIL_NAMES

REPO_ROOT = Path(__file__).resolve().parents[2]
NEIGHBOURS_CSV = REPO_ROOT / "data" / "reference" / "council_neighbours_2022.csv"
ISLAND_COUNCILS = frozenset({"S12000013", "S12000023", "S12000027"})
EXPECTED_METHOD = "dz2022_dissolve_touch_1m"
EXPECTED_REASON = (
    "shared land boundary (2022 data zones dissolved to councils, touch within 1 m)"
)
EXPECTED_FIELDNAMES = ("council_a", "council_b", "method", "reason")


def _load_rows() -> list[dict[str, str]]:
    with NEIGHBOURS_CSV.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == list(EXPECTED_FIELDNAMES), reader.fieldnames
        return list(reader)


def test_council_neighbours_2022_invariants():
    """Valid S12 codes; no self-pairs/duplicates; a < b; islands absent; row count from file."""
    rows = _load_rows()
    # Row count comes from the file itself — do not hard-code an expected length.
    assert rows, f"expected data rows in {NEIGHBOURS_CSV}"
    row_count = len(rows)

    valid_codes = frozenset(OFFICIAL_COUNCIL_NAMES)
    seen_pairs: set[tuple[str, str]] = set()
    codes_in_file: set[str] = set()

    for i, row in enumerate(rows):
        a = row["council_a"].strip()
        b = row["council_b"].strip()
        method = row["method"].strip()
        reason = row["reason"].strip()

        assert a in valid_codes, f"row {i}: council_a {a!r} is not a 2022 S12 council"
        assert b in valid_codes, f"row {i}: council_b {b!r} is not a 2022 S12 council"
        assert a != b, f"row {i}: self-pair {a}"
        # Documented one-way storage: lexicographic council_a < council_b.
        assert a < b, f"row {i}: expected council_a < council_b, got {a},{b}"
        assert method == EXPECTED_METHOD, f"row {i}: method {method!r}"
        assert reason == EXPECTED_REASON, f"row {i}: reason {reason!r}"

        pair = (a, b)
        assert pair not in seen_pairs, f"row {i}: duplicate pair {pair}"
        seen_pairs.add(pair)
        codes_in_file.update((a, b))

    assert len(seen_pairs) == row_count
    assert ISLAND_COUNCILS.isdisjoint(codes_in_file), (
        f"island councils must be absent; found {sorted(ISLAND_COUNCILS & codes_in_file)}"
    )
    # File ends with a trailing newline (text CSV convention).
    text = NEIGHBOURS_CSV.read_text(encoding="utf-8")
    assert text.endswith("\n"), "council_neighbours_2022.csv must end with a newline"
