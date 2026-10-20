"""D7 sold-TFA provenance chain.

The source file, both filter scripts, and both filter outputs are pinned by
the full sha256. S-x2 and the B2 loader accept the filter2 output only after
every earlier pin has matched. An eight-character prefix match is a mismatch.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence

D7_SOURCE_SHA256 = "d99b8daa6e03843923799d249714fa850bd360c6e9cd01a922d43b6000ba2d6e"
D7_FILTER1_SCRIPT_SHA256 = "849081cdad05aad0a8ed4f84eacdf2bc155af5082d03a0fad459b9777097a564"
D7_FILTER1_OUTPUT_SHA256 = "8d605492cfbc02c345490e4ba48341d3f57553b471ac015948a48a0c0dd65443"
D7_FILTER2_SCRIPT_SHA256 = "e4b3561b38ad982a6ffa8124156bfdc2ce3fa84ff93fb60c3e82543839dc2f8d"
D7_FILTER2_OUTPUT_SHA256 = "c0afda350fd500ecd53bbcd22ad309ac3f4cc159cfa48f135918c2376f969046"
D7_ROW_COUNT = 34659
D7_YEAR_MIN = 2019
D7_YEAR_MAX = 2023

# Production pins. Tests may replace entries; the driver does that for synthetic
# files only. Comparing a sha uses the full 64-character string.
PIN_TABLE: dict[str, object] = {
    "source": D7_SOURCE_SHA256,
    "filter1_script": D7_FILTER1_SCRIPT_SHA256,
    "filter1_output": D7_FILTER1_OUTPUT_SHA256,
    "filter2_script": D7_FILTER2_SCRIPT_SHA256,
    "filter2_output": D7_FILTER2_OUTPUT_SHA256,
    "row_count": D7_ROW_COUNT,
    "year_min": D7_YEAR_MIN,
    "year_max": D7_YEAR_MAX,
}

PriceReader = Callable[[str], str]


def read_price_cell(value: str) -> str:
    """Price-cell hook. Callers must not invoke it before the year check passes."""
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _full_match(actual: str, expected: str) -> bool:
    """True only when both strings are the same 64-character sha256."""
    if len(actual) != 64 or len(expected) != 64:
        return False
    return actual == expected


def provenance_accepts(sha: str | None) -> bool:
    """The filter2 output pin, and only that pin, may reach S-x2.

    The source sha, a prefix, or any other digest is refused. The B2 loader
    supplies this digest only after ``run_d7_chain`` has matched every step.
    """
    if not isinstance(sha, str) or len(sha) != 64:
        return False
    source = str(PIN_TABLE["source"])
    scripts = (
        str(PIN_TABLE["filter1_script"]),
        str(PIN_TABLE["filter1_output"]),
        str(PIN_TABLE["filter2_script"]),
    )
    if sha != str(PIN_TABLE["filter2_output"]) or sha == source:
        return False
    if any(len(item) != 64 for item in (source, *scripts)):
        return False
    return True


def d7_provenance_manifest() -> dict[str, object]:
    """Pins recorded for the manifest. Script shas are the pinned script bytes."""
    return {
        "source_sha256": str(PIN_TABLE["source"]),
        "filter1_script_sha256": str(PIN_TABLE["filter1_script"]),
        "filter1_output_sha256": str(PIN_TABLE["filter1_output"]),
        "filter2_script_sha256": str(PIN_TABLE["filter2_script"]),
        "filter2_output_sha256": str(PIN_TABLE["filter2_output"]),
        "row_count": int(PIN_TABLE["row_count"]),
        "year_range": f"{int(PIN_TABLE['year_min'])}-{int(PIN_TABLE['year_max'])}",
    }


def _not_run(step: str, check: str, expected: object, actual: object) -> str:
    return f"{step}: NOT_RUN: {check}: expected {expected}, got {actual}"


@dataclass
class D7ChainResult:
    status: str
    message: str = ""
    manifest: dict[str, object] = field(default_factory=dict)
    d7_sha256: str | None = None
    s_x2: str = "NOT_RUN"
    fitted: dict | None = None

    @property
    def passed(self) -> bool:
        return self.status == "passed"


def _result(message: str, manifest: dict[str, object]) -> D7ChainResult:
    return D7ChainResult(status="NOT_RUN", message=message, manifest=manifest, s_x2="NOT_RUN")


def execute_filter1(script: Path, source: Path, dest: Path) -> None:
    """Run the pinned filter1 script. Tests spy on this function."""
    _execute(script, source, dest)


def execute_filter2(script: Path, source: Path, dest: Path) -> None:
    """Run the pinned filter2 script. Tests spy on this function."""
    _execute(script, source, dest)


def _execute(script: Path, source: Path, dest: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(script), str(source), str(dest)],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip() or "filter failed"
        raise RuntimeError(detail)


def fit_headline(rows: Sequence[Mapping], d7_sha256: str | None = None):
    """Registered onto the hedonic fit. The chain calls this only after every pin matches."""
    if _FIT is None:
        raise RuntimeError("fit_headline is not registered")
    return _FIT(rows, d7_sha256=d7_sha256)


_FIT: Callable | None = None


def register_fit_headline(func: Callable) -> None:
    global _FIT
    _FIT = func


def _year_field(line: str, index: int) -> str:
    """Return one CSV field and stop at the end of that field."""
    field_index = 0
    buf: list[str] = []
    for char in line:
        if char == ",":
            if field_index == index:
                return "".join(buf)
            field_index += 1
            buf = []
            continue
        if field_index == index:
            buf.append(char)
        elif field_index > index:
            return "".join(buf)
    return "".join(buf) if field_index == index else ""


def _header_and_rows(path: Path) -> tuple[list[str], list[str]]:
    raw = path.read_bytes().splitlines()
    if not raw:
        return [], []
    header = raw[0].decode("utf-8").split(",")
    rows = [line.decode("utf-8") for line in raw[1:] if line.strip()]
    return header, rows


def inspect_filter2_output(path: Path) -> str | None:
    """Row count and year range. The year field is read before any price cell."""
    header, rows = _header_and_rows(path)
    if "year" not in header:
        return _not_run("D7_FILTER2_OUT", "year_range", _year_span(), "absent")
    year_index = header.index("year")
    expected_count = int(PIN_TABLE["row_count"])
    if len(rows) != expected_count:
        return _not_run("D7_FILTER2_OUT", "row_count", expected_count, len(rows))
    years: list[int] = []
    for line in rows:
        text = _year_field(line, year_index).strip()
        if not text.isdigit():
            return _not_run("D7_FILTER2_OUT", "year_range", _year_span(), text or "blank")
        years.append(int(text))
    if not years:
        return _not_run("D7_FILTER2_OUT", "year_range", _year_span(), "absent")
    span = f"{min(years)}-{max(years)}"
    allowed = set(range(int(PIN_TABLE["year_min"]), int(PIN_TABLE["year_max"]) + 1))
    if set(years) != allowed or span != _year_span():
        return _not_run("D7_FILTER2_OUT", "year_range", _year_span(), span)
    price_indexes = [index for index, name in enumerate(header) if name in {"price", "value", "Value"}]
    if price_indexes:
        for line in rows:
            for index in price_indexes:
                read_price_cell(_year_field(line, index))
    return None


def _year_span() -> str:
    return f"{int(PIN_TABLE['year_min'])}-{int(PIN_TABLE['year_max'])}"


def accept_filter2_output(
    path: Path,
    *,
    hedonic_rows: Sequence[Mapping] | None = None,
    manifest: dict[str, object] | None = None,
    run_fit: bool = True,
) -> D7ChainResult:
    """Hash, then row count and years, then the fit hook."""
    recorded = dict(d7_provenance_manifest() if manifest is None else manifest)
    if not path.is_file():
        return _result(
            _not_run("D7_FILTER2_OUT", "sha256", PIN_TABLE["filter2_output"], "absent"),
            recorded,
        )
    actual = sha256_file(path)
    recorded["filter2_output_actual"] = actual
    recorded["filter2_output_sha256"] = actual
    expected = str(PIN_TABLE["filter2_output"])
    if not _full_match(actual, expected):
        return _result(_not_run("D7_FILTER2_OUT", "sha256", expected, actual), recorded)
    message = inspect_filter2_output(path)
    if message:
        return _result(message, recorded)
    delivered = actual
    fitted = None
    s_x2 = "NOT_RUN"
    if run_fit:
        fitted = fit_headline(list(hedonic_rows or []), d7_sha256=delivered)
        s_x2 = "fit"
    return D7ChainResult(
        status="passed",
        message="",
        manifest=recorded,
        d7_sha256=delivered,
        s_x2=s_x2,
        fitted=fitted if isinstance(fitted, dict) else None,
    )


def run_d7_chain(
    *,
    source: Path,
    filter1_script: Path,
    filter1_output: Path,
    filter2_script: Path,
    filter2_output: Path,
    hedonic_rows: Sequence[Mapping] | None = None,
    run_fit: bool = True,
) -> D7ChainResult:
    """Source, filter1 script, filter1 output, filter2 script, filter2 output.

    A mismatch returns NOT_RUN and does not call the next step.
    """
    manifest: dict[str, object] = d7_provenance_manifest()
    if not source.is_file():
        return _result(_not_run("D7_SOURCE", "sha256", PIN_TABLE["source"], "absent"), manifest)
    source_sha = sha256_file(source)
    manifest["source_actual"] = source_sha
    if not _full_match(source_sha, str(PIN_TABLE["source"])):
        return _result(
            _not_run("D7_SOURCE", "sha256", PIN_TABLE["source"], source_sha),
            manifest,
        )
    if not filter1_script.is_file():
        return _result(
            _not_run("D7_FILTER1", "script sha256", PIN_TABLE["filter1_script"], "absent"),
            manifest,
        )
    filter1_sha = sha256_file(filter1_script)
    manifest["filter1_script_sha256"] = filter1_sha
    if not _full_match(filter1_sha, str(PIN_TABLE["filter1_script"])):
        return _result(
            _not_run("D7_FILTER1", "script sha256", PIN_TABLE["filter1_script"], filter1_sha),
            manifest,
        )
    execute_filter1(filter1_script, source, filter1_output)
    if not filter1_output.is_file():
        return _result(
            _not_run("D7_FILTER1_OUT", "sha256", PIN_TABLE["filter1_output"], "absent"),
            manifest,
        )
    filter1_out = sha256_file(filter1_output)
    manifest["filter1_output_actual"] = filter1_out
    if not _full_match(filter1_out, str(PIN_TABLE["filter1_output"])):
        return _result(
            _not_run("D7_FILTER1_OUT", "sha256", PIN_TABLE["filter1_output"], filter1_out),
            manifest,
        )
    if not filter2_script.is_file():
        return _result(
            _not_run("D7_FILTER2", "script sha256", PIN_TABLE["filter2_script"], "absent"),
            manifest,
        )
    filter2_sha = sha256_file(filter2_script)
    manifest["filter2_script_sha256"] = filter2_sha
    if not _full_match(filter2_sha, str(PIN_TABLE["filter2_script"])):
        return _result(
            _not_run("D7_FILTER2", "script sha256", PIN_TABLE["filter2_script"], filter2_sha),
            manifest,
        )
    execute_filter2(filter2_script, filter1_output, filter2_output)
    return accept_filter2_output(
        filter2_output,
        hedonic_rows=hedonic_rows,
        manifest=manifest,
        run_fit=run_fit,
    )
