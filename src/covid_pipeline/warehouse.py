"""Load the curated layer into a star schema (DuckDB by default, PostgreSQL optional)."""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import pandas as pd

from .config import ANALYTICAL_QUERIES_PATH, DUCKDB_PATH, SCHEMA_PATH, ensure_directories

log = logging.getLogger(__name__)

TABLES = ["dim_date", "dim_country", "fact_covid_daily", "fact_covid_weekly", "fact_forecast_weekly"]

DAILY_MEASURES = [
    "new_cases",
    "new_deaths",
    "rolling_7d_cases",
    "rolling_7d_deaths",
    "rolling_7d_deaths_per_million",
    "cumulative_cases_per_million",
    "cumulative_deaths_per_million",
    "case_fatality_rate",
    "first_dose_rate",
    "vaccination_rate",
    "booster_rate",
    "hosp_patients_per_million",
    "icu_patients_per_million",
    "covid_bed_occupancy_share",
]
WEEKLY_MEASURES = [
    "new_cases",
    "new_deaths",
    "weekly_cases_per_million",
    "weekly_deaths_per_million",
    "cumulative_cases_per_million",
    "cumulative_deaths_per_million",
    "case_fatality_rate",
    "first_dose_rate",
    "vaccination_rate",
    "booster_rate",
    "hosp_patients_per_million",
    "icu_patients_per_million",
    "covid_bed_occupancy_share",
]
COUNTRY_ATTRIBUTES = [
    "population",
    "hospital_beds_per_thousand",
    "median_age",
    "gdp_per_capita",
    "life_expectancy",
    "human_development_index",
]


def load_query_pack(path: Path = ANALYTICAL_QUERIES_PATH) -> dict[str, str]:
    """Parse ``sql/analytical_queries.sql`` into {name: sql} using its ``-- name:`` markers."""
    queries: dict[str, str] = {}
    name = None
    for line in Path(path).read_text().splitlines():
        if line.startswith("-- name:"):
            name = line.removeprefix("-- name:").strip()
            queries[name] = ""
        elif name is not None and not line.startswith("-- ====="):
            queries[name] += line + "\n"
    return {k: v.strip().rstrip(";") for k, v in queries.items()}


def date_key(dates: pd.Series) -> pd.Series:
    return dates.dt.strftime("%Y%m%d").astype("int64")


def build_dim_date(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """A contiguous calendar. It extends a year past the data so forecast target weeks resolve."""
    dates = pd.Series(pd.date_range(start, end + pd.DateOffset(years=1), freq="D"))
    iso = dates.dt.isocalendar()
    return pd.DataFrame(
        {
            "date_key": date_key(dates),
            "date": dates.dt.date,
            "year": dates.dt.year,
            "quarter": dates.dt.quarter,
            "month": dates.dt.month,
            "month_name": dates.dt.month_name(),
            "day": dates.dt.day,
            "iso_year": iso["year"].astype("int64"),
            "iso_week": iso["week"].astype("int64"),
            "day_of_week": iso["day"].astype("int64"),
            "is_week_end": dates.dt.weekday == 6,
        }
    )


def build_dim_country(daily: pd.DataFrame) -> pd.DataFrame:
    latest = daily.sort_values("date").groupby("iso_code").last().reset_index()
    dim = latest.rename(columns={"location": "country_name"}).sort_values("iso_code").reset_index(drop=True)
    dim["country_key"] = dim.index + 1
    dim["population"] = dim["population"].round().astype("Int64")
    return dim[["country_key", "iso_code", "country_name", "continent", "who_region", *COUNTRY_ATTRIBUTES]]


def _to_fact(frame: pd.DataFrame, date_col: str, measures: list[str], country_keys: pd.Series) -> pd.DataFrame:
    fact = pd.DataFrame(
        {
            "date_key": date_key(frame[date_col]),
            "country_key": frame["iso_code"].map(country_keys),
        }
    )
    if fact["country_key"].isna().any():
        missing = sorted(frame.loc[fact["country_key"].isna(), "iso_code"].unique())
        raise ValueError(f"Facts reference countries missing from dim_country: {missing}")
    fact["country_key"] = fact["country_key"].astype("int64")
    return pd.concat([fact, frame[measures].reset_index(drop=True)], axis=1)


def build_star_schema(daily: pd.DataFrame, weekly: pd.DataFrame) -> dict[str, pd.DataFrame]:
    dim_date = build_dim_date(daily["date"].min(), max(daily["date"].max(), weekly["week_end"].max()))
    dim_country = build_dim_country(daily)
    country_keys = dim_country.set_index("iso_code")["country_key"]
    return {
        "dim_date": dim_date,
        "dim_country": dim_country,
        "fact_covid_daily": _to_fact(daily.reset_index(drop=True), "date", DAILY_MEASURES, country_keys),
        "fact_covid_weekly": _to_fact(weekly.reset_index(drop=True), "week_end", WEEKLY_MEASURES, country_keys),
    }


def load_duckdb(daily: pd.DataFrame, weekly: pd.DataFrame, db_path: Path = DUCKDB_PATH, schema_path: Path = SCHEMA_PATH) -> dict[str, int]:
    """Rebuild the warehouse in a single transaction: a failed load leaves the previous version intact."""
    ensure_directories()
    frames = build_star_schema(daily, weekly)
    con = duckdb.connect(str(db_path))
    try:
        con.execute("BEGIN TRANSACTION")
        con.execute(Path(schema_path).read_text())
        for table, frame in frames.items():
            con.register("frame", frame)
            con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM frame")
            con.unregister("frame")
        con.execute("COMMIT")
        counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    log.info("DuckDB warehouse loaded: %s", counts)
    return counts


def load_forecasts_duckdb(forecasts: pd.DataFrame, db_path: Path = DUCKDB_PATH) -> int:
    """Replace fact_forecast_weekly with the given forecasts (columns as written by forecast.py)."""
    con = duckdb.connect(str(db_path))
    try:
        con.register("fc", forecasts)
        con.execute("BEGIN TRANSACTION")
        con.execute("DELETE FROM fact_forecast_weekly")
        con.execute(
            """
            INSERT INTO fact_forecast_weekly BY NAME
            SELECT CAST(strftime(fc.target_date, '%Y%m%d') AS INTEGER) AS date_key,
                   c.country_key,
                   CAST(strftime(fc.origin_date, '%Y%m%d') AS INTEGER) AS origin_date_key,
                   fc.horizon_weeks,
                   fc.predicted_deaths,
                   fc.lower_80,
                   fc.upper_80,
                   fc.model
            FROM fc
            JOIN dim_country c USING (iso_code)
            """
        )
        con.execute("COMMIT")
        return con.execute("SELECT COUNT(*) FROM fact_forecast_weekly").fetchone()[0]
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def load_postgres(daily: pd.DataFrame, weekly: pd.DataFrame, postgres_url: str, schema_path: Path = SCHEMA_PATH) -> dict[str, int]:
    try:
        from sqlalchemy import create_engine, text
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        raise SystemExit("PostgreSQL support needs: pip install -e '.[postgres]'") from exc

    frames = build_star_schema(daily, weekly)
    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        conn.execute(text(Path(schema_path).read_text()))
        for table, frame in frames.items():
            frame.to_sql(table, conn, if_exists="append", index=False, method="multi", chunksize=5_000)
        counts = {t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one() for t in TABLES}
    log.info("PostgreSQL warehouse loaded: %s", counts)
    return counts
