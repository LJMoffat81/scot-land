"""v1.4 hedonic secondary estimator.

Headline form is the log WLS in the frozen plan. The levels form and the
named sensitivities are information only and are never swapped in. No 2024
price file is read. Cluster bootstrap seed and replicate count are fixed.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np

BOOTSTRAP_SEED = 20261015
BOOTSTRAP_REPS = 1999
CI_WIDTH_NOT_INFORMATIVE = 0.5
FIT_YEARS = (2021, 2022)
MIN_SALES_PER_YEAR = 5
MIN_SALES_POOLED = 10

SENSITIVITY_IDS = (
    "S-c1",
    "S-c2",
    "S-c3",
    "S-x1",
    "S-x2",
    "S-x3",
    "S-x4",
    "S-x5",
    "S-x6",
    "r20",
    "r40",
    "S-g1",
    "median_price",
)
INTERNAL_ONLY = frozenset({"S-x4"})
FIDELITY_LIMITATION = (
    "Fidelity limitation: the frozen 'negative location premium' test is not "
    "operationalised in e1ab6d0a; only β̂ ≤0 is applied. No post-hoc definition."
)


class HedonicError(ValueError):
    """The hedonic fit cannot proceed."""


class PriceYearError(HedonicError):
    """A 2024 price was requested outside the frozen-coefficient path."""


def assert_development_years(years: Sequence[int]) -> None:
    """Development and tests stay on 2004–2023. 2024 is not read."""
    for year in years:
        value = int(year)
        if value == 2024:
            raise PriceYearError("2024 prices are not read in development or test")
        if value < 2004 or value > 2023:
            raise PriceYearError(f"year {value} is outside the seen development window")


def refuse_2024_price_file(name: str) -> None:
    """Default mode never opens a 2024 price file."""
    if "2024" in str(name):
        raise PriceYearError("no 2024 price file in development or test")


def _eligible(rows: Sequence[Mapping]) -> list[Mapping]:
    by_zone: dict[str, dict[int, Mapping]] = {}
    for row in rows:
        year = int(row["year"])
        assert_development_years([year])
        if year not in FIT_YEARS:
            continue
        zone = str(row["zone"])
        by_zone.setdefault(zone, {})[year] = row
    kept: list[Mapping] = []
    for years in by_zone.values():
        if set(FIT_YEARS) - set(years):
            continue
        if any(int(years[year]["n_sales"]) < MIN_SALES_PER_YEAR for year in FIT_YEARS):
            continue
        pooled = sum(int(years[year]["n_sales"]) for year in FIT_YEARS)
        if pooled < MIN_SALES_POOLED:
            continue
        kept.extend(years[year] for year in FIT_YEARS)
    if len(kept) < 4:
        raise HedonicError("fit window has too few rows")
    return kept


def _design(
    rows: Sequence[Mapping],
    *,
    area_field: str = "a_m2",
    include_floor: bool = True,
    price_field: str = "price",
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    cells = sorted({str(row["cell"]) for row in rows})
    names: list[str] = []
    columns: list[np.ndarray] = []
    for cell in cells:
        mask = np.array([1.0 if str(row["cell"]) == cell else 0.0 for row in rows])
        names.append(f"alpha[{cell}]")
        columns.append(mask)
    year = np.array([1.0 if int(row["year"]) == 2022 else 0.0 for row in rows])
    names.append("tau_2022")
    columns.append(year)
    for cell in cells:
        area = np.array(
            [
                math.log(float(row[area_field])) if str(row["cell"]) == cell else 0.0
                for row in rows
            ]
        )
        names.append(f"beta[{cell}]")
        columns.append(area)
        if include_floor:
            floor = np.array(
                [
                    math.log(float(row["f_m2"])) if str(row["cell"]) == cell else 0.0
                    for row in rows
                ]
            )
            names.append(f"delta[{cell}]")
            columns.append(floor)
    x_names = sorted({key for row in rows for key in row.keys() if str(key).startswith("x_")})
    for key in x_names:
        names.append(key)
        columns.append(np.array([float(row[key]) for row in rows]))
    x = np.column_stack(columns)
    y = np.array([math.log(float(row[price_field])) for row in rows])
    w = np.array([float(row["n_sales"]) for row in rows])
    if np.any(w <= 0) or np.any(~np.isfinite(y)):
        raise HedonicError("weights and log price must be finite and positive")
    return x, y, w, names


def _wls(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    scale = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(x * scale[:, None], y * scale, rcond=None)
    return np.asarray(beta, dtype=float)


def _feature_value(name: str, row: Mapping) -> float:
    """One headline-design column for a single zone-year row."""
    if name.startswith("alpha["):
        cell = name[len("alpha[") : -1]
        return 1.0 if str(row["cell"]) == cell else 0.0
    if name == "tau_2022":
        return 1.0 if int(row.get("year", 0)) == 2022 else 0.0
    if name.startswith("beta["):
        cell = name[len("beta[") : -1]
        if str(row["cell"]) != cell:
            return 0.0
        return math.log(float(row["a_m2"]))
    if name.startswith("delta["):
        cell = name[len("delta[") : -1]
        if str(row["cell"]) != cell:
            return 0.0
        return math.log(float(row["f_m2"]))
    if name.startswith("x_"):
        return float(row[name])
    raise HedonicError(f"unknown coefficient {name}")


def fitted_price(fit: Mapping, row: Mapping) -> float:
    """P̂_z from the headline log model. Observed price is not used."""
    names = list(fit["coefficient_names"])
    coef = [float(value) for value in fit["coefficients"]]
    if len(names) != len(coef):
        raise HedonicError("coefficient names do not match the headline fit")
    log_price = 0.0
    for name, value in zip(names, coef):
        log_price += _feature_value(name, row) * value
    return math.exp(log_price)


def _beta_by_cell(names: Sequence[str], coef: np.ndarray) -> dict[str, float]:
    out: dict[str, float] = {}
    for name, value in zip(names, coef):
        if name.startswith("beta["):
            out[name[5:-1]] = float(value)
    return out


def _percentile_ci(samples: Sequence[float]) -> dict[str, float]:
    arr = np.asarray(list(samples), dtype=float)
    low, high = np.quantile(arr, [0.025, 0.975])
    return {"low": float(low), "high": float(high), "width": float(high - low)}


def _fit_rows(
    rows: Sequence[Mapping],
    *,
    area_field: str = "a_m2",
    include_floor: bool = True,
    price_field: str = "price",
) -> tuple[np.ndarray, list[str], dict[str, float]]:
    x, y, w, names = _design(
        rows,
        area_field=area_field,
        include_floor=include_floor,
        price_field=price_field,
    )
    coef = _wls(x, y, w)
    return coef, names, _beta_by_cell(names, coef)


def _cluster_index(rows: Sequence[Mapping], field: str) -> list[np.ndarray]:
    groups: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        groups.setdefault(str(row[field]), []).append(index)
    return [np.asarray(indexes, dtype=int) for indexes in groups.values()]


def _resample_beta(
    rows: Sequence[Mapping],
    indexes: Sequence[int],
    *,
    area_field: str,
    include_floor: bool,
) -> dict[str, float] | None:
    sample = [rows[int(index)] for index in indexes]
    try:
        _coef, _names, beta = _fit_rows(sample, area_field=area_field, include_floor=include_floor)
    except (HedonicError, np.linalg.LinAlgError, ValueError):
        return None
    return beta


def iz_cluster_bootstrap(
    rows: Sequence[Mapping],
    *,
    area_field: str = "a_m2",
    include_floor: bool = True,
    seed: int = BOOTSTRAP_SEED,
    reps: int = BOOTSTRAP_REPS,
) -> dict[str, dict]:
    """Percentile 95% CI from an IZ2011 cluster bootstrap. This CI gates nothing here."""
    clusters = _cluster_index(rows, "iz")
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {}
    completed = 0
    for _ in range(reps):
        chosen = rng.integers(0, len(clusters), size=len(clusters))
        indexes = np.concatenate([clusters[int(item)] for item in chosen])
        beta = _resample_beta(rows, indexes, area_field=area_field, include_floor=include_floor)
        if beta is None:
            continue
        completed += 1
        for cell, value in beta.items():
            draws.setdefault(cell, []).append(value)
    cis = {cell: _percentile_ci(values) for cell, values in draws.items() if values}
    return {
        "seed": seed,
        "reps": reps,
        "reps_completed": completed,
        "cluster": "IZ2011",
        "ci_by_cell": cis,
        "gates": False,
    }


def ca_wild_cluster_bootstrap(
    rows: Sequence[Mapping],
    coef: np.ndarray,
    names: Sequence[str],
    *,
    area_field: str = "a_m2",
    include_floor: bool = True,
    seed: int = BOOTSTRAP_SEED,
    reps: int = BOOTSTRAP_REPS,
) -> dict[str, dict]:
    """Rademacher wild-cluster bootstrap by council area. Information only."""
    x, y, w, design_names = _design(rows, area_field=area_field, include_floor=include_floor)
    if list(design_names) != list(names):
        raise HedonicError("wild-cluster design does not match the headline fit")
    fitted = x @ coef
    residual = y - fitted
    clusters = _cluster_index(rows, "ca")
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {}
    completed = 0
    for _ in range(reps):
        signs = rng.choice(np.array([-1.0, 1.0]), size=len(clusters))
        y_star = fitted.copy()
        for sign, indexes in zip(signs, clusters):
            y_star[indexes] = fitted[indexes] + float(sign) * residual[indexes]
        try:
            star = _wls(x, y_star, w)
            beta = _beta_by_cell(names, star)
        except (HedonicError, np.linalg.LinAlgError, ValueError):
            continue
        completed += 1
        for cell, value in beta.items():
            draws.setdefault(cell, []).append(value)
    return {
        "seed": seed,
        "reps": reps,
        "reps_completed": completed,
        "cluster": "CA2019",
        "weights": "rademacher",
        "information_only": True,
        "gates": False,
        "replaces_iz_ci": False,
        "ci_by_cell": {cell: _percentile_ci(values) for cell, values in draws.items() if values},
    }


def _levels_beta(rows: Sequence[Mapping]) -> dict[str, float]:
    """Levels form. Returned only as a sensitivity, never as the headline share."""
    cells = sorted({str(row["cell"]) for row in rows})
    columns: list[np.ndarray] = []
    names: list[str] = []
    for cell in cells:
        mask = np.array([1.0 if str(row["cell"]) == cell else 0.0 for row in rows])
        names.append(f"alpha[{cell}]")
        columns.append(mask)
        area = np.array(
            [float(row["a_m2"]) if str(row["cell"]) == cell else 0.0 for row in rows]
        )
        names.append(f"lambda[{cell}]")
        columns.append(area)
    x = np.column_stack(columns)
    y = np.array([float(row["price"]) for row in rows])
    w = np.array([float(row["n_sales"]) for row in rows])
    coef = _wls(x, y, w)
    return {
        name[7:-1]: float(value)
        for name, value in zip(names, coef)
        if name.startswith("lambda[")
    }


def _sensitivity_row(name: str, *, status: str, beta: Mapping[str, float] | None = None) -> dict:
    return {
        "id": name,
        "status": status,
        "gates": False,
        "information_only": True,
        "swapped_in": False,
        "internal_only": name in INTERNAL_ONLY,
        "publish": name not in INTERNAL_ONLY,
        "beta_by_cell": None if beta is None else {key: float(value) for key, value in beta.items()},
    }


def sensitivity_table(rows: Sequence[Mapping], headline: Mapping[str, float]) -> list[dict]:
    """Named sensitivities. None of them replaces the headline log coefficients."""
    table = [
        _sensitivity_row("levels", status="fit", beta=_levels_beta(rows)),
    ]
    try:
        _coef, _names, dropped = _fit_rows(rows, include_floor=False)
        table.append(_sensitivity_row("S-x1", status="fit", beta=dropped))
    except HedonicError:
        table.append(_sensitivity_row("S-x1", status="not_in_fixture"))
    if rows and "median_price" in rows[0]:
        _coef, _names, median_beta = _fit_rows(rows, price_field="median_price")
        table.append(_sensitivity_row("median_price", status="reported_never_swapped_in", beta=median_beta))
    else:
        table.append(_sensitivity_row("median_price", status="not_crosswalkable"))
    for name, field in (("r20", "a_r20"), ("r40", "a_r40")):
        if rows and field in rows[0]:
            _coef, _names, beta = _fit_rows(rows, area_field=field)
            table.append(_sensitivity_row(name, status="fit", beta=beta))
        else:
            table.append(_sensitivity_row(name, status="not_in_fixture"))
    for name in SENSITIVITY_IDS:
        if any(item["id"] == name for item in table):
            continue
        table.append(_sensitivity_row(name, status="specified_information_only"))
    for item in table:
        if item["gates"] or item["swapped_in"]:
            raise HedonicError("a sensitivity would gate or replace the headline")
        if item["beta_by_cell"] is not None and item["id"] == "levels":
            continue
        if item["beta_by_cell"] == dict(headline) and item["id"] not in {"levels"}:
            continue
    return table


def fit_headline(rows: Sequence[Mapping]) -> dict:
    """Log-form WLS, then both bootstraps. Levels coefficients are not returned as shares."""
    kept = _eligible(rows)
    coef, names, beta = _fit_rows(kept)
    iz_ci = iz_cluster_bootstrap(kept)
    iz_snapshot = {
        "seed": iz_ci["seed"],
        "reps": iz_ci["reps"],
        "reps_completed": iz_ci["reps_completed"],
        "ci_by_cell": {cell: dict(bounds) for cell, bounds in iz_ci["ci_by_cell"].items()},
    }
    wild = ca_wild_cluster_bootstrap(kept, coef, names)
    if iz_ci["ci_by_cell"] != iz_snapshot["ci_by_cell"] or iz_ci["reps"] != iz_snapshot["reps"]:
        raise HedonicError("wild-cluster bootstrap changed the IZ interval")
    informative = {
        cell: ci["width"] <= CI_WIDTH_NOT_INFORMATIVE
        for cell, ci in iz_ci["ci_by_cell"].items()
    }
    # β̂ ≤0 only. The frozen negative-location-premium wording has no operational test.
    failures = {cell: value <= 0 for cell, value in beta.items()}
    return {
        "form": "log",
        "headline_form": "log",
        "levels_swapped_in": False,
        "fidelity_limitation": FIDELITY_LIMITATION,
        "beta_by_cell": beta,
        "coefficient_names": names,
        "coefficients": [float(value) for value in coef],
        "iz_ci": iz_ci,
        "iz_ci_before_wild": iz_snapshot,
        "wild_cluster": wild,
        "model_failure_by_cell": failures,
        "informative_by_cell": informative,
        "seed": BOOTSTRAP_SEED,
        "reps": BOOTSTRAP_REPS,
        "gates_use": "iz_point_beta",
        "sensitivities": sensitivity_table(kept, beta),
    }


def land_share_for_zone(fit: Mapping, row: Mapping) -> dict:
    """Share is the cell elasticity. A non-positive elasticity is unavailable."""
    cell = str(row["cell"])
    beta = float(fit["beta_by_cell"][cell])
    failure = bool(fit["model_failure_by_cell"][cell]) or beta <= 0
    informative = bool(fit["informative_by_cell"].get(cell, True))
    share = 0.0 if failure else beta
    predicted = None if failure else fitted_price(fit, row)
    return {
        "zone": str(row["zone"]),
        "cell": cell,
        "share": share,
        "unavailable": failure,
        "model_failure": failure,
        "count_in_1d": informative,
        "fitted_price": predicted,
        "land_per_home": 0.0 if predicted is None else beta * predicted,
        "beta": beta,
        "fidelity_limitation": FIDELITY_LIMITATION,
    }


def apply_frozen_coefficients(fit: Mapping, rows: Sequence[Mapping]) -> dict:
    """Apply the 2021–22 coefficients. Does not refit and does not read a file."""
    before = [float(value) for value in fit["coefficients"]]
    beta = dict(fit["beta_by_cell"])
    applied = []
    for row in rows:
        cell = str(row["cell"])
        if cell not in beta:
            raise HedonicError(f"no frozen coefficient for {cell}")
        value = float(beta[cell])
        applied.append(
            {
                "zone": str(row["zone"]),
                "year": int(row["year"]),
                "share": 0.0 if value <= 0 else value,
                "refit": False,
            }
        )
    after = [float(value) for value in fit["coefficients"]]
    if before != after or dict(fit["beta_by_cell"]) != beta:
        raise HedonicError("applying frozen coefficients refit the model")
    return {"refit": False, "coefficients_unchanged": True, "zones": applied}
