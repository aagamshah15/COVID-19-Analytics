# Project Brief: COVID-19 Analytics (2026)

## 1) Business Problem
Provide decision-oriented visibility into how the pandemic's mortality and healthcare burden evolved across countries and how vaccination rollout related to outcomes, and let anyone test "what if" scenarios for a future outbreak.

## 2) Data + Scale
- Sources: Our World in Data (OWID), WHO, World Bank World Development Indicators
- Period: 2020-2023, weekly
- Geography: global country-level (filterable by region and country)
- Refresh: rebuilt from the live sources every Monday

## 3) Solution
- Automated pipeline: ingest with a checksummed manifest, transform, data quality gate, star-schema warehouse (DuckDB) and a 22-query SQL pack
- ML-based weekly deaths forecast, backtested against a naive baseline
- Interactive web dashboard (Svelte + TypeScript on GitHub Pages) with light and dark themes: Overview, Where it hit, Country, Vaccines, Hospitals, Outlook, Simulator and Data
- Pandemic scenario simulator that runs in the browser:
  - an age-structured SEIR engine with vaccination, hospital overload, behaviour change and seasonality
  - inputs learned from the data: panel regression of lockdown effects, per-country calibration, ridge regression of country effects, a wave-severity classifier and country analogs
  - Monte Carlo ranges, sensitivity analysis, shareable links and a downloadable PDF report
- CI on every push, and a scheduled rebuild that retrains the models and redeploys the site (GitHub Actions)

## 4) Key Outputs
- Live dashboard: https://aagamshah15.github.io/COVID-19-Analytics/
- `warehouse/covid_dw.duckdb` (star schema) + `sql/analytical_queries.sql` (22 queries)
- `reports/dq_report.csv` (quality gate results)
- `reports/forecast_metrics.json` (backtest vs naive baseline)
- `reports/simulator_metrics.json` (simulator validation: temporal holdout, cross-country hindcast, ablations)
- `data/processed/simulator.json` (the trained simulator model the dashboard loads)
- `data/processed/tableau_exec_extract.csv` (flat weekly extract of actuals + forecasts, for BI tools)
- `notebooks/` (healthcare burden story, forecast review, simulator model review)

## 5) Impact Narrative
- Identified high-burden country segments
- Quantified vaccination-mortality patterns
- Provided short-term predictive signal for healthcare strain
- Turned the historical data into a scenario tool a non-technical reader can run in one click
- Reported model limits honestly: on unseen data the simulator beats its own stripped-down versions but not simple statistical baselines, so results are presented as scenarios, not forecasts

## 6) Tech Stack
Python, pandas, NumPy, SciPy, statsmodels, scikit-learn, DuckDB / PostgreSQL, SQL, pytest, Svelte 5, TypeScript, Vite, D3, Vitest, GitHub Actions, GitHub Pages

## 7) Portfolio Links
- GitHub: https://github.com/aagamshah15/COVID-19-Analytics
- Live dashboard: https://aagamshah15.github.io/COVID-19-Analytics/
- LinkedIn Post: <add post link>
