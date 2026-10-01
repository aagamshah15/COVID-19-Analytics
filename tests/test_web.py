import json

import pandas as pd

from covid_pipeline.web import WEEKLY_SERIES, build_countries, build_forecast, build_weekly


def test_weekly_export_is_columnar_and_json_safe(curated):
    _, weekly = curated
    out = build_weekly(weekly)
    assert len(out["weeks"]) == weekly["week_end"].nunique()
    series = out["series"]["AAA"]
    assert set(series) == set(WEEKLY_SERIES)
    assert all(len(v) == len(out["weeks"]) for v in series.values())
    json.dumps(out, allow_nan=False)  # NaN must have become null


def test_reporting_gaps_export_as_null(curated):
    _, weekly = curated
    deaths = build_weekly(weekly)["series"]["DDD"]["d"]
    assert deaths[-1] is None
    assert deaths[0] is not None


def test_countries_carry_iso_numeric_for_the_map(curated):
    _, weekly = curated
    namibia = next(c for c in build_countries(weekly) if c["iso"] == "NAM")
    assert namibia["numeric"] == "516"
    assert isinstance(namibia["population"], int)


def test_forecast_export_groups_points_by_country():
    fc = pd.DataFrame(
        {
            "iso_code": ["AAA", "AAA"],
            "origin_date": pd.to_datetime(["2023-12-31"] * 2),
            "target_date": pd.to_datetime(["2024-01-07", "2024-01-14"]),
            "horizon_weeks": [1, 2],
            "predicted_deaths": [10.04, 12.0],
            "lower_80": [5.0, 6.0],
            "upper_80": [20.0, 24.0],
            "is_focus_country": [True, True],
        }
    )
    out = build_forecast(fc)
    assert out["AAA"]["focus"] is True
    assert [p["h"] for p in out["AAA"]["points"]] == [1, 2]
    assert out["AAA"]["points"][0]["p"] == 10.0
