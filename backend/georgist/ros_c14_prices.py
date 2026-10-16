"""2024 primary price per DZ2011. Scored-run only.

This is the only module that may request the C14 "total value" column, and
only when ``scored_run`` is true and the caller is the run entry point
``scripts/build_v14_primary_inputs.py``. Default mode raises if that column
is requested. Values are never written to stdout or logs.
"""

from __future__ import annotations

import inspect
import logging
from collections import defaultdict
from pathlib import Path
from typing import Mapping

from georgist.ros_c14_input import (
    SCORING_YEAR,
    SCOTLAND_CODE,
    InputBuildError,
    _e8_keep,
    _load_crosswalk,
    _parse_volume,
    _parse_year,
    _read_csv_rows,
    _read_xlsx_rows,
)

logger = logging.getLogger(__name__)

MEDIAN_SENSITIVITY = "not_crosswalkable"
ENTRY_POINT_MODULE = "build_v14_primary_inputs.py"
COUNT_COLUMNS = (
    "calendar year",
    "data zone code",
    "volume",
)
TOTAL_VALUE_COLUMN = "total value"


class PriceColumnError(RuntimeError):
    """Price columns were requested outside a scored run."""


def requested_columns(*, scored_run: bool, price_columns: bool) -> tuple[str, ...]:
    """Columns to ask the C14 reader for.

    Default mode (``scored_run`` false) raises when price columns are requested
    and otherwise returns the count columns only.
    """
    if price_columns and not scored_run:
        raise PriceColumnError(
            "total value is requested only when scored_run is true"
        )
    if price_columns:
        return COUNT_COLUMNS + (TOTAL_VALUE_COLUMN,)
    return COUNT_COLUMNS


def _from_run_entry_point() -> bool:
    for frame in inspect.stack():
        if frame.function == "main" and frame.filename.endswith(ENTRY_POINT_MODULE):
            return True
    return False


def _read_rows(path: Path, names: tuple[str, ...]) -> list[dict[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv_rows(path, names)
    if suffix in {".xlsx", ".xlsm"}:
        return _read_xlsx_rows(path, names)
    raise InputBuildError(f"unsupported C14 file type: {suffix}")


def _parse_total_value(raw: str) -> float:
    text = str(raw).strip()
    if not text or "[c]" in text or "[z]" in text:
        raise PriceColumnError("total value cell is not numeric")
    try:
        value = float(text)
    except ValueError:
        raise PriceColumnError("total value cell is not numeric") from None
    if value < 0:
        raise PriceColumnError("total value cell is negative")
    return value


def read_value_volume(path: Path, *, scored_run: bool) -> dict[str, tuple[float, float]]:
    """Sum total value and volume for scoring-year rows that are not suppressed.

    Refuses to run unless this is a scored run called from the entry point.
    The returned map is for the crosswalk; it is not logged.
    """
    names = requested_columns(scored_run=scored_run, price_columns=True)
    if not _from_run_entry_point():
        raise PriceColumnError(
            "total value is requested only from the scored-run entry point"
        )
    projected = _read_rows(path, names)
    totals: dict[str, list[float]] = {}
    for row in projected:
        year = _parse_year(row.get("calendar year", ""))
        if year != SCORING_YEAR:
            continue
        code = str(row.get("data zone code", "")).strip().upper()
        if not code or code == SCOTLAND_CODE:
            continue
        volume, suppressed = _parse_volume(row.get("volume", ""))
        if suppressed or volume is None:
            continue
        value = _parse_total_value(row.get(TOTAL_VALUE_COLUMN, ""))
        bucket = totals.setdefault(code, [0.0, 0.0])
        bucket[0] += value
        bucket[1] += float(volume)
    logger.info("price columns read for scoring year; values not logged")
    return {code: (pair[0], pair[1]) for code, pair in totals.items()}


def crosswalk_means(
    *,
    dz2022_status: Mapping[str, str],
    crosswalk_path: Path,
    value_volume_by_dz2022: Mapping[str, tuple[float, float]],
) -> dict[str, float]:
    """Sales-weighted mean on O-D1 weights. Status ``ok`` only.

    mean_i = sum_j v_ij * value_j / sum_j v_ij * volume_j.
    Suppressed, name-collision and absent sources contribute nothing.
    Missing sources are left missing. They are not imputed.
    """
    edges = _e8_keep(_load_crosswalk(crosswalk_path))
    numerator: dict[str, float] = defaultdict(float)
    denominator: dict[str, float] = defaultdict(float)
    for edge in edges:
        source = str(edge["dz2022"])
        if dz2022_status.get(source) != "ok":
            continue
        pair = value_volume_by_dz2022.get(source)
        if pair is None:
            continue
        value_j, volume_j = pair
        weight = float(edge["v"])
        target = str(edge["dz2011"])
        numerator[target] += weight * float(value_j)
        denominator[target] += weight * float(volume_j)
    means: dict[str, float] = {}
    for code, weight_volume in denominator.items():
        if weight_volume <= 0:
            continue
        means[code] = numerator[code] / weight_volume
    return means


def dz2022_status_map(inputs: Mapping) -> dict[str, str]:
    """Status by DZ2022 code from ``build_inputs`` (``ok`` is the price source)."""
    return {str(zone["code"]): str(zone["status"]) for zone in inputs["dz2022"]}
