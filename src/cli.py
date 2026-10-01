from __future__ import annotations

import argparse

from .config import CLEAN_DAILY_PATH, CLEAN_WEEKLY_PATH, DEFAULT_END_DATE, DEFAULT_START_DATE, RAW_MERGED_PATH, TABLEAU_EXTRACT_PATH
from .dq import run_dq_checks
from .ingest import ingest_from_local, ingest_raw_data
from .tableau_export import build_tableau_extract
from .transform import clean_and_feature_engineer


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="COVID-19 healthcare burden ETL pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run full pipeline")
    run_parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    run_parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    run_parser.add_argument("--dq-threshold", type=float, default=99.5)
    run_parser.add_argument("--warehouse-target", choices=["duckdb", "postgres"], default="duckdb")
    run_parser.add_argument("--postgres-url", default=None)

    ingest_parser = sub.add_parser("ingest", help="Download and merge raw source data")
    ingest_parser.add_argument("--save", action="store_true", default=True)

    transform_parser = sub.add_parser("transform", help="Build clean daily/weekly features")
    transform_parser.add_argument("--input", default=str(RAW_MERGED_PATH))
    transform_parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    transform_parser.add_argument("--end-date", default=DEFAULT_END_DATE)

    dq_parser = sub.add_parser("dq", help="Run data quality checks")
    dq_parser.add_argument("--daily", default=str(CLEAN_DAILY_PATH))
    dq_parser.add_argument("--weekly", default=str(CLEAN_WEEKLY_PATH))
    dq_parser.add_argument("--threshold", type=float, default=99.5)
    dq_parser.add_argument("--fail-on-breach", action="store_true")

    warehouse_parser = sub.add_parser("warehouse", help="Load star schema to DuckDB")
    warehouse_parser.add_argument("--daily", default=str(CLEAN_DAILY_PATH))
    warehouse_parser.add_argument("--weekly", default=str(CLEAN_WEEKLY_PATH))
    warehouse_parser.add_argument("--target", choices=["duckdb", "postgres"], default="duckdb")
    warehouse_parser.add_argument("--postgres-url", default=None)

    forecast_parser = sub.add_parser("forecast", help="Train ML model and forecast weekly deaths")
    forecast_parser.add_argument("--country", default="India")
    forecast_parser.add_argument("--horizon-weeks", type=int, default=12)
    forecast_parser.add_argument("--weekly", default=str(CLEAN_WEEKLY_PATH))
    forecast_parser.add_argument("--top-n", type=int, default=None, help="If set, forecast top-N countries by total deaths")

    tableau_parser = sub.add_parser("tableau-extract", help="Build denormalized Tableau-ready extract")
    tableau_parser.add_argument("--weekly", default=str(CLEAN_WEEKLY_PATH))
    tableau_parser.add_argument("--daily", default=str(CLEAN_DAILY_PATH))
    tableau_parser.add_argument("--output", default=str(TABLEAU_EXTRACT_PATH))
    tableau_parser.add_argument("--include-top5-forecasts", action="store_true")

    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.command == "ingest":
        merged = ingest_raw_data(save=args.save)
        print(f"Ingested rows: {len(merged)}")
        return

    if args.command == "transform":
        raw = ingest_from_local(args.input)
        daily, weekly = clean_and_feature_engineer(raw, start_date=args.start_date, end_date=args.end_date, save=True)
        print(f"Daily rows: {len(daily)} | Weekly rows: {len(weekly)}")
        return

    if args.command == "dq":
        daily = ingest_from_local(args.daily)
        weekly = ingest_from_local(args.weekly)
        report, score = run_dq_checks(daily, weekly, save=True)
        print(report.to_string(index=False))
        print(f"DQ quality score: {score}%")
        if args.fail_on_breach and score < args.threshold:
            raise SystemExit(f"DQ score {score}% below threshold {args.threshold}%")
        return

    if args.command == "warehouse":
        daily = ingest_from_local(args.daily)
        weekly = ingest_from_local(args.weekly)
        if args.target == "duckdb":
            try:
                from .warehouse import load_star_schema
            except ModuleNotFoundError as exc:
                raise SystemExit("Missing dependency for DuckDB load. Install with: python3 -m pip install -r requirements.txt") from exc

            counts = load_star_schema(daily, weekly)
        else:
            if not args.postgres_url:
                raise SystemExit("--postgres-url is required when --target postgres")
            from .warehouse_postgres import load_star_schema_postgres

            counts = load_star_schema_postgres(daily=daily, weekly=weekly, postgres_url=args.postgres_url)
        print(counts)
        return

    if args.command == "forecast":
        from .forecast_ml import train_and_forecast_country, train_and_forecast_top_countries

        if args.top_n:
            metrics = train_and_forecast_top_countries(top_n=args.top_n, horizon_weeks=args.horizon_weeks, input_path=args.weekly)
        else:
            metrics = train_and_forecast_country(country=args.country, horizon_weeks=args.horizon_weeks, input_path=args.weekly)
        print(metrics)
        return

    if args.command == "tableau-extract":
        output_path = build_tableau_extract(
            weekly_path=args.weekly,
            daily_path=args.daily,
            output_path=args.output,
            include_top5_forecasts=args.include_top5_forecasts,
        )
        print(f"Tableau extract created: {output_path}")
        return

    if args.command == "run":
        merged = ingest_raw_data(save=True)
        daily, weekly = clean_and_feature_engineer(
            merged,
            start_date=args.start_date,
            end_date=args.end_date,
            save=True,
        )
        report, score = run_dq_checks(daily, weekly, save=True)
        if score < args.dq_threshold:
            raise SystemExit(f"DQ score {score}% below threshold {args.dq_threshold}%")

        if args.warehouse_target == "duckdb":
            try:
                from .warehouse import load_star_schema
            except ModuleNotFoundError as exc:
                raise SystemExit("Missing dependency for DuckDB load. Install with: python3 -m pip install -r requirements.txt") from exc

            counts = load_star_schema(daily, weekly)
        else:
            if not args.postgres_url:
                raise SystemExit("--postgres-url is required when --warehouse-target postgres")
            from .warehouse_postgres import load_star_schema_postgres

            counts = load_star_schema_postgres(daily=daily, weekly=weekly, postgres_url=args.postgres_url)

        print(f"Merged rows: {len(merged)}")
        print(f"Daily rows: {len(daily)} | Weekly rows: {len(weekly)}")
        print(f"DQ score: {score}%")
        print(report.to_string(index=False))
        print(f"Warehouse counts: {counts}")


if __name__ == "__main__":
    main()
