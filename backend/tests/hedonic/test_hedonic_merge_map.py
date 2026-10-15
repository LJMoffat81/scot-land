"""O-MM hedonic merge map: determinism + never load price columns."""

from __future__ import annotations

import csv
import io
import math
import zipfile
from pathlib import Path

import pytest

from georgist import hedonic_merge_map as hmm

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "hedonic"


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _make_spd_zip(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    fields = [
        "Postcode",
        "DataZone2011Code",
        "CouncilArea2019Code",
        "ITL2025Level3Code",
        "CensusHouseholdCount2022",
    ]
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SmallUser.csv", buf.getvalue())


def _synthetic_tree(root: Path) -> dict[str, Path]:
    """Build a tiny geography where one CA cell fails and merges to ITL3/national."""
    root.mkdir(parents=True, exist_ok=True)

    # 45 urban zones in CA-A (estimable), 10 urban in CA-B (thin → merge).
    # Shared ITL3 for both; thin CA-B merges into ITL3 pool with nothing else
    # of substance → may go national depending on IQR.
    zones = []
    for i in range(45):
        zones.append(
            {
                "dz": f"S010100{i:02d}",
                "ca": "S12000001",
                "itl": "TLM71",
                "ur6": 1,
                # Spread ln A for IQR ≥ 0.30
                "a": math.exp(4.0 + (i / 44.0) * 0.80),
                "n21": 10,
                "n22": 10,
            }
        )
    for i in range(10):
        zones.append(
            {
                "dz": f"S010200{i:02d}",
                "ca": "S12000002",
                "itl": "TLM71",
                "ur6": 1,
                "a": math.exp(4.2 + (i / 9.0) * 0.10),  # tiny IQR
                "n21": 8,
                "n22": 8,
            }
        )
    # Rural national-merge case: 5 zones only
    for i in range(5):
        zones.append(
            {
                "dz": f"S010300{i:02d}",
                "ca": "S12000003",
                "itl": "TLM72",
                "ur6": 6,
                "a": 200.0 + i,
                "n21": 12,
                "n22": 12,
            }
        )

    counts_rows = []
    for z in zones:
        counts_rows.append(
            {"code": z["dz"], "year": 2021, "sales_n": z["n21"], "suppressed": "false"}
        )
        counts_rows.append(
            {"code": z["dz"], "year": 2022, "sales_n": z["n22"], "suppressed": "false"}
        )
        # Extra year must be ignored
        counts_rows.append(
            {"code": z["dz"], "year": 2023, "sales_n": 99, "suppressed": "false"}
        )
    counts = root / "counts.csv"
    _write_csv(counts, counts_rows, ["code", "year", "sales_n", "suppressed"])

    # One DZ2022 per DZ2011 (1:1), house_plot_ha so A_z_m2 = a
    plot_rows = []
    weight_rows = []
    for z in zones:
        j = z["dz"].replace("S010", "S0109")  # fake DZ2022
        # A_z = ha * 10000 / homes  → homes=100, ha = a/100
        homes = 100.0
        ha = z["a"] * homes / 10_000.0
        plot_rows.append(
            {
                "code": j,
                "homes": f"{homes:.1f}",
                "house_plot_ha": f"{ha:.8f}",
                "flags": "",
            }
        )
        weight_rows.append(
            {
                "dz2011": z["dz"],
                "dz2022": j,
                "uprn_count": 100,
            }
        )
    plot = root / "plot_split.csv"
    _write_csv(plot, plot_rows, ["code", "homes", "house_plot_ha", "flags"])
    weights = root / "uprn_weights.csv"
    _write_csv(weights, weight_rows, ["dz2011", "dz2022", "uprn_count"])

    ur_rows = [{"dz2011": z["dz"], "ur6": z["ur6"]} for z in zones]
    ur = root / "ur6.csv"
    _write_csv(ur, ur_rows, ["dz2011", "ur6"])

    spd_rows = []
    for z in zones:
        spd_rows.append(
            {
                "Postcode": f"AB1 {z['dz'][-3:]}",
                "DataZone2011Code": z["dz"],
                "CouncilArea2019Code": z["ca"],
                "ITL2025Level3Code": z["itl"],
                "CensusHouseholdCount2022": 50,
            }
        )
    # Tie-break fixture: equal household weights for two CAs on one extra zone
    # (not in fit window — only exercises modal helper via SPD load).
    spd = root / "spd.zip"
    _make_spd_zip(spd, spd_rows)

    return {
        "counts": counts,
        "plot_split": plot,
        "uprn_weights": weights,
        "ur": ur,
        "spd": spd,
    }


@pytest.fixture()
def synth(tmp_path: Path) -> dict[str, Path]:
    return _synthetic_tree(tmp_path / "omm")


def test_two_runs_identical_bytes_and_sha(synth: dict[str, Path], tmp_path: Path) -> None:
    rows1 = hmm.build_merge_map_from_paths(
        counts_path=synth["counts"],
        plot_split_path=synth["plot_split"],
        uprn_weights_path=synth["uprn_weights"],
        ur_path=synth["ur"],
        spd_zip=synth["spd"],
        seed=hmm.SEED,
    )
    rows2 = hmm.build_merge_map_from_paths(
        counts_path=synth["counts"],
        plot_split_path=synth["plot_split"],
        uprn_weights_path=synth["uprn_weights"],
        ur_path=synth["ur"],
        spd_zip=synth["spd"],
        seed=hmm.SEED,
    )
    b1 = hmm.serialize_merge_map(rows1)
    b2 = hmm.serialize_merge_map(rows2)
    assert b1 == b2
    assert hmm.sha256_bytes(b1) == hmm.sha256_bytes(b2)

    out1 = tmp_path / "m1.csv"
    out2 = tmp_path / "m2.csv"
    d1 = hmm.write_merge_map(out1, rows1)
    d2 = hmm.write_merge_map(out2, rows2)
    assert d1 == d2
    assert out1.read_bytes() == out2.read_bytes()
    assert d1 == hmm.sha256_bytes(out1.read_bytes())


def test_seed_constant() -> None:
    assert hmm.SEED == 20261015


def test_no_price_columns_loaded(tmp_path: Path) -> None:
    bad = tmp_path / "prices.csv"
    _write_csv(
        bad,
        [
            {
                "code": "S01006506",
                "year": 2021,
                "sales_n": 10,
                "Price - Mean": 150000,
            }
        ],
        ["code", "year", "sales_n", "Price - Mean"],
    )
    with pytest.raises(ValueError, match="price/value/rent"):
        hmm.load_fit_window_counts(bad)

    # Columns-read vs denylist unit check
    with pytest.raises(ValueError, match="price/value/rent"):
        hmm.assert_no_price_columns(
            ["code", "dz_med2021", "sales_n", "Median", "value", "rent"]
        )

    ok = hmm.assert_no_price_columns(
        ["code", "year", "sales_n", "CensusHouseholdCount2022", "uprn_count"]
    )
    assert "sales_n" in ok


def test_merge_ladder_assigns_levels(synth: dict[str, Path]) -> None:
    rows = hmm.build_merge_map_from_paths(
        counts_path=synth["counts"],
        plot_split_path=synth["plot_split"],
        uprn_weights_path=synth["uprn_weights"],
        ur_path=synth["ur"],
        spd_zip=synth["spd"],
        seed=hmm.SEED,
    )
    by_dz = {r["dz2011"]: r for r in rows}
    # Large urban CA should stay at ca level
    assert by_dz["S01010000"]["merge_level"] == "ca"
    assert by_dz["S01010000"]["cell_final"].startswith("S12000001|")
    # Thin urban CA should not stay at its own CA cell
    assert by_dz["S01020000"]["merge_level"] in {"itl3", "national"}
    assert by_dz["S01020000"]["cell_final"] != by_dz["S01020000"]["cell_ca"]
    # Tiny rural set → national
    assert by_dz["S01030000"]["merge_level"] == "national"
    assert by_dz["S01030000"]["cell_final"] == "NATIONAL|rural"
    # Stable sort
    assert [r["dz2011"] for r in rows] == sorted(r["dz2011"] for r in rows)


def test_modal_tie_break_uses_seed() -> None:
    a = hmm._pick_modal({"S12000001": 10.0, "S12000002": 10.0}, dz="S01009999", seed=hmm.SEED)
    b = hmm._pick_modal({"S12000001": 10.0, "S12000002": 10.0}, dz="S01009999", seed=hmm.SEED)
    assert a == b
    # Different seed can differ (not required, but same seed must match)
    c = hmm._pick_modal({"S12000001": 10.0, "S12000002": 10.0}, dz="S01009999", seed=1)
    d = hmm._pick_modal({"S12000001": 10.0, "S12000002": 10.0}, dz="S01009999", seed=1)
    assert c == d


def test_iqr_threshold() -> None:
    xs = [math.exp(4.0 + i * 0.01) for i in range(40)]
    assert hmm.iqr([math.log(x) for x in xs]) < 0.30
    ys = [math.exp(4.0 + i * 0.02) for i in range(40)]
    assert hmm.iqr([math.log(y) for y in ys]) >= 0.30
