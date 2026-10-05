"""Train the simulator: fit every model, validate, and export ``simulator.json``.

Order matters: reporting (M5) corrects the calibration targets, the Rt panel (M1) supplies
fatigue and adherence, the calibration (M2) fixes the lockdown and awareness parameters and each
country's multipliers, and M3 learns those multipliers from country features.

``simulator.json`` holds everything the browser and the API need: model constants, presets,
feature scaling, the linear models (so a visitor's edited country can be re-predicted), every
country's starting values with where each came from, and the validation results.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from ..config import (
    SIM_CALIBRATION_PATH,
    SIM_VALIDATION_PATH,
    SIM_WAVES_PATH,
    SIMULATOR_METRICS_PATH,
    SIMULATOR_MODEL_PATH,
    ensure_directories,
)
from . import calibrate as cal
from . import models as m
from .features import AGE_MEAN_COLUMNS, AGE_SHARE_COLUMNS
from .scenario import BANDS, PRESETS, pathogen_dict

log = logging.getLogger(__name__)

MODEL_VERSION = "1.0.0"
SIGNAL_COLUMNS = [
    "median_age",
    "share_65_plus",
    "gdp_per_capita",
    "health_exp_per_capita",
    "out_of_pocket_share",
    "uhc_index",
    "physicians_per_thousand",
    "hospital_beds_per_thousand",
    "urban_share",
    "population_density",
    "diabetes_prevalence",
    "basic_sanitation",
    "extreme_poverty",
    "handwashing_facilities",
    "measles_immunization",
    "life_expectancy",
]
OUTCOME_COLUMNS = [
    "reported_deaths_pm_2021",
    "excess_deaths_pm_2021",
    "peak_weekly_deaths_pm_2021",
    "stringency_mean_2021",
    "first_dose_peak",
]


@dataclass
class TrainConfig:
    """Search grids and resampling sizes; tests shrink them."""

    n_boot: int = 500
    grids: cal.Grids = field(default_factory=cal.Grids)
    hindcast_folds: int = 5


def reference_age_structure(profile: pd.DataFrame) -> tuple[list[float], list[float]]:
    """Population-weighted world age shares and the mean age within each band."""
    data = profile.dropna(subset=[*AGE_SHARE_COLUMNS, "population"])
    weights = data["population"]
    shares = np.array([np.average(data[c], weights=weights) for c in AGE_SHARE_COLUMNS])
    means = np.array([np.average(data[mc], weights=weights * data[sc]) for sc, mc in zip(AGE_SHARE_COLUMNS, AGE_MEAN_COLUMNS, strict=True)])
    return (shares / shares.sum()).round(5).tolist(), means.round(3).tolist()


def train(profile: pd.DataFrame, sim_weekly: pd.DataFrame, config: TrainConfig | None = None, save: bool = True) -> tuple[dict, dict]:
    config = config or TrainConfig()
    started = time.time()
    profile = profile.dropna(subset=["population"]).copy()
    indexed = profile.set_index("iso_code")
    big = indexed[indexed["population"] >= m.MIN_POPULATION]

    standardizer = m.Standardizer.fit(m.raw_features(big))
    Z_big = standardizer.transform(m.raw_features(big))
    Z_all = standardizer.transform(m.raw_features(indexed))

    log.info("M1: lockdown effect on Rt (panel regression)")
    npi = m.fit_npi_panel(sim_weekly, profile)

    log.info("M5: death reporting")
    reporting_model, reporting_metrics, reporting_observed = m.fit_reporting(profile, Z_big)
    reporting_pred = pd.Series(m.expit(m.predict_linear(reporting_model, Z_all)), index=Z_all.index)
    reporting = reporting_pred.copy()
    reporting.update(reporting_observed)

    log.info("M4: vaccine rollout")
    vaccine_models, vaccine_metrics, curves = m.fit_vaccine_rollout(sim_weekly, Z_big)

    log.info("M6: wave classifier")
    wave_model, wave_metrics, waves = m.fit_wave_classifier(sim_weekly, Z_big)

    log.info("M7: archetypes")
    archetype_model, archetype_metrics, _ = m.fit_archetypes(Z_big)
    archetypes = m.assign_archetypes(archetype_model, Z_all)

    log.info("M2: calibrating the engine to 2020")
    countries = cal.calibration_set(profile, sim_weekly, reporting, npi)
    peak_day = npi["seasonality"]["peak_day_of_year_north"]
    fitted, cal_summary, shared = cal.calibrate(countries, config.grids, peak_day=peak_day, n_boot=config.n_boot)

    log.info("M3: country multipliers from features")
    by_iso = fitted.set_index("iso_code")
    tau_model, tau_metrics = m.fit_ridge(Z_big.loc[by_iso.index], np.log(by_iso["transmission"]), "transmission (log multiplier on R0)")
    sev_model, sev_metrics = m.fit_ridge(Z_big.loc[by_iso.index], np.log(by_iso["severity"]), "severity (log multiplier on 60+ IFR)")
    aware_model, aware_metrics = m.fit_ridge(
        Z_big.loc[by_iso.index], np.log(by_iso["awareness"]), "awareness (log multiplier on the threshold)"
    )

    log.info("Validation: temporal holdout and cross-country hindcast")
    holdout, holdout_detail = cal.temporal_holdout(countries, shared, tau_grid=config.grids.tau, seed_grid=config.grids.seed)
    hindcast, hindcast_detail = cal.hindcast(countries, fitted, Z_big, shared, n_splits=config.hindcast_folds)

    shares, means = reference_age_structure(profile)
    constants = replace(
        shared.constants(),
        fatigue_ratio=npi["fatigue_ratio"],
        reference_shares=shares,
        reference_means=means,
    )
    uncertainty = {
        "log_transmission_sd": {"calibrated": round(tau_metrics["residual_sd"] / 2, 4), "predicted": tau_metrics["residual_sd"]},
        "log_severity_sd": {"calibrated": round(sev_metrics["residual_sd"] / 2, 4), "predicted": sev_metrics["residual_sd"]},
        "log_awareness_country_sd": {"calibrated": round(aware_metrics["residual_sd"] / 2, 4), "predicted": aware_metrics["residual_sd"]},
        "logit_reporting_sd": {"observed": 0.2, "predicted": reporting_metrics["residual_sd"]},
        "logit_vaccine_acceptance_sd": {"observed": 0.2, "predicted": vaccine_metrics["ceiling"]["residual_sd"]},
        "log_vaccine_capacity_sd": {"observed": 0.2, "predicted": vaccine_metrics["speed"]["residual_sd"]},
        "npi_coef_sd": round((cal_summary["npi_coef_90ci"][0] - cal_summary["npi_coef_90ci"][1]) / -3.29, 6),
        "log_awareness_sd": _log_sd(cal_summary["awareness_deaths_pm_90ci"]),
        "seasonality_sd": round((cal_summary["seasonality_90ci"][1] - cal_summary["seasonality_90ci"][0]) / 3.29, 4),
        "log_r0_sd": 0.1,
        "log_ifr_sd": 0.2,
        "notes": "Calibrated and observed values use smaller spreads than model predictions; r0 and ifr spreads are assumptions.",
    }

    countries_out = _countries(
        indexed,
        Z_all,
        by_iso,
        tau_model,
        sev_model,
        aware_model,
        reporting_model,
        reporting_observed,
        vaccine_models,
        curves,
        npi,
        archetypes,
    )
    validation = {
        "temporal_holdout": holdout,
        "cross_country_hindcast": hindcast,
        "reading": (
            "Scores are mean absolute errors in weekly deaths per million on data the fit never saw. The simulator "
            "beats its own ablations (no awareness, no features) but not simple statistical baselines at forecasting, "
            "which is why the app presents scenarios, not forecasts."
        ),
    }
    model = {
        "version": MODEL_VERSION,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "bands": BANDS,
        "constants": asdict(constants),
        "uncertainty": uncertainty,
        "presets": [pathogen_dict(p) for p in PRESETS.values()],
        "features": standardizer.to_dict(),
        "models": {
            "transmission": tau_model,
            "severity": sev_model,
            "awareness": aware_model,
            "reporting": reporting_model,
            "vaccine_acceptance": vaccine_models["ceiling"],
            "vaccine_capacity": vaccine_models["speed"],
            "npi": {k: npi[k] for k in ("fatigue_ratio", "adherence_per_sd_65_plus", "z65_mean", "z65_std")},
            "season_tropic_latitude": m.SEASON_TROPIC_LATITUDE,
            "season_full_latitude": m.SEASON_FULL_LATITUDE,
            "waves": wave_model,
            "archetypes": archetype_model,
        },
        "countries": countries_out,
        "validation": validation,
    }
    metrics = {
        "version": MODEL_VERSION,
        "trained_at": model["trained_at"],
        "runtime_seconds": round(time.time() - started, 1),
        "m1_lockdown_panel": npi,
        "m2_calibration": cal_summary,
        "m3_transmission": tau_metrics,
        "m3_severity": sev_metrics,
        "m3_awareness": aware_metrics,
        "m4_vaccine_rollout": vaccine_metrics,
        "m5_reporting": reporting_metrics,
        "m6_wave_classifier": wave_metrics,
        "m7_archetypes": archetype_metrics,
        "overload": (
            "Literature prior (Bravata et al. 2021). OWID hospital data (36 countries, occupancy only) "
            "can't separate overload from case mix."
        ),
        "validation": validation,
    }
    if save:
        ensure_directories()
        SIMULATOR_MODEL_PATH.write_text(json.dumps(_json_safe(model), separators=(",", ":"), allow_nan=False))
        SIMULATOR_METRICS_PATH.write_text(json.dumps(_json_safe(metrics), indent=2, allow_nan=False))
        _save_tables(countries, fitted, holdout_detail, hindcast_detail, waves)
    log.info(
        "Simulator trained in %.0fs: lockdown %.0f%% at stringency 80, awareness %s deaths/M/day, seasonality %.2f, %s countries",
        time.time() - started,
        100 * cal_summary["reduction_at_80"],
        cal_summary["awareness_deaths_pm"],
        cal_summary["seasonality"],
        cal_summary["countries"],
    )
    return model, metrics


def _log_sd(ci: list) -> float | None:
    lo, hi = ci
    if lo is None or hi is None or lo <= 0:
        return None
    return round((math.log(hi) - math.log(lo)) / 3.29, 4)


def _countries(
    indexed, Z, fitted, tau_model, sev_model, aware_model, reporting_model, reporting_observed, vaccine_models, curves, npi, archetypes
) -> list:
    """Every country's starting point: signals, learned settings and where each value came from."""
    tau_pred = m.predict_linear(tau_model, Z)
    sev_pred = m.predict_linear(sev_model, Z)
    aware_pred = m.predict_linear(aware_model, Z)
    rep_pred = m.predict_linear(reporting_model, Z)
    acc_pred = m.predict_linear(vaccine_models["ceiling"], Z)
    cap_pred = m.predict_linear(vaccine_models["speed"], Z)
    adherence = m.adherence(indexed["share_65_plus"], npi).fillna(1.0)
    out = []
    for iso, row in indexed.iterrows():
        if row[AGE_SHARE_COLUMNS].isna().any():
            continue

        def learned(pred: float, observed: float | None, link: str, source: str) -> dict:
            """Value, its source and its residual on the link scale (kept when a visitor edits the place)."""
            to_link = {"log": np.log, "logit": m.logit}[link]
            from_link = {"log": np.exp, "logit": m.expit}[link]
            if observed is not None and np.isfinite(observed):
                return {"value": float(observed), "source": source, "residual": float(to_link(observed) - pred)}
            return {"value": float(from_link(pred)), "source": "predicted", "residual": 0.0}

        cal_row = fitted.loc[iso] if iso in fitted.index else None
        curve = curves.loc[iso] if iso in curves.index else None
        out.append(
            {
                "iso": iso,
                "name": row["location"],
                "continent": row["continent"],
                "population": float(row["population"]),
                "age_shares": [float(row[c]) for c in AGE_SHARE_COLUMNS],
                "age_means": [float(row[c]) for c in AGE_MEAN_COLUMNS],
                "age_source": row.get("age_source"),
                "latitude": _num(row.get("latitude")),
                "signals": {c: _num(row.get(c)) for c in SIGNAL_COLUMNS},
                "z": [round(float(v), 4) for v in Z.loc[iso]],
                "learned": {
                    "transmission": learned(tau_pred[iso], cal_row["transmission"] if cal_row is not None else None, "log", "calibrated"),
                    "severity": learned(sev_pred[iso], cal_row["severity"] if cal_row is not None else None, "log", "calibrated"),
                    "awareness": learned(aware_pred[iso], cal_row["awareness"] if cal_row is not None else None, "log", "calibrated"),
                    "reporting": learned(rep_pred[iso], reporting_observed.get(iso), "logit", "observed"),
                    "vaccine_acceptance": learned(acc_pred[iso], curve["K"] if curve is not None else None, "logit", "observed"),
                    "vaccine_capacity": learned(cap_pred[iso], curve["peak_daily"] if curve is not None else None, "log", "observed"),
                    "adherence": {"value": float(adherence[iso]), "source": "predicted", "residual": 0.0},
                },
                "seed_day_2020": _num(cal_row["seed_day"]) if cal_row is not None else None,
                "fit_rmse_log": _num(cal_row["fit_rmse_log"]) if cal_row is not None else None,
                "archetype": {
                    "cluster": int(archetypes.at[iso, "cluster"]),
                    "pc1": round(float(archetypes.at[iso, "pc1"]), 4),
                    "pc2": round(float(archetypes.at[iso, "pc2"]), 4),
                },
                "outcomes": {c: _num(row.get(c)) for c in OUTCOME_COLUMNS},
            }
        )
    return out


