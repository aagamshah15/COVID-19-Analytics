import numpy as np
import pandas as pd

from covid_pipeline.transform import build_weekly, clean_daily, flag_reporting_gaps


def test_aggregates_are_excluded(curated):
    daily, _ = curated
    assert "OWID_WRL" not in set(daily["iso_code"])
    assert daily["iso_code"].nunique() == 6


def test_negative_revisions_are_clipped_and_flagged(curated):
    daily, _ = curated
    row = daily[(daily["iso_code"] == "AAA") & (daily["date"] == "2021-03-03")].iloc[0]
    assert row["new_deaths"] == 0
    assert row["revision_clipped"]
    assert (daily[["new_cases", "new_deaths"]] >= 0).all().all()


def test_weekly_keeps_only_complete_sunday_weeks(curated):
    daily, weekly = curated
    assert (weekly["week_end"].dt.weekday == 6).all()
    assert weekly["week_end"].min() == pd.Timestamp("2020-01-12")  # Jan 1-5 is a partial week
    aaa = daily[(daily["iso_code"] == "AAA") & daily["date"].between("2020-01-06", "2020-01-12")]
    week = weekly[(weekly["iso_code"] == "AAA") & (weekly["week_end"] == "2020-01-12")].iloc[0]
    assert week["new_cases"] == aaa["new_cases"].sum()


def test_reporting_stop_becomes_null_not_zero(curated):
    _, weekly = curated
    ddd = weekly[weekly["iso_code"] == "DDD"].set_index("week_end")
    assert ddd.loc["2023-12-31", "new_deaths"] != ddd.loc["2023-12-31", "new_deaths"]  # NaN
    assert not ddd.loc["2023-12-31", "deaths_reported"]
    assert ddd.loc["2023-06-04", "deaths_reported"]


def test_short_or_low_volume_zero_runs_are_not_gaps():
    weeks = pd.date_range("2022-01-02", periods=40, freq="W-SUN")
    small = pd.DataFrame({"iso_code": "SML", "week_end": weeks, "new_deaths": [1.0] * 10 + [0.0] * 30})
    short = pd.DataFrame({"iso_code": "SHT", "week_end": weeks, "new_deaths": ([50.0] * 30 + [0.0] * 5 + [50.0] * 5)})
    frame = pd.concat([small, short], ignore_index=True)
    assert not flag_reporting_gaps(frame, "new_deaths").any()


def test_cfr_is_null_where_deaths_exceed_cases():
    df = pd.DataFrame(
        {
            "iso_code": ["FRA"] * 2,
            "location": ["France"] * 2,
            "continent": ["Europe"] * 2,
            "date": pd.to_datetime(["2020-04-01", "2020-04-02"]),
            "population": [1e6] * 2,
            "total_cases": [100.0, 200.0],
            "total_deaths": [150.0, 10.0],
            "new_cases": [0.0, 100.0],
            "new_deaths": [0.0, 0.0],
        }
    )
    daily = clean_daily(df)
    assert np.isnan(daily["case_fatality_rate"].iloc[0])
    assert daily["cfr_inconsistent"].tolist() == [True, False]
    assert daily["case_fatality_rate"].iloc[1] == 0.05


def test_vaccination_is_zero_before_rollout_and_rate_is_a_share(curated):
    daily, weekly = curated
    assert daily.loc[daily["date"] < "2020-12-01", "vaccination_rate"].eq(0).all()
    assert weekly["vaccination_rate"].dropna().between(0, 1).all()


def test_weekly_per_million_is_a_flow(curated):
    _, weekly = curated
    row = weekly.dropna(subset=["new_deaths"]).iloc[100]
    assert row["weekly_deaths_per_million"] == row["new_deaths"] / row["population"] * 1e6


def test_build_weekly_is_deterministic(curated):
    daily, weekly = curated
    pd.testing.assert_frame_equal(build_weekly(daily), weekly)
