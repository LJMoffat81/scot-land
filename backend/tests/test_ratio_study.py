"""The ratio report covers every council and writes nothing back."""

import csv
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "scripts" / "ratio_study.py"
REPORT = ROOT / "reports" / "ratio_study.csv"
NOTE = "needs sale-level data"
FROZEN = (
    "data/config/agr.yaml",
    "data/processed/councils.json",
    "backend/agr/valuation.py",
)


def _digest(rel: str) -> str:
    data = (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def test_ratio_report_covers_32_councils_and_writes_nothing_back():
    before = {rel: _digest(rel) for rel in FROZEN}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    after = {rel: _digest(rel) for rel in FROZEN}
    assert after == before

    with REPORT.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 32
    assert rows[0].keys() >= {
        "council_code",
        "name",
        "ratio",
        "pass_0_90_1_10",
        "cod",
        "prd",
        "note",
    }
    assert {row["note"] for row in rows} == {NOTE}
    assert all(row["cod"] == "" and row["prd"] == "" for row in rows)
    blob = REPORT.read_text(encoding="utf-8").lower()
    assert "sale_price" not in blob
    assert "sold" not in blob
