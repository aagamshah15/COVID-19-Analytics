"""Paths, source URLs and pipeline defaults.

All paths hang off ``PROJECT_ROOT``, which can be overridden with the
``COVID_PIPELINE_HOME`` environment variable (useful for tests and CI).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("COVID_PIPELINE_HOME", Path(__file__).resolve().parents[2]))

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
WAREHOUSE_DIR = PROJECT_ROOT / "warehouse"
REPORTS_DIR = PROJECT_ROOT / "reports"
SQL_DIR = PROJECT_ROOT / "sql"

# Raw layer: source files exactly as downloaded, plus a manifest describing them.
RAW_OWID_PATH = RAW_DIR / "owid_covid_compact.csv"
RAW_WHO_PATH = RAW_DIR / "who_covid_daily.csv"
RAW_WORLDBANK_PATH = RAW_DIR / "worldbank_wdi.json"
RAW_MANIFEST_PATH = RAW_DIR / "manifest.json"
# Static reference data, committed (regenerate with scripts/country_centroids.mjs).
CENTROIDS_PATH = DATA_DIR / "reference" / "country_centroids.csv"
# Versioned copy of the World Bank indicators, used when the live API is down (see worldbank.py).
WORLDBANK_SNAPSHOT_PATH = DATA_DIR / "reference" / "worldbank_wdi_snapshot.json"

# Curated layer.
DAILY_PATH = PROCESSED_DIR / "covid_daily.parquet"
WEEKLY_PATH = PROCESSED_DIR / "covid_weekly.parquet"
FORECAST_PATH = PROCESSED_DIR / "forecast_weekly_deaths.csv"
TABLEAU_EXTRACT_PATH = PROCESSED_DIR / "tableau_exec_extract.csv"
# Simulator training tables.
COUNTRY_PROFILE_PATH = PROCESSED_DIR / "country_profile.parquet"
SIM_WEEKLY_PATH = PROCESSED_DIR / "sim_weekly.parquet"
SIM_CALIBRATION_PATH = PROCESSED_DIR / "sim_calibration.parquet"
SIM_VALIDATION_PATH = PROCESSED_DIR / "sim_validation.parquet"
SIM_WAVES_PATH = PROCESSED_DIR / "sim_waves.parquet"

# Reports.
DQ_REPORT_PATH = REPORTS_DIR / "dq_report.csv"
FORECAST_METRICS_PATH = REPORTS_DIR / "forecast_metrics.json"
SIMULATOR_METRICS_PATH = REPORTS_DIR / "simulator_metrics.json"
# The trained simulator: everything the browser and the API need, in one JSON file.
SIMULATOR_MODEL_PATH = PROCESSED_DIR / "simulator.json"

# Warehouse.
DUCKDB_PATH = WAREHOUSE_DIR / "covid_dw.duckdb"
SCHEMA_PATH = WAREHOUSE_DIR / "schema.sql"
ANALYTICAL_QUERIES_PATH = SQL_DIR / "analytical_queries.sql"

# Upstream sources. The legacy covid.ourworldindata.org host and the
# covid19.who.int CSV link were retired; these are the maintained locations.
OWID_URL = "https://catalog.ourworldindata.org/garden/covid/latest/compact/compact.csv"
WHO_URL = "https://srhdpeuwpubsa.blob.core.windows.net/whdh/COVID/WHO-COVID-19-global-daily-data.csv"
# World Bank WDI (source 2). One request per indicator; see worldbank.py.
WORLDBANK_URL = "https://api.worldbank.org/v2/country/all/indicator/{indicator}?format=json&source=2&per_page=20000&date={years}"

DEFAULT_START_DATE = "2020-01-01"
DEFAULT_END_DATE = "2023-12-31"


@dataclass(frozen=True)
class DQThresholds:
    """Thresholds used by the data quality gate."""

    min_countries: int = 150
    # The latest date in the curated data must be within this many days of the requested end date.
    max_end_gap_days: int = 14
    min_who_match_rate: float = 0.90
    # people_fully_vaccinated can legitimately exceed population slightly (non-residents, stale census).
    max_vaccination_rate: float = 1.10
    min_vaccination_coverage_2022: float = 0.60
    # Simulator inputs (all warn-level: they never block the warehouse, but sim-train needs them).
    min_profile_countries: int = 150
    min_stringency_countries: int = 150
    min_excess_mortality_countries: int = 100
    max_age_share_error: float = 0.01


def ensure_directories() -> None:
    for path in (RAW_DIR, PROCESSED_DIR, WAREHOUSE_DIR, REPORTS_DIR):
        path.mkdir(parents=True, exist_ok=True)
