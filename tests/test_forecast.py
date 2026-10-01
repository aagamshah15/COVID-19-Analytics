import numpy as np
import pytest

from covid_pipeline.forecast import build_features, forecast


def test_targets_are_future_values_and_features_are_past(curated):
    _, weekly = curated
    feats = build_features(weekly, horizon_weeks=2)
    aaa = feats[feats["iso_code"] == "AAA"].reset_index(drop=True)
    assert aaa.loc[10, "target_h1"] == aaa.loc[11, "deaths_lag_0"]
    assert aaa.loc[10, "target_h2"] == aaa.loc[12, "deaths_lag_0"]
    assert aaa.loc[10, "deaths_lag_1"] == aaa.loc[9, "deaths_lag_0"]


@pytest.fixture(scope="module")
def result(curated):
    _, weekly = curated
    return forecast(weekly, horizon_weeks=2, top_n=2, save=False)


def test_forecast_output_is_sane(result):
    fc, _ = result
    assert (fc["predicted_deaths"] >= 0).all()
    assert (fc["lower_80"] <= fc["predicted_deaths"] + 1e-9).all()
    assert (fc["upper_80"] >= fc["predicted_deaths"] - 1e-9).all()
    assert set(fc["horizon_weeks"]) == {1, 2}
    assert fc["is_focus_country"].sum() == 2 * 2


def test_countries_that_stopped_reporting_are_not_forecast(result):
    fc, report = result
    assert "DDD" not in set(fc["iso_code"])
    assert report["not_forecast_reporting_stopped"] == ["Dland"]


def test_backtest_reports_skill_against_baseline(result):
    _, report = result
    overall = report["backtest"]["all_countries"]
    assert overall["n"] > 0
    assert np.isfinite(overall["skill_vs_naive"])
    assert set(report["backtest"]["by_horizon_focus"]) == {1, 2}
