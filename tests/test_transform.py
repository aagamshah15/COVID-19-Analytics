import pandas as pd

from src.transform import clean_and_feature_engineer


def test_clean_and_feature_engineer_basic_metrics():
    df = pd.DataFrame(
        {
            "iso_code": ["AAA", "AAA", "AAA", "BBB"],
            "continent": ["Asia", "Asia", "Asia", "Europe"],
            "location": ["Aland", "Aland", "Aland", "Bland"],
            "date": ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-01"],
            "new_cases": [10, 5, 0, 7],
            "new_deaths": [1, 0, 0, 1],
            "total_cases": [10, 15, 15, 7],
            "total_deaths": [1, 1, 1, 1],
            "people_fully_vaccinated": [0, 0, 0, 0],
            "people_vaccinated": [0, 0, 0, 0],
            "population": [1000, 1000, 1000, 2000],
        }
    )

    daily, weekly = clean_and_feature_engineer(df, start_date="2020-01-01", end_date="2020-12-31", save=False)

    assert len(daily) == 4
    assert len(weekly) > 0
    assert "rolling_7d_cases" in daily.columns
    assert "vaccination_rate" in daily.columns

    aland_last = daily[daily["location"] == "Aland"].sort_values("date").iloc[-1]
    assert aland_last["rolling_7d_cases"] == 15
