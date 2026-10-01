from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
WAREHOUSE_DIR = PROJECT_ROOT / "warehouse"
REPORTS_DIR = PROJECT_ROOT / "reports"

RAW_OWID_PATH = RAW_DIR / "owid-covid-data.csv"
RAW_WHO_PATH = RAW_DIR / "who_covid_global.csv"
RAW_MERGED_PATH = RAW_DIR / "covid_merged_daily.csv"

CLEAN_DAILY_PATH = PROCESSED_DIR / "covid_daily_features.csv"
CLEAN_WEEKLY_PATH = PROCESSED_DIR / "covid_weekly_features.csv"
DQ_REPORT_PATH = REPORTS_DIR / "dq_report.csv"
FORECAST_TOP5_METRICS_PATH = REPORTS_DIR / "forecast_metrics_top5.json"
TABLEAU_EXTRACT_PATH = PROCESSED_DIR / "tableau_exec_extract.csv"

DUCKDB_PATH = WAREHOUSE_DIR / "covid_dw.duckdb"
SCHEMA_PATH = WAREHOUSE_DIR / "schema.sql"
POSTGRES_SCHEMA_PATH = WAREHOUSE_DIR / "schema_postgres.sql"

OWID_URL = "https://covid.ourworldindata.org/data/owid-covid-data.csv"
WHO_URL = "https://covid19.who.int/WHO-COVID-19-global-data.csv"

DEFAULT_START_DATE = "2020-01-01"
DEFAULT_END_DATE = "2023-12-31"


def ensure_directories() -> None:
    for path in [RAW_DIR, PROCESSED_DIR, WAREHOUSE_DIR, REPORTS_DIR]:
        path.mkdir(parents=True, exist_ok=True)