def _num(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return round(v, 6) if math.isfinite(v) else None


def _json_safe(value):
    """NaN and infinity become null (JSON has neither); numpy scalars become Python numbers."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_json_safe(v) for v in value.tolist()]
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def _save_tables(countries, fitted, holdout_detail, hindcast_detail, waves) -> None:
    """Long-format tables for the model-review notebook."""
    weeks = []
    for c, row in zip(countries, fitted.itertuples(), strict=True):
        for k, (obs, fit) in enumerate(zip(c.observed, row.weekly, strict=True)):
            weeks.append({"iso_code": c.iso, "week": k, "observed_deaths": obs, "fitted_deaths": fit, "population": c.place.population})
    calibration = fitted.drop(columns="weekly").merge(pd.DataFrame(weeks), on="iso_code")
    calibration.to_parquet(SIM_CALIBRATION_PATH, index=False)

    rows = []
    for test, detail in (("temporal_holdout", holdout_detail), ("cross_country_hindcast", hindcast_detail)):
        for r in detail.itertuples():
            for k, (obs, pred) in enumerate(zip(r.observed, r.predicted, strict=True)):
                rows.append({"test": test, "iso_code": r.iso_code, "method": r.method, "week": k, "observed_pm": obs, "predicted_pm": pred})
    pd.DataFrame(rows).to_parquet(SIM_VALIDATION_PATH, index=False)
    waves.drop(columns="start_index").to_parquet(SIM_WAVES_PATH, index=False)


def load_model() -> dict:
    return json.loads(SIMULATOR_MODEL_PATH.read_text())
