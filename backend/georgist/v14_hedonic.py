"""v1.4 hedonic secondary estimator.

Headline form is the log WLS in the frozen plan. The levels form and the
named sensitivities are information only and are never swapped in. No 2024
price file is read. Cluster bootstrap seed and replicate count are fixed.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np
from statsmodels.base.model import LikelihoodModel
from statsmodels.regression.mixed_linear_model import MixedLM

from georgist.v14_d7_chain import (
    D7_FILTER2_OUTPUT_SHA256,
    d7_provenance_manifest,
    provenance_accepts,
    register_fit_headline,
)

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
S_G1_REASON = "no frozen DZ2022 price input"
MEDIAN_2024_REASON = "not_crosswalkable"
# Filter2 output of the pinned D7 chain (source d99b8daa, then both filters).
# S-x2 accepts this digest only through provenance_accepts, not as a bare prefix.
D7_SHA256 = D7_FILTER2_OUTPUT_SHA256
S_C3_REML = True
S_C3_METHOD = "lbfgs"
S_C3_MAXITER = 1000
S_C3_GTOL = 1e-8
DECLARED_STATUS = {
    "S-c1": ("fit", "UR6 x ITL3"),
    "S-c2": ("fit", "national UR3 with IZ2011 fixed effects"),
    "S-c3": ("fit", "REML MixedLM on the fit-window rows"),
    "S-x1": ("fit", "drops F"),
    "S-x2": ("fit", "fit when the D7 provenance chain accepts the filter2 sha, otherwise NOT_RUN"),
    "S-x3": ("fit", "flat share above 0.5 and at or below 0.5, reported separately"),
    "S-x4": ("fit", "internal only, never published"),
    "S-x5": ("fit", "RoS median on the fit window"),
    "S-x6": ("fit", "drops flagged zones"),
    "r20": ("fit", "plot split r20, with the FRAGILE rule"),
    "r40": ("fit", "plot split r40, with the FRAGILE rule"),
    "S-g1": ("NOT_RUN", S_G1_REASON),
    "median_price": ("fit", "fit window; 2024 median NOT_RUN: not_crosswalkable"),
}
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


def _sensitivity_row(
    name: str,
    *,
    status: str,
    beta: Mapping[str, float] | None = None,
    reason: str = "",
    converged: bool | None = None,
    fragile: bool | None = None,
    by_split: Mapping | None = None,
) -> dict:
    row = {
        "id": name,
        "status": status,
        "reason": reason,
        "gates": False,
        "information_only": True,
        "swapped_in": False,
        "internal_only": name in INTERNAL_ONLY,
        "publish": name not in INTERNAL_ONLY,
        "beta_by_cell": None if beta is None else {key: float(value) for key, value in beta.items()},
    }
    if converged is not None:
        row["converged"] = converged
    if fragile is not None:
        row["fragile"] = fragile
    if by_split is not None:
        row["by_split"] = by_split
    return row


def sensitivity_manifest() -> list[dict]:
    """Declared before any 2023 outcome. No id can be added after this list."""
    manifest = []
    for name in SENSITIVITY_IDS:
        status, reason = DECLARED_STATUS[name]
        item = {
            "id": name,
            "status": status,
            "reason": reason,
            "gates": False,
            "information_only": True,
            "swapped_in": False,
            "internal_only": name in INTERNAL_ONLY,
            "publish": name not in INTERNAL_ONLY,
        }
        if name == "S-x2":
            item["d7_provenance"] = d7_provenance_manifest()
        manifest.append(item)
    return manifest


def _with_cell(rows: Sequence[Mapping], cell_of) -> list[dict]:
    copied: list[dict] = []
    for row in rows:
        item = dict(row)
        item["cell"] = cell_of(row)
        copied.append(item)
    return copied


def _fit_named(name: str, rows: Sequence[Mapping], **kwargs) -> dict:
    try:
        _coef, _names, beta = _fit_rows(rows, **kwargs)
    except (HedonicError, np.linalg.LinAlgError, ValueError, KeyError, ZeroDivisionError) as exc:
        return _sensitivity_row(name, status="NOT_RUN", reason=str(exc))
    return _sensitivity_row(name, status="fit", beta=beta)


def _iz_code(row: Mapping) -> str:
    return str(row.get("iz2011") or row.get("iz") or "")


def _ur3(row: Mapping) -> str:
    if row.get("ur3"):
        return str(row["ur3"])
    ur6 = row.get("ur6")
    if ur6 is None:
        return ""
    klass = int(ur6)
    if klass in (1, 2):
        return "urban"
    if klass in (3, 4):
        return "towns"
    if klass in (5, 6):
        return "rural"
    return ""


def _fit_s_c1(rows: Sequence[Mapping]) -> dict:
    if any("ur6" not in row or "itl3" not in row for row in rows):
        return _sensitivity_row("S-c1", status="NOT_RUN", reason="UR6 or ITL3 is not on the rows")
    return _fit_named("S-c1", _with_cell(rows, lambda row: f"{row['ur6']}|{row['itl3']}"))


def _fit_s_c2(rows: Sequence[Mapping]) -> dict:
    if any(not _iz_code(row) or not _ur3(row) for row in rows):
        return _sensitivity_row("S-c2", status="NOT_RUN", reason="UR3 or IZ2011 is not on the rows")
    iz_codes = sorted({_iz_code(row) for row in rows})
    kept_effects = iz_codes[1:]
    prepared = []
    for row in rows:
        item = dict(row)
        item["cell"] = _ur3(row)
        code = _iz_code(row)
        for effect in kept_effects:
            item[f"x_iz_{effect}"] = 1.0 if code == effect else 0.0
        prepared.append(item)
    return _fit_named("S-c2", prepared)


def _fit_mixedlm(endog, exog, groups, exog_re):
    """Fit once with lbfgs. gtol=1e-8 maps to L-BFGS-B pgtol=1e-8.

    factr and every other optimiser option stay at their defaults.
    No retry and no solver swap. MixedLM.fit drops pgtol before the
    lbfgs solver (its allow-list still names gtol, which lbfgs ignores),
    so the parent fit receives pgtol after that filter.
    """
    model = MixedLM(endog, exog, groups, exog_re=exog_re)
    original = LikelihoodModel.fit

    def _with_pgtol(self, *args, **kwargs):
        kwargs.pop("gtol", None)
        kwargs["pgtol"] = S_C3_GTOL
        return original(self, *args, **kwargs)

    LikelihoodModel.fit = _with_pgtol
    try:
        # pgtol is applied on the parent fit. Passing it here is dropped by
        # MixedLM.fit's allow-list, which still names the ignored gtol.
        return model.fit(
            reml=S_C3_REML,
            method=S_C3_METHOD,
            maxiter=S_C3_MAXITER,
        )
    finally:
        LikelihoodModel.fit = original


def _fit_s_c3(rows: Sequence[Mapping]) -> dict:
    """Partial pooling of the land slope. No second solver and no retune."""
    try:
        y = np.array([math.log(float(row["price"])) for row in rows])
        area = np.array([math.log(float(row["a_m2"])) for row in rows])
        exog = np.column_stack([np.ones(len(rows)), area])
        groups = np.array([str(row.get("ur3") or row.get("cell") or "") for row in rows])
        if len(set(groups)) < 2 or any(not group for group in groups):
            return _sensitivity_row(
                "S-c3",
                status="NOT_RUN",
                reason="MixedLM needs two or more groups",
                converged=False,
            )
        result = _fit_mixedlm(y, exog, groups, area.reshape(-1, 1))
    except Exception as exc:
        return _sensitivity_row("S-c3", status="ERROR", reason=str(exc), converged=False)
    converged = bool(getattr(result, "converged", False))
    if not converged:
        return _sensitivity_row(
            "S-c3",
            status="NOT_CONVERGED",
            reason="MixedLM did not converge",
            converged=False,
        )
    slope = float(np.asarray(result.fe_params, dtype=float)[1])
    return _sensitivity_row("S-c3", status="fit", reason="converged", beta={"pooled": slope}, converged=True)


def _fit_s_x2(rows: Sequence[Mapping], d7_sha256: str | None) -> dict:
    if not provenance_accepts(d7_sha256):
        return _sensitivity_row("S-x2", status="NOT_RUN", reason="D7 sha does not match")
    if any("ratio_mean" not in row for row in rows):
        return _sensitivity_row("S-x2", status="NOT_RUN", reason="D7 ratio_mean is not on the rows")
    kept = [row for row in rows if 0.9 <= float(row["ratio_mean"]) <= 1.1]
    if len(kept) < 4:
        return _sensitivity_row("S-x2", status="NOT_RUN", reason="sold/stock band has too few rows")
    return _fit_named("S-x2", kept)


def _flat_share(row: Mapping) -> float | None:
    if "flat_share" in row:
        return float(row["flat_share"])
    if "pt_flat_share" in row:
        return float(row["pt_flat_share"]) + float(row.get("pt_maisonette_share") or 0.0)
    return None


def _fit_s_x3(rows: Sequence[Mapping]) -> dict:
    shares = [_flat_share(row) for row in rows]
    if any(share is None for share in shares):
        return _sensitivity_row("S-x3", status="NOT_RUN", reason="flat share is not on the rows")
    above = [row for row, share in zip(rows, shares) if share is not None and share > 0.5]
    at_or_below = [row for row, share in zip(rows, shares) if share is not None and share <= 0.5]
    high = _fit_named("S-x3", above)
    low = _fit_named("S-x3", at_or_below)
    if high["status"] != "fit" and low["status"] != "fit":
        return _sensitivity_row("S-x3", status="NOT_RUN", reason=high["reason"] or low["reason"])
    return _sensitivity_row(
        "S-x3",
        status="fit",
        by_split={">0.5": high["beta_by_cell"], "<=0.5": low["beta_by_cell"]},
    )


def _fit_s_x4(rows: Sequence[Mapping]) -> dict:
    if any("other_land_per_home" not in row for row in rows):
        return _sensitivity_row("S-x4", status="NOT_RUN", reason="D5 other land per home is not on the rows")
    prepared = []
    for row in rows:
        item = dict(row)
        item["x_other_land_per_home"] = math.log(1.0 + float(row["other_land_per_home"]))
        prepared.append(item)
    fitted = _fit_named("S-x4", prepared)
    fitted["internal_only"] = True
    fitted["publish"] = False
    return fitted


def _median_fit(name: str, rows: Sequence[Mapping]) -> dict:
    if any(int(row["year"]) >= 2024 for row in rows):
        return _sensitivity_row(name, status="NOT_RUN", reason=MEDIAN_2024_REASON)
    if any("median_price" not in row for row in rows):
        return _sensitivity_row(name, status="NOT_RUN", reason="median price is not on the fit-window rows")
    return _fit_named(name, rows, price_field="median_price")


def _fit_s_x6(rows: Sequence[Mapping]) -> dict:
    if not any("low_parcel_coverage" in row or "flagged" in row for row in rows):
        return _sensitivity_row("S-x6", status="NOT_RUN", reason="zone flags are not on the rows")
    kept = []
    for row in rows:
        flagged = bool(row.get("flagged")) or float(row.get("low_parcel_coverage") or 0.0) >= 0.5
        if not flagged:
            kept.append(row)
    if len(kept) < 4:
        return _sensitivity_row("S-x6", status="NOT_RUN", reason="dropping flagged zones leaves too few rows")
    return _fit_named("S-x6", kept)


def _fragile(left: Mapping[str, float] | None, right: Mapping[str, float] | None) -> bool:
    if not left or not right:
        return False
    for cell in set(left) | set(right):
        if cell not in left or cell not in right:
            continue
        a = float(left[cell])
        b = float(right[cell])
        if (a > 0) != (b > 0) or (a < 0) != (b < 0) or abs(a - b) > CI_WIDTH_NOT_INFORMATIVE:
            return True
    return False


def sensitivity_table(
    rows: Sequence[Mapping],
    headline: Mapping[str, float],
    *,
    d7_sha256: str | None = None,
    d7_accept: bool = True,
) -> list[dict]:
    """Named sensitivities. None of them replaces the headline log coefficients."""
    listed = list(rows)
    if any(int(row.get("year", 0)) >= 2024 for row in listed):
        raise PriceYearError("2024 prices are not read in development or test")
    r20 = (
        _fit_named("r20", listed, area_field="a_r20")
        if listed and "a_r20" in listed[0]
        else _sensitivity_row("r20", status="NOT_RUN", reason="r20 plot area is not on the rows")
    )
    r40 = (
        _fit_named("r40", listed, area_field="a_r40")
        if listed and "a_r40" in listed[0]
        else _sensitivity_row("r40", status="NOT_RUN", reason="r40 plot area is not on the rows")
    )
    fragile = _fragile(r20.get("beta_by_cell"), r40.get("beta_by_cell"))
    if r20["status"] == "fit" and r40["status"] == "fit":
        r20["fragile"] = fragile
        r40["fragile"] = fragile
    by_id = {
        "S-c1": _fit_s_c1(listed),
        "S-c2": _fit_s_c2(listed),
        "S-c3": _fit_s_c3(listed),
        "S-x1": _fit_named("S-x1", listed, include_floor=False),
        "S-x2": (
            _fit_s_x2(listed, d7_sha256)
            if d7_accept
            else _sensitivity_row("S-x2", status="NOT_RUN", reason="D7 sha does not match")
        ),
        "S-x3": _fit_s_x3(listed),
        "S-x4": _fit_s_x4(listed),
        "S-x5": _median_fit("S-x5", listed),
        "S-x6": _fit_s_x6(listed),
        "r20": r20,
        "r40": r40,
        "S-g1": _sensitivity_row("S-g1", status="NOT_RUN", reason=S_G1_REASON),
        "median_price": _median_fit("median_price", listed),
    }
    table = [_sensitivity_row("levels", status="fit", beta=_levels_beta(listed))]
    table.extend(by_id[name] for name in SENSITIVITY_IDS)
    allowed = set(SENSITIVITY_IDS) | {"levels"}
    extra = [item["id"] for item in table if item["id"] not in allowed]
    if extra:
        raise HedonicError(f"sensitivity added after the manifest: {extra}")
    for item in table:
        if item["gates"] or item["swapped_in"]:
            raise HedonicError("a sensitivity would gate or replace the headline")
        if item["status"] in {"NOT_RUN", "NOT_CONVERGED", "ERROR"} and not item["reason"]:
            raise HedonicError(f"{item['id']} has no reason")
        if item["id"] != "levels" and item["beta_by_cell"] == dict(headline):
            continue
    return table


def fit_headline(
    rows: Sequence[Mapping],
    d7_sha256: str | None = None,
    *,
    d7_accept: bool = True,
) -> dict:
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
        "sensitivities": sensitivity_table(
            kept, beta, d7_sha256=d7_sha256, d7_accept=d7_accept
        ),
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


register_fit_headline(fit_headline)
