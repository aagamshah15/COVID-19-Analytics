# Project Brief: COVID-19 Global Healthcare Burden Intelligence (2026)

## 1) Business Problem
Provide decision-oriented visibility into how mortality burden evolved globally and how vaccination rollout related to outcomes.

## 2) Data + Scale
- Sources: Our World in Data (OWID), WHO
- Period: 2020-2023
- Geography: global country-level (filterable)

## 3) Solution
- Automated ETL and feature engineering
- Star-schema analytics warehouse (DuckDB)
- Data quality scorecard
- Executive Tableau story
- ML-based weekly burden forecasting

## 4) Key Outputs
- `data/processed/covid_weekly_features.csv`
- `warehouse/covid_dw.duckdb`
- `reports/dq_report.csv`
- `data/processed/forecast_<country>.csv`

## 5) Impact Narrative
- Identified high-burden country segments
- Quantified vaccination-mortality patterns
- Provided short-term predictive signal for healthcare strain

## 6) Tech Stack
Python, Pandas, NumPy, DuckDB SQL, Tableau Public, GitHub Actions, ML forecasting

## 7) Portfolio Links
- GitHub: <add repo link>
- Tableau Public: <add dashboard link>
- LinkedIn Post: <add post link>
