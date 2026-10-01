from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from .config import DUCKDB_PATH, SCHEMA_PATH, ensure_directories


def init_db(schema_path: Path = SCHEMA_PATH, db_path: Path = DUCKDB_PATH) -> None:
    ensure_directories()
    con = duckdb.connect(str(db_path))
    con.execute("DROP TABLE IF EXISTS fact_covid_metrics")
    con.execute("DROP TABLE IF EXISTS fact_covid_daily")
    con.execute("DROP TABLE IF EXISTS fact_covid_weekly")
    con.execute("DROP TABLE IF EXISTS dim_country")
    con.execute("DROP TABLE IF EXISTS dim_date")
    with open(schema_path, "r", encoding="utf-8") as f:
        con.execute(f.read())
    con.close()


def _build_dim_date(daily: pd.DataFrame) -> pd.DataFrame:
    dim = (
        daily[["date"]]
        .drop_duplicates()
        .sort_values("date")
        .assign(
            date_key=lambda d: d["date"].dt.strftime("%Y%m%d").astype(int),
            day=lambda d: d["date"].dt.day,
            month=lambda d: d["date"].dt.month,
            month_name=lambda d: d["date"].dt.month_name(),
            quarter=lambda d: d["date"].dt.quarter,
            year=lambda d: d["date"].dt.year,
            iso_week=lambda d: d["date"].dt.isocalendar().week.astype(int),
        )
    )
    return dim[["date_key", "date", "day", "month", "month_name", "quarter", "year", "iso_week"]]


def _build_dim_country(daily: pd.DataFrame) -> pd.DataFrame:
    dim = (
        daily[["iso_code", "location", "continent", "population", "hospital_beds_per_thousand", "aged_65_older", "gdp_per_capita"]]
        .dropna(subset=["iso_code", "location"])
        .drop_duplicates(subset=["iso_code"])
        .rename(columns={"location": "country_name"})
        .sort_values(["continent", "country_name"], na_position="last")
        .reset_index(drop=True)
    )
    dim["country_key"] = dim.index + 1
    return dim[
        [
            "country_key",
            "iso_code",
            "country_name",
            "continent",
            "population",
            "hospital_beds_per_thousand",
            "aged_65_older",
            "gdp_per_capita",
        ]
    ]


def build_star_schema_frames(daily: pd.DataFrame, weekly: pd.DataFrame) -> dict[str, pd.DataFrame]:
    daily = daily.copy()
    weekly = weekly.copy()

    dim_date = _build_dim_date(daily)
    dim_country = _build_dim_country(daily)

    daily = daily.merge(dim_date[["date", "date_key"]], on="date", how="left")
    daily = daily.merge(dim_country[["country_key", "iso_code"]], on="iso_code", how="inner")
    daily["fact_daily_key"] = range(1, len(daily) + 1)

    fact_daily = daily[
        [
            "fact_daily_key",
            "date_key",
            "country_key",
            "new_cases",
            "new_deaths",
            "rolling_7d_cases",
            "rolling_7d_deaths",
            "cases_per_million",
            "deaths_per_million",
            "case_fatality_rate",
            "vaccination_rate",
        ]
    ]

    weekly["date"] = pd.to_datetime(weekly["date"], errors="coerce")
    weekly = weekly.merge(dim_date[["date", "date_key"]], on="date", how="left")
    weekly = weekly.merge(dim_country[["country_key", "iso_code"]], on="iso_code", how="inner")
    weekly["fact_weekly_key"] = range(1, len(weekly) + 1)

    fact_weekly = weekly[
        [
            "fact_weekly_key",
            "date_key",
            "country_key",
            "new_cases",
            "new_deaths",
            "rolling_7d_cases",
            "rolling_7d_deaths",
            "cases_per_million",
            "deaths_per_million",
            "case_fatality_rate",
            "vaccination_rate",
        ]
    ]

    return {
        "dim_date": dim_date,
        "dim_country": dim_country,
        "fact_covid_daily": fact_daily,
        "fact_covid_weekly": fact_weekly,
    }


def load_star_schema(daily: pd.DataFrame, weekly: pd.DataFrame, db_path: Path = DUCKDB_PATH) -> dict[str, int]:
    init_db(db_path=db_path)
    frames = build_star_schema_frames(daily=daily, weekly=weekly)
    dim_date = frames["dim_date"]
    dim_country = frames["dim_country"]
    fact_daily = frames["fact_covid_daily"]
    fact_weekly = frames["fact_covid_weekly"]

    con = duckdb.connect(str(db_path))
    con.register("df_dim_date", dim_date)
    con.register("df_dim_country", dim_country)
    con.register("df_fact_daily", fact_daily)
    con.register("df_fact_weekly", fact_weekly)

    con.execute("DELETE FROM fact_covid_daily")
    con.execute("DELETE FROM fact_covid_weekly")
    con.execute("DELETE FROM dim_country")
    con.execute("DELETE FROM dim_date")

    con.execute("INSERT INTO dim_date SELECT * FROM df_dim_date")
    con.execute("INSERT INTO dim_country SELECT * FROM df_dim_country")
    con.execute("INSERT INTO fact_covid_daily SELECT * FROM df_fact_daily")
    con.execute("INSERT INTO fact_covid_weekly SELECT * FROM df_fact_weekly")

    counts = {
        "dim_date": con.sql("SELECT COUNT(*) FROM dim_date").fetchone()[0],
        "dim_country": con.sql("SELECT COUNT(*) FROM dim_country").fetchone()[0],
        "fact_covid_daily": con.sql("SELECT COUNT(*) FROM fact_covid_daily").fetchone()[0],
        "fact_covid_weekly": con.sql("SELECT COUNT(*) FROM fact_covid_weekly").fetchone()[0],
    }
    con.close()
    return counts
