import duckdb
import pytest

from covid_pipeline.warehouse import build_star_schema, load_duckdb, load_forecasts_duckdb


@pytest.fixture()
def db(curated, tmp_path):
    daily, weekly = curated
    path = tmp_path / "test.duckdb"
    counts = load_duckdb(daily, weekly, db_path=path)
    return path, counts


def test_counts_match_curated(db, curated):
    daily, weekly = curated
    _, counts = db
    assert counts["dim_country"] == daily["iso_code"].nunique()
    assert counts["fact_covid_daily"] == len(daily)
    assert counts["fact_covid_weekly"] == len(weekly)


def test_no_orphaned_facts(db):
    path, _ = db
    con = duckdb.connect(str(path), read_only=True)
    for table in ("fact_covid_daily", "fact_covid_weekly"):
        orphans = con.execute(
            f"""SELECT COUNT(*) FROM {table} f
                LEFT JOIN dim_date d USING (date_key)
                LEFT JOIN dim_country c USING (country_key)
                WHERE d.date_key IS NULL OR c.country_key IS NULL"""
        ).fetchone()[0]
        assert orphans == 0, table


def test_weekly_keys_are_sundays(db):
    path, _ = db
    con = duckdb.connect(str(path), read_only=True)
    assert con.execute("SELECT BOOL_AND(d.is_week_end) FROM fact_covid_weekly JOIN dim_date d USING (date_key)").fetchone()[0]


def test_reload_is_idempotent(db, curated):
    path, counts = db
    assert load_duckdb(*curated, db_path=path) == counts


def test_dim_date_covers_forecast_horizon(curated):
    frames = build_star_schema(*curated)
    assert frames["dim_date"]["date"].max().year == 2024


def test_forecasts_load(db):
    import pandas as pd

    path, _ = db
    fc = pd.DataFrame(
        {
            "iso_code": ["AAA"],
            "origin_date": pd.to_datetime(["2023-12-31"]),
            "target_date": pd.to_datetime(["2024-01-07"]),
            "horizon_weeks": [1],
            "predicted_deaths": [10.0],
            "lower_80": [5.0],
            "upper_80": [20.0],
            "model": ["test"],
        }
    )
    assert load_forecasts_duckdb(fc, db_path=path) == 1
