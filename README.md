# COVID-19 Global Healthcare Burden Intelligence Pipeline (2026 Edition)

Business-storytelling focused, recruiter-ready data project that rebuilds a prior COVID analytics initiative as a production-style analytics pipeline.

## What This Project Delivers

- Automated ETL pipeline combining **OWID** + **WHO** global COVID datasets
- Cleaned feature layers (daily + weekly) for 2020-2023
- Dimensional warehouse in **DuckDB** with **PostgreSQL-compatible** schema/load path
- Data quality framework with measurable scorecard and report output
- 20+ analytical SQL queries for executive narrative and country comparisons
- Tableau-ready datasets for interactive global filtering
- ML forecasting module (XGBoost fallback included) with explainability outputs

## Resume Alignment

This implementation now supports defensible claims around:

- End-to-end ETL automation with ingestion, validation, transformation, and scheduled execution
- Dimensional modeling + star schema analytics in SQL
- Data quality framework with explicit checks and scoring
- Dashboard storytelling with mortality, vaccination, and country segmentation
- Predictive analytics extension for short-term burden forecasting

## Architecture

1. **Ingestion** (`src/ingest.py`)
- Downloads OWID and WHO source files dynamically.
- Merges by `iso_code + date` and fills core metrics.

2. **Transformation** (`src/transform.py`)
- Filters to country-level records, date bounds (`2020-01-01` to `2023-12-31`).
- Computes healthcare burden features:
  - `rolling_7d_cases`, `rolling_7d_deaths`
  - `cases_per_million`, `deaths_per_million`
  - `case_fatality_rate`, `vaccination_rate`
- Produces daily and weekly curated layers.

3. **Data Quality** (`src/dq.py`)
- Runs checks for duplicates, key completeness, invalid ranges, and null exposure.
- Outputs report to `reports/dq_report.csv` and aggregate quality score.

4. **Warehouse Load** (`src/warehouse.py`)
- Creates star schema and loads:
  - `dim_date`
  - `dim_country`
  - `fact_covid_daily`
  - `fact_covid_weekly`

5. **Predictive Analytics** (`src/forecast_ml.py`)
- Trains country-level weekly deaths model (XGBoost or numpy fallback).
- Supports **top-5 country forecasting** in one command.
- Outputs forecast CSV + explainability/metric JSON.

6. **Tableau Extract** (`src/tableau_export.py`)
- Produces one denormalized dashboard dataset for Tableau Public.
- Supports blending actuals + forecast rows with top-5 country flags.

## Quick Start

```bash
pip install -r requirements.txt
python -m src.cli run --start-date 2020-01-01 --end-date 2023-12-31
python -m src.cli forecast --top-n 5 --horizon-weeks 12
python -m src.cli tableau-extract --include-top5-forecasts
```

## CLI Commands

```bash
python -m src.cli ingest
python -m src.cli transform --input data/raw/covid_merged_daily.csv
python -m src.cli dq --daily data/processed/covid_daily_features.csv --weekly data/processed/covid_weekly_features.csv --threshold 99.5 --fail-on-breach
python -m src.cli warehouse --daily data/processed/covid_daily_features.csv --weekly data/processed/covid_weekly_features.csv --target duckdb
python -m src.cli warehouse --daily data/processed/covid_daily_features.csv --weekly data/processed/covid_weekly_features.csv --target postgres --postgres-url postgresql+psycopg2://user:pass@host:5432/dbname
python -m src.cli run --start-date 2020-01-01 --end-date 2023-12-31 --dq-threshold 99.5
python -m src.cli forecast --country India --horizon-weeks 12
python -m src.cli forecast --top-n 5 --horizon-weeks 12
python -m src.cli tableau-extract --include-top5-forecasts
```

## Output Artifacts

- Raw data:
  - `data/raw/owid-covid-data.csv`
  - `data/raw/who_covid_global.csv`
  - `data/raw/covid_merged_daily.csv`
- Processed data:
  - `data/processed/covid_daily_features.csv`
  - `data/processed/covid_weekly_features.csv`
  - `data/processed/forecast_<country>.csv`
  - `data/processed/tableau_exec_extract.csv`
- Reports:
  - `reports/dq_report.csv`
  - `reports/forecast_metrics_<country>.json`
  - `reports/forecast_metrics_top5.json`
- Warehouse:
  - `warehouse/covid_dw.duckdb`
  - `warehouse/schema_postgres.sql`

## SQL Analytics

- Query pack: `sql/analytical_queries.sql` (22 queries)
- Includes burden trends, vaccination impact slices, peer segmentation, and KPI summaries.

## Scheduling

### Local daily scheduler

```bash
python orchestration/scheduler.py --time 07:30
```

### GitHub Actions

- Daily workflow file: `.github/workflows/pipeline.yml`
- Runs ETL with DQ threshold gating, top-5 forecasting, Tableau extract build, and artifact upload.

## Tableau Public Storyboard Plan

Recommended 5-page executive narrative:

1. Global burden over time (cases/deaths per million)
2. Vaccination rollout vs mortality trend
3. Country benchmarking and peer clusters
4. Regional/country filter deep-dive
5. Forecast outlook (AI angle) for selected countries

Use `data/processed/tableau_exec_extract.csv` for dashboard builds and `sql/analytical_queries.sql` for KPI tiles/text callouts.

## LinkedIn Publish Workflow

1. Publish Tableau workbook to Tableau Public.
2. Add project GitHub link + Tableau Public link in one post.
3. Include 2-3 insights from query outputs and 1 forecast takeaway.
4. Attach 1-page PDF summary (optional but recommended).

## Current Status

- Pipeline, schema, DQ, SQL pack, tests, and forecasting module are implemented.
- Dashboard assets and LinkedIn copy can be finalized next.
