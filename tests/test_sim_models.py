import json

import numpy as np
import pandas as pd
import pytest

from covid_pipeline.simulator import models as m
from covid_pipeline.simulator.calibrate import Grids
from covid_pipeline.simulator.train import TrainConfig, train


def _panel(true_coef_per_10: float, n_countries: int = 30, seed: int = 0, season: float = 0.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Weekly panel where log Rt responds to stringency two weeks earlier with a known coefficient,
    plus an optional seasonal cycle peaking on day 10 in the north (day 192.5 in the south)."""
    rng = np.random.default_rng(seed)
    weeks = pd.date_range("2020-02-02", "2021-06-27", freq="W-SUN")
    rows, profiles = [], []
    for i in range(n_countries):
        iso = f"C{i:02d}"
        stringency = np.clip(np.cumsum(rng.normal(0, 8, len(weeks))) + 40, 0, 100)
        lagged = pd.Series(stringency).shift(2).fillna(0).to_numpy()
        latitude = 45.0 if i % 2 else -35.0
        day = m.hemisphere_day(weeks.dayofyear.to_numpy(), latitude)
        seasonal = season * m.season_weight(latitude) * np.cos(2 * np.pi * (day - 10) / 365)
        log_rt = 0.3 + rng.normal(0, 0.1) + true_coef_per_10 * lagged / 10 + seasonal + rng.normal(0, 0.05, len(weeks))
        rows.append(
            pd.DataFrame(
                {
                    "iso_code": iso,
                    "week_end": weeks,
                    "stringency_index": stringency,
                    "reproduction_rate": np.exp(log_rt),
                    "new_cases": 1000.0,
                    "first_dose_rate": np.nan,
                }
            )
        )
        profiles.append({"iso_code": iso, "population": 5e6, "share_65_plus": 0.05 + 0.01 * i, "latitude": latitude})
    return pd.concat(rows, ignore_index=True), pd.DataFrame(profiles)


def test_npi_panel_recovers_a_known_effect_without_spurious_fatigue_or_adherence():
    panel, profile = _panel(-0.06)
    fit = m.fit_npi_panel(panel, profile)
    for period in ("2020H1", "2020H2", "2021H1"):
        assert fit["periods"][period]["coef_per_10"] == pytest.approx(-0.06, abs=0.01)
    assert fit["fatigue_ratio"] == pytest.approx(1.0, abs=0.2)
    lo, hi = fit["adherence_interaction"]["ci95"]
    assert lo < 0 < hi  # no interaction was built in


def test_npi_panel_recovers_seasonal_amplitude_and_timing():
    panel, profile = _panel(-0.06, season=0.2)
    seasonality = m.fit_npi_panel(panel, profile)["seasonality"]
    assert seasonality["amplitude_log_rt"] == pytest.approx(0.2, abs=0.03)
    assert seasonality["peak_day_of_year_north"] == pytest.approx(10, abs=8)


def test_vaccine_curves_recover_a_logistic_rollout():
    weeks = pd.date_range("2020-12-06", "2022-12-25", freq="W-SUN")
    t = (weeks - pd.Timestamp("2020-12-01")).days.to_numpy(dtype=float)
    coverage = 0.7 / (1 + np.exp(-0.03 * (t - 200)))
    panel = pd.DataFrame({"iso_code": "AAA", "week_end": weeks, "first_dose_rate": coverage})
    curve = m.fit_vaccine_curves(panel).loc["AAA"]
    assert curve["K"] == pytest.approx(0.7, abs=0.01)
    assert curve["r"] == pytest.approx(0.03, rel=0.05)
    assert curve["peak_daily"] == pytest.approx(0.7 * 0.03 / 4, rel=0.06)


def test_detect_waves_finds_each_peak_and_starts_at_the_trough():
    weeks = pd.date_range("2020-03-01", periods=80, freq="W-SUN")
    t = np.arange(80)
    deaths = 20 * np.exp(-(((t - 15) / 4) ** 2)) + 50 * np.exp(-(((t - 50) / 5) ** 2))
    panel = pd.DataFrame({"iso_code": "AAA", "week_end": weeks, "population": 5e6, "weekly_deaths_per_million": deaths})
    waves = m.detect_waves(panel)
    assert len(waves) == 2
    assert waves["peak"].tolist() == [weeks[15], weeks[50]]
    assert weeks[25] <= waves["start"].iloc[1] <= weeks[40]  # between the waves, not at the series start


def test_standardizer_imputes_with_training_medians():
    raw = pd.DataFrame({"a": [1.0, 2.0, 3.0, np.nan]})
    scaler = m.Standardizer.fit(raw)
    z = scaler.transform(raw)
    assert z["a"].iloc[3] == pytest.approx(z["a"].iloc[1])  # the missing value became the median (2.0)
    assert z["a"].mean() == pytest.approx(0.0)


def test_training_end_to_end_on_synthetic_data(sim_tables):
    profile, sim_weekly = sim_tables
    grids = Grids(
        npi=np.array([-0.012, -0.006]),
        awareness=np.array([4.0, np.inf]),
        seasonality=np.array([0.0, 0.2]),
        tau=np.array([0.6, 1.0, 1.5]),
        seed=np.array([20.0, 50.0]),
    )
    config = TrainConfig(n_boot=20, grids=grids, hindcast_folds=3)
    model, metrics = train(profile, sim_weekly, config, save=False)
    json.dumps(model, allow_nan=True)  # serialisable

    assert len(model["presets"]) == 14
    assert model["constants"]["npi_coef"] <= -0.006
    assert set(model["validation"]["temporal_holdout"]) == {
        "simulator",
        "no_policy_effect",
        "no_awareness",
        "no_seasonality",
        "persistence",
    }
    assert set(model["validation"]["cross_country_hindcast"]) >= {"simulator", "continent_average", "nearest_analog"}
    assert metrics["m6_wave_classifier"]["waves"] > 0

    countries = {c["iso"]: c for c in model["countries"]}
    assert set(countries) == set(profile["iso_code"])
    tau = countries["AAA"]["learned"]["transmission"]
    assert tau["source"] == "calibrated"
    # The browser re-predicts an edited country as model(z) + the country's own residual.
    model_tau = model["models"]["transmission"]
    pred = model_tau["intercept"] + np.dot(list(model_tau["coef"].values()), countries["AAA"]["z"])
    assert np.exp(pred + tau["residual"]) == pytest.approx(tau["value"], rel=1e-3)
    assert countries["NAM"]["age_source"] == "imputed_from_median_age"
    assert countries["AAA"]["learned"]["awareness"]["source"] == "calibrated"
    assert "awareness" in model["models"]
