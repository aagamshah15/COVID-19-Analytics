"""Weekly COVID-19 deaths forecasting.

Approach
--------
* One **global model pooled across all countries** (a single country has only ~200 weekly points),
  trained on deaths *per million* in log space so large and small countries share one scale.
* **Direct multi-horizon**: a separate model per horizon h predicts week t+h from information known
  at week t. No recursive feedback and no "future" covariates that would not be known at forecast time.
* The model predicts the **change** from the current week (in log space) and is blended 50/50 with
  persistence. Weekly COVID deaths are strongly autocorrelated, so persistence is a hard baseline;
  learning a damped adjustment to it beats the baseline where the level-based model did not.
* Evaluated with an **expanding-window rolling-origin backtest** against a naive baseline
  (next weeks = this week). Skill > 0 means the model beats the baseline.
* 80% prediction intervals come from the empirical backtest residuals per horizon.
* Weeks flagged as reporting gaps are null, so they are never used as targets, and countries that
  are not reporting at the forecast origin are not forecast (a forecast of "zero" would be fiction).
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance

from .config import FORECAST_METRICS_PATH, FORECAST_PATH, ensure_directories

log = logging.getLogger(__name__)

MODEL_NAME = "global_hgb_delta_blend"
# Weight on the learned change; 0 = pure persistence, 1 = full model.
SHRINK = 0.5
FEATURES = [
    "deaths_lag_0",
    "deaths_lag_1",
    "deaths_lag_2",
    "deaths_lag_3",
    "deaths_lag_7",
    "deaths_mean_4",
    "deaths_mean_8",
    "cases_lag_0",
    "cases_lag_1",
    "cases_lag_2",
    "cases_growth_1",
    "vaccination_rate",
    "booster_rate",
    "median_age",
    "hospital_beds_per_thousand",
]


def _model() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_iter=150,
        learning_rate=0.05,
        max_depth=4,
        min_samples_leaf=50,
        l2_regularization=1.0,
        random_state=42,
    )


def build_features(weekly: pd.DataFrame, horizon_weeks: int) -> pd.DataFrame:
    """One row per country-week (the forecast origin) with features and targets ``target_h{h}``."""
    df = weekly.sort_values(["iso_code", "week_end"]).copy()
    df["deaths_pm"] = np.log1p(df["weekly_deaths_per_million"].clip(lower=0))
    df["cases_pm"] = np.log1p(df["weekly_cases_per_million"].clip(lower=0))
    g = df.groupby("iso_code", sort=False)

    for lag in (0, 1, 2, 3, 7):
        df[f"deaths_lag_{lag}"] = g["deaths_pm"].shift(lag)
    for lag in (0, 1, 2):
        df[f"cases_lag_{lag}"] = g["cases_pm"].shift(lag)
    df["deaths_mean_4"] = g["deaths_pm"].transform(lambda s: s.rolling(4).mean())
    df["deaths_mean_8"] = g["deaths_pm"].transform(lambda s: s.rolling(8).mean())
    df["cases_growth_1"] = df["cases_lag_0"] - df["cases_lag_1"]
    df[["vaccination_rate", "booster_rate"]] = df[["vaccination_rate", "booster_rate"]].fillna(0)

    for h in range(1, horizon_weeks + 1):
        df[f"target_h{h}"] = g["deaths_pm"].shift(-h)
    return df


def _fit(train: pd.DataFrame, target: str) -> HistGradientBoostingRegressor:
    train = train.dropna(subset=[target, "deaths_lag_0"])
    return _model().fit(train[FEATURES], train[target] - train["deaths_lag_0"])


def _predict(model: HistGradientBoostingRegressor, frame: pd.DataFrame) -> np.ndarray:
    """Log1p deaths per million: persistence plus a damped learned change."""
    return frame["deaths_lag_0"].to_numpy() + SHRINK * model.predict(frame[FEATURES])


def _expm1_deaths(log_pm: np.ndarray, population: np.ndarray) -> np.ndarray:
    return np.clip(np.expm1(log_pm), 0, None) * population / 1e6


def _score(actual: np.ndarray, predicted: np.ndarray, baseline: np.ndarray) -> dict:
    mae = float(np.mean(np.abs(actual - predicted)))
    mae_naive = float(np.mean(np.abs(actual - baseline)))
    total = float(np.sum(np.abs(actual)))
    return {
        "mae_deaths": round(mae, 2),
        "mae_naive_deaths": round(mae_naive, 2),
        "wape": round(float(np.sum(np.abs(actual - predicted)) / total), 4) if total else None,
        "skill_vs_naive": round(1 - mae / mae_naive, 4) if mae_naive else None,
        "n": int(len(actual)),
    }


def backtest(
    features: pd.DataFrame,
    horizon_weeks: int,
    focus_iso: list[str],
    n_folds: int = 6,
    fold_weeks: int = 13,
) -> tuple[dict, dict[int, tuple[float, float]], pd.Series]:
    """Expanding-window backtest. Returns metrics, per-horizon log residual quantiles, feature importance."""
    origins = np.sort(features["week_end"].unique())
    last_origin = origins[-1]
    cutoffs = [last_origin - pd.Timedelta(weeks=fold_weeks * k) for k in range(n_folds, 0, -1)]

    preds = []
    importance = None
    for i, cutoff in enumerate(cutoffs):
        test_end = cutoff + pd.Timedelta(weeks=fold_weeks)
        for h in range(1, horizon_weeks + 1):
            target = f"target_h{h}"
            # Train only on origins whose target week is observable at the cutoff (no leakage).
            train = features[(features["week_end"] + pd.Timedelta(weeks=h) <= cutoff)]
            test = features[(features["week_end"] > cutoff) & (features["week_end"] <= test_end)].dropna(subset=[target, "deaths_lag_0"])
            if train.empty or test.empty:
                continue
            model = _fit(train, target)
            p = _predict(model, test)
            preds.append(
                pd.DataFrame(
                    {
                        "fold": i,
                        "horizon": h,
                        "iso_code": test["iso_code"].to_numpy(),
                        "log_actual": test[target].to_numpy(),
                        "log_pred": p,
                        "log_naive": test["deaths_lag_0"].to_numpy(),
                        "population": test["population"].to_numpy(),
                    }
                )
            )
            if h == 1 and i == len(cutoffs) - 1:
                pi = permutation_importance(model, test[FEATURES], test[target] - test["deaths_lag_0"], n_repeats=5, random_state=42)
                importance = pd.Series(pi.importances_mean, index=FEATURES).sort_values(ascending=False)

    bt = pd.concat(preds, ignore_index=True)
    for col in ("actual", "pred", "naive"):
        bt[col] = _expm1_deaths(bt[f"log_{col}"].to_numpy(), bt["population"].to_numpy())
    bt["log_resid"] = bt["log_actual"] - bt["log_pred"]

    def summarise(frame: pd.DataFrame) -> dict:
        return _score(frame["actual"].to_numpy(), frame["pred"].to_numpy(), frame["naive"].to_numpy())

    focus = bt[bt["iso_code"].isin(focus_iso)]
    metrics = {
        "folds": len(cutoffs),
        "fold_weeks": fold_weeks,
        "first_cutoff": str(pd.Timestamp(cutoffs[0]).date()),
        "all_countries": summarise(bt),
        "focus_countries": summarise(focus),
        "by_horizon_focus": {int(h): summarise(f) for h, f in focus.groupby("horizon")},
        "by_country": {iso: summarise(f) for iso, f in focus.groupby("iso_code")},
    }
    quantiles = {int(h): (float(f["log_resid"].quantile(0.1)), float(f["log_resid"].quantile(0.9))) for h, f in bt.groupby("horizon")}
    return metrics, quantiles, importance if importance is not None else pd.Series(dtype=float)


def forecast(
    weekly: pd.DataFrame,
    horizon_weeks: int = 12,
    top_n: int = 5,
    min_population: int = 1_000_000,
    save: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Backtest, then fit on all data and forecast every reporting country ``horizon_weeks`` ahead.

    Countries below ``min_population`` are excluded: a single death moves their per-million rate so
    much that they add noise rather than signal to the pooled model.
    """
    weekly = weekly[weekly["population"] >= min_population]
    features = build_features(weekly, horizon_weeks)

    origin_date = features["week_end"].max()
    at_origin = features[features["week_end"] == origin_date]
    origin = at_origin.dropna(subset=["deaths_lag_0"])
    not_reporting = sorted(at_origin.loc[at_origin["deaths_lag_0"].isna(), "location"])
    if not_reporting:
        log.warning(
            "Not forecasting %s countries with no death reports at %s: %s",
            len(not_reporting),
            origin_date.date(),
            ", ".join(not_reporting),
        )

    totals = weekly[weekly["iso_code"].isin(origin["iso_code"])].groupby("iso_code")["new_deaths"].sum()
    focus_iso = totals.sort_values(ascending=False).head(top_n).index.tolist()

    log.info("Backtesting %s-week horizon (focus: %s)", horizon_weeks, ", ".join(focus_iso))
    metrics, quantiles, importance = backtest(features, horizon_weeks, focus_iso)
    rows = []
    for h in range(1, horizon_weeks + 1):
        target = f"target_h{h}"
        log_pred = _predict(_fit(features, target), origin)
        q_lo, q_hi = quantiles[h]
        pop = origin["population"].to_numpy()
        rows.append(
            pd.DataFrame(
                {
                    "iso_code": origin["iso_code"].to_numpy(),
                    "location": origin["location"].to_numpy(),
                    "origin_date": origin_date,
                    "target_date": origin_date + pd.Timedelta(weeks=h),
                    "horizon_weeks": h,
                    "predicted_deaths": _expm1_deaths(log_pred, pop),
                    "lower_80": _expm1_deaths(log_pred + q_lo, pop),
                    "upper_80": _expm1_deaths(log_pred + q_hi, pop),
                    "is_focus_country": origin["iso_code"].isin(focus_iso).to_numpy(),
                    "model": MODEL_NAME,
                }
            )
        )
    forecasts = pd.concat(rows, ignore_index=True).sort_values(["iso_code", "horizon_weeks"]).reset_index(drop=True)

    country_names = weekly.drop_duplicates("iso_code").set_index("iso_code")["location"]
    report = {
        "model": MODEL_NAME,
        "target": "weekly deaths (modelled as log1p deaths per million)",
        "horizon_weeks": horizon_weeks,
        "origin_date": str(origin_date.date()),
        "focus_countries": {iso: country_names[iso] for iso in focus_iso},
        "training_universe": f"{features['iso_code'].nunique()} countries with population >= {min_population:,}",
        "not_forecast_reporting_stopped": not_reporting,
        "method": f"log-space change model blended with persistence (weight {SHRINK})",
        "baseline": "naive persistence: every future week equals the last observed week",
        "backtest": metrics,
        "interval": "80% empirical interval from backtest log residuals per horizon",
        "permutation_importance_h1": {k: round(float(v), 5) for k, v in importance.items()},
    }
    if save:
        ensure_directories()
        forecasts.to_csv(FORECAST_PATH, index=False)
        FORECAST_METRICS_PATH.write_text(json.dumps(report, indent=2))
    focus = metrics["focus_countries"]
    log.info(
        "Backtest skill vs naive on focus countries: %s (MAE %s vs %s)",
        focus["skill_vs_naive"],
        focus["mae_deaths"],
        focus["mae_naive_deaths"],
    )
    return forecasts, report
