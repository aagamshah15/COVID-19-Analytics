"""Every query in sql/analytical_queries.sql must execute against the schema."""

import duckdb
import pandas as pd
import pytest

from covid_pipeline.warehouse import load_duckdb, load_forecasts_duckdb, load_query_pack

QUERIES = load_query_pack()


@pytest.fixture(scope="module")
def con(curated, tmp_path_factory):
    path = tmp_path_factory.mktemp("wh") / "pack.duckdb"
    load_duckdb(*curated, db_path=path)
    fc = pd.DataFrame(
        {
            "iso_code": ["AAA", "AAA"],
            "origin_date": pd.to_datetime(["2023-12-31"] * 2),
            "target_date": pd.to_datetime(["2024-01-07", "2024-01-14"]),
            "horizon_weeks": [1, 2],
            "predicted_deaths": [10.0, 12.0],
            "lower_80": [5.0, 6.0],
            "upper_80": [20.0, 24.0],
            "model": ["test", "test"],
        }
    )
    load_forecasts_duckdb(fc, db_path=path)
    return duckdb.connect(str(path), read_only=True)


def test_pack_has_expected_queries():
    assert len(QUERIES) == 22
    assert all(sql.strip() for sql in QUERIES.values())


@pytest.mark.parametrize("name", sorted(QUERIES))
def test_query_executes(con, name):
    result = con.execute(QUERIES[name]).fetchdf()
    assert len(result) > 0, f"{name} returned no rows"


def test_kpis_are_consistent(con, curated):
    _, weekly = curated
    kpis = con.execute(QUERIES["q01_executive_kpis"]).fetchdf().iloc[0]
    assert kpis["total_deaths"] == pytest.approx(weekly["new_deaths"].sum())
    assert kpis["countries"] == weekly["iso_code"].nunique()
