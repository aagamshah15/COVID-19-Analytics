"""Command line entry point: ``covid-pipeline <command>`` (or ``python -m covid_pipeline``)."""

from __future__ import annotations

import argparse
import logging
import os
import sys

import pandas as pd

from . import export, forecast, ingest, quality, transform, warehouse
from .config import DEFAULT_END_DATE, DEFAULT_START_DATE, DUCKDB_PATH, FORECAST_PATH

log = logging.getLogger("covid_pipeline")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="covid-pipeline", description="COVID-19 healthcare burden pipeline")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    def window(p: argparse.ArgumentParser) -> None:
        p.add_argument("--start-date", default=DEFAULT_START_DATE)
        p.add_argument("--end-date", default=DEFAULT_END_DATE)

    def offline(p: argparse.ArgumentParser) -> None:
        p.add_argument("--offline", action="store_true", help="use cached raw files instead of downloading")

    def target(p: argparse.ArgumentParser) -> None:
        p.add_argument("--target", choices=["duckdb", "postgres"], default="duckdb")
        p.add_argument("--postgres-url", default=os.environ.get("POSTGRES_URL"), help="defaults to $POSTGRES_URL")

    def fc(p: argparse.ArgumentParser) -> None:
        p.add_argument("--horizon-weeks", type=int, default=8)
        p.add_argument("--top-n", type=int, default=5, help="focus countries reported in the backtest")

    run = sub.add_parser("run", help="ingest -> transform -> dq -> warehouse -> forecast -> export")
    window(run), offline(run), target(run), fc(run)
    run.add_argument("--skip-forecast", action="store_true")

    offline(sub.add_parser("ingest", help="download raw OWID + WHO files"))
    t = sub.add_parser("transform", help="build curated daily/weekly tables from raw files")
    window(t)
    window(sub.add_parser("dq", help="run the data quality gate on curated tables"))
    target(sub.add_parser("warehouse", help="load curated tables into the star schema"))
    fc(sub.add_parser("forecast", help="backtest + forecast weekly deaths"))
    sub.add_parser("export", help="write the dashboard extract (actuals + forecasts)")
    return parser


def _gate(daily: pd.DataFrame, weekly: pd.DataFrame, start_date: str, end_date: str) -> None:
    result = quality.run_dq(daily, weekly, start_date=start_date, end_date=end_date)
    log.info("DQ: %s/%s checks passed, %s warnings", sum(c.passed for c in result.checks), len(result.checks), len(result.warnings))
    if not result.passed:
        raise SystemExit(f"Data quality gate failed: {', '.join(c.name for c in result.errors)}")


def _load_warehouse(args: argparse.Namespace, daily: pd.DataFrame, weekly: pd.DataFrame) -> None:
    if args.target == "postgres":
        if not args.postgres_url:
            raise SystemExit("--postgres-url (or $POSTGRES_URL) is required for --target postgres")
        warehouse.load_postgres(daily, weekly, args.postgres_url)
    else:
        warehouse.load_duckdb(daily, weekly)


def _forecast(args: argparse.Namespace, weekly: pd.DataFrame) -> pd.DataFrame:
    forecasts, _ = forecast.forecast(weekly, horizon_weeks=args.horizon_weeks, top_n=args.top_n)
    if DUCKDB_PATH.exists():
        warehouse.load_forecasts_duckdb(forecasts)
    return forecasts


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command == "run":
        merged = ingest.ingest(offline=args.offline)
        daily, weekly = transform.transform(merged, args.start_date, args.end_date)
        _gate(daily, weekly, args.start_date, args.end_date)
        _load_warehouse(args, daily, weekly)
        forecasts = None if args.skip_forecast else _forecast(args, weekly)
        export.build_extract(weekly, forecasts)
    elif args.command == "ingest":
        ingest.fetch_sources(offline=args.offline)
    elif args.command == "transform":
        merged = ingest.merge_sources(ingest.load_owid(), ingest.load_who())
        transform.transform(merged, args.start_date, args.end_date)
    elif args.command == "dq":
        _gate(*transform.load_curated(), args.start_date, args.end_date)
    elif args.command == "warehouse":
        _load_warehouse(args, *transform.load_curated())
    elif args.command == "forecast":
        _forecast(args, transform.load_curated()[1])
    elif args.command == "export":
        forecasts = pd.read_csv(FORECAST_PATH, parse_dates=["origin_date", "target_date"]) if FORECAST_PATH.exists() else None
        export.build_extract(transform.load_curated()[1], forecasts)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
