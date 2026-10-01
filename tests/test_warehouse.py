from pathlib import Path

import pandas as pd

from src.warehouse import load_star_schema


def test_load_star_schema_counts(tmp_path: Path):
    daily = pd.DataFrame(
        {
            "iso_code": ["AAA", "AAA"],
            "continent": ["Asia", "Asia"],
            "location": ["Aland", "Aland"],
            "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
            "population": [1000, 1000],
            "hospital_beds_per_thousand": [2.0, 2.0],
            "aged_65_older": [10.0, 10.0],
            "gdp_per_capita": [10000.0, 10000.0],
            "new_cases": [1, 2],
            "new_deaths": [0, 1],
            "rolling_7d_cases": [1, 3],
            "rolling_7d_deaths": [0, 1],
            "cases_per_million": [1000.0, 3000.0],
            "deaths_per_million": [0.0, 1000.0],
            "case_fatality_rate": [0.0, 0.5],
            "vaccination_rate": [0.0, 0.1],
        }
    )

    weekly = pd.DataFrame(
        {
            "iso_code": ["AAA"],
            "location": ["Aland"],
            "continent": ["Asia"],
            "date": pd.to_datetime(["2020-01-05"]),
            "population": [1000],
            "new_cases": [3],
            "new_deaths": [1],
            "rolling_7d_cases": [3],
            "rolling_7d_deaths": [1],
            "cases_per_million": [3000],
            "deaths_per_million": [1000],
            "case_fatality_rate": [0.5],
            "vaccination_rate": [0.1],
        }
    )

    db_path = tmp_path / "test.duckdb"
    counts = load_star_schema(daily, weekly, db_path=db_path)

    assert counts["dim_country"] == 1
    assert counts["fact_covid_daily"] == 2
    assert counts["fact_covid_weekly"] == 1
