"""Land-value model fill for thin / suppressed / absent Data Zones.

Spec: docs/surface_rent_spec.md §2–3. Rules: docs/ECONOMIC_RULES.md §6.1, §12.

Fills null residential zones with a per-UR6-class log-linear prediction. Never
copies a neighbour zone's value (rule 1). Thin UR6 classes borrow adjacent-class
training rows with a class fixed effect (tag borrowed_class:<c>).

Research estimates only — not official valuations or tax bills. Does not change
public publication of modelled £; Wealth Engine / internal calibration support.
Does not touch the 5% land-yield placeholder (Valuation owns r−g).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np

from georgist import surface_rent as sr

# RoS 2023 DZ2011 spine accounting (docs/surface_rent_spec.md §12.4):
# Pre-pooling: 6,976 zones = 6,246 priced (≥5 sales) + 724 suppressed + 6 absent;
# null fill = 724 + 6 − 3 zero-dwellings = 727.
# FILL-POOLED / M3: after 3y+5y pooling the remaining model-fill target is 129
# (includes 4 not-in-price-file). Prefer surface.yaml model_fill.null_dz_fill_target_n.
NULL_DZ_FILL_TARGET_N = 129
PRE_POOLING_NULL_DZ_FILL_TARGET_N = 727

DEFAULT_DELTA = 1.0  # log(L + δ); ASSUMPTION, config-overridable
DEFAULT_INTERVAL_Z = 1.2815515655446004  # ~80% normal interval on the log scale


@dataclass(frozen=True)
class ClassFit:
    ur6_class: int
    train_n: int
    borrowed_from: tuple[int, ...]
    beta: tuple[float, ...]  # intercept + one coef per driver
    residual_sd: float
    driver_keys: tuple[str, ...]


@dataclass(frozen=True)
class FittedModel:
    class_fits: Mapping[int, ClassFit]
    delta: float
    driver_keys: tuple[str, ...]
    n_train: int
    quality: str = "research_estimate"


@dataclass(frozen=True)
class ModelPrediction:
    code: str
    land_value: float
    low: float
    high: float
    ur6_class: int
    tags: tuple[str, ...]
    borrowed_from: tuple[int, ...]


def null_dz_fill_target_n(config: Mapping | None = None) -> int:
    """Post-pooling null-zone fill target from surface.yaml (default 129)."""
    cfg = config if config is not None else sr.load_config()
    section = cfg.get("model_fill") or {}
    return int(section.get("null_dz_fill_target_n", NULL_DZ_FILL_TARGET_N))


def _log_target(land_value: float, delta: float) -> float:
    if land_value is None or land_value <= 0:
        raise ValueError("model target needs a positive land value")
    return math.log(float(land_value) + float(delta))


def _exp_target(y: float, delta: float) -> float:
    return max(0.0, math.exp(float(y)) - float(delta))


def _driver_vector(row: Mapping, keys: Sequence[str]) -> list[float]:
    out = []
    for k in keys:
        v = row.get(k)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out.append(0.0)
        else:
            out.append(float(v))
    return out


def _ols(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, float]:
    """Ordinary least squares; returns beta and residual SD (ddof = p)."""
    if len(y) < 2:
        raise ValueError("need at least 2 training rows for OLS")
    beta, _, _, _ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta
    dof = max(1, len(y) - x.shape[1])
    sd = float(np.sqrt(np.sum(resid ** 2) / dof))
    return beta, sd


def _training_classes(ur6: int, adjacency: Mapping[int, Sequence[int]], class_counts: Mapping[int, int],
                      class_min: int) -> tuple[list[int], tuple[int, ...]]:
    """Own class, plus adjacent classes when own class is below class_min_zones."""
    own_n = int(class_counts.get(ur6, 0))
    if own_n >= class_min:
        return [ur6], ()
    borrowed = tuple(int(c) for c in adjacency.get(ur6, ()) if int(class_counts.get(int(c), 0)) > 0)
    return [ur6, *borrowed], borrowed


def fit_land_value_model(
    rows: Sequence[Mapping],
    *,
    config: Mapping,
    driver_keys: Sequence[str] | None = None,
    delta: float | None = None,
    land_key: str = "land_value",
    exclude_zero: Iterable[str] = sr.ZERO_DWELLINGS_FALLBACK,
) -> FittedModel:
    """Fit one log-linear model per UR6 class on observed positive land values.

    Each training row needs: code, ur6_class, land_value (>0), sales_n (>= n_min),
    and optional numeric driver columns. Forbidden drivers are refused.
    """
    price_cfg = config.get("price") or {}
    n_min = int(price_cfg.get("n_min", 5))
    class_min = int(config.get("class_min_zones", 150))
    adjacency = {int(k): [int(x) for x in v] for k, v in (config.get("ur6_adjacency") or {}).items()}
    delta = float(config.get("model_fill", {}).get("delta", DEFAULT_DELTA) if delta is None else delta)
    keys = tuple(driver_keys if driver_keys is not None else (config.get("model_fill") or {}).get("drivers", ()))
    if keys:
        sr.validate_drivers(keys, config)

    donors = sr.sample_for("fill_donor", list(rows), exclude_zero)
    train = []
    for r in donors:
        lv = r.get(land_key)
        if lv is None or float(lv) <= 0:
            continue
        if int(r.get("sales_n") or 0) < n_min:
            continue
        if r.get("ur6_class") is None:
            continue
        train.append(r)
    if not train:
        raise ValueError("no positive observed land values to fit the fill model")

    class_counts: dict[int, int] = {}
    for r in train:
        class_counts[int(r["ur6_class"])] = class_counts.get(int(r["ur6_class"]), 0) + 1

    fits: dict[int, ClassFit] = {}
    for ur6 in sorted(set(class_counts) | set(adjacency)):
        use_classes, borrowed = _training_classes(ur6, adjacency, class_counts, class_min)
        subset = [r for r in train if int(r["ur6_class"]) in use_classes]
        if len(subset) < 2:
            continue
        y = np.array([_log_target(float(r[land_key]), delta) for r in subset], dtype=float)
        # Intercept + drivers + class FE when borrowing
        cols = [_driver_vector(r, keys) for r in subset]
        if borrowed:
            fe = [[1.0 if int(r["ur6_class"]) == ur6 else 0.0] for r in subset]
            x = np.column_stack([np.ones(len(subset)), np.array(cols, dtype=float), np.array(fe, dtype=float)])
        else:
            x = np.column_stack([np.ones(len(subset)), np.array(cols, dtype=float)]) if keys else np.ones((len(subset), 1))
        beta, sd = _ols(y, x)
        # Store only intercept+driver beta for prediction on the target class; FE column is 1 for own class
        if borrowed:
            # beta = [intercept, *driver_coefs, own_class_fe]; fold FE into intercept for this class
            intercept = float(beta[0] + beta[-1])
            driver_beta = tuple(float(b) for b in beta[1:-1])
            beta_out = (intercept, *driver_beta)
        else:
            beta_out = tuple(float(b) for b in beta)
        fits[ur6] = ClassFit(ur6, train_n=len(subset), borrowed_from=borrowed, beta=beta_out,
                             residual_sd=sd, driver_keys=keys)

    if not fits:
        raise ValueError("could not fit any UR6 class model")
    return FittedModel(class_fits=fits, delta=delta, driver_keys=keys, n_train=len(train))


def predict_land_value(
    model: FittedModel,
    rows: Sequence[Mapping],
    *,
    interval_z: float = DEFAULT_INTERVAL_Z,
    exclude_zero: Iterable[str] = sr.ZERO_DWELLINGS_FALLBACK,
) -> list[ModelPrediction]:
    """Predict land value (£/dwelling) and log-scale interval for each row."""
    rows = sr.sample_for("fill_donor", list(rows), exclude_zero)
    out: list[ModelPrediction] = []
    for r in rows:
        ur6 = int(r["ur6_class"])
        fit = model.class_fits.get(ur6)
        if fit is None:
            # fall back to nearest fitted adjacent class's intercept-only if present
            raise ValueError(f"no model fit for UR6 class {ur6}")
        x = [1.0, *_driver_vector(r, fit.driver_keys)]
        if len(x) != len(fit.beta):
            raise ValueError("driver dimension mismatch")
        yhat = sum(b * xi for b, xi in zip(fit.beta, x))
        half = float(interval_z) * float(fit.residual_sd)
        central = _exp_target(yhat, model.delta)
        low = _exp_target(yhat - half, model.delta)
        high = _exp_target(yhat + half, model.delta)
        tags = ["model_filled", "research_estimate", f"model_fill_ur6:{ur6}"]
        if fit.borrowed_from:
            tags.append("borrowed_class:" + ",".join(str(c) for c in fit.borrowed_from))
        out.append(ModelPrediction(
            code=str(r["code"]), land_value=central, low=min(low, central), high=max(high, central),
            ur6_class=ur6, tags=tuple(tags), borrowed_from=fit.borrowed_from,
        ))
    return out


def fit_predict(
    train_rows: list[Mapping],
    test_rows: list[Mapping],
    *,
    config: Mapping,
    land_key: str = "land_value",
    price_key: str | None = "price_gbp",
    drc_key: str | None = "drc_gbp",
) -> list[tuple[float, float, float]]:
    """Pluggable holdout model: predict implied price P̂ = L̂ + DRC when DRC is present, else L̂."""
    model = fit_land_value_model(train_rows, config=config, land_key=land_key)
    preds = predict_land_value(model, test_rows)
    by_code = {p.code: p for p in preds}
    out = []
    for r in test_rows:
        p = by_code[str(r["code"])]
        drc = float(r[drc_key]) if drc_key and r.get(drc_key) is not None else 0.0
        if price_key and r.get(price_key) is not None:
            out.append((p.land_value + drc, p.low + drc, p.high + drc))
        else:
            out.append((p.land_value, p.low, p.high))
    return out


def fill_null_zones(
    *,
    observed_rows: Sequence[Mapping],
    null_rows: Sequence[Mapping],
    config: Mapping,
    land_key: str = "land_value",
    exclude_zero: Iterable[str] = sr.ZERO_DWELLINGS_FALLBACK,
) -> dict:
    """Fit on observed zones; return model fills for null (suppressed / absent) zones.

    Zero-dwelling zones are excluded (not_applicable). Output is for Wealth Engine /
    internal calibration — research estimates, not official figures. Does not change
    public publication of modelled £.
    """
    null_rows = sr.sample_for("fill_donor", list(null_rows), exclude_zero)
    model = fit_land_value_model(observed_rows, config=config, land_key=land_key, exclude_zero=exclude_zero)
    preds = predict_land_value(model, null_rows, exclude_zero=exclude_zero)
    price_cfg = config.get("price") or {}
    fills = {}
    for p in preds:
        src = next((r for r in null_rows if str(r.get("code")) == p.code), {})
        absent = bool(src.get("absent_from_ros_price_file")) or "absent_from_ros_price_file" in str(src.get("flags") or "")
        lv = sr.resolve_land_value(
            dwellings=int(src.get("dwellings") or 1),
            observed=None,
            sales_n=0,
            model_gbp=p.land_value,
            n_min=int(price_cfg.get("n_min", 5)),
            n_full=int(price_cfg.get("n_full", 15)),
            shrinkage_k=float(price_cfg.get("shrinkage_k", 8)),
            absent_from_price_file=absent,
        )
        tags = set(p.tags) | set(lv.tags)
        fills[p.code] = {
            "land_value": p.land_value,
            "land_value_low": p.low,
            "land_value_high": p.high,
            "fill_method": lv.fill_method,
            "ur6_class": p.ur6_class,
            "proxy_tags": sorted(tags),
            "quality": "modelled",
            "value_tier": "proxy",
            "note": "research_estimate_internal_calibration",
        }
    return {
        "model": model,
        "fills": fills,
        "n_filled": len(fills),
        "n_null_input": len(null_rows),
        "null_dz_fill_target_n": null_dz_fill_target_n(config),
        "quality": "research_estimate",
        "publication": "internal_calibration_only",
    }
