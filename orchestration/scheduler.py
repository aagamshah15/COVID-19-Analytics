"""Lightweight local scheduler for automated ETL runs.

Usage:
    python orchestration/scheduler.py --time 07:30
"""

from __future__ import annotations

import argparse
import subprocess
import time

import schedule


def run_pipeline() -> None:
    subprocess.run([
        "python",
        "-m",
        "src.cli",
        "run",
        "--start-date",
        "2020-01-01",
        "--end-date",
        "2023-12-31",
    ], check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--time", default="07:30", help="24h local time for daily run")
    args = parser.parse_args()

    schedule.every().day.at(args.time).do(run_pipeline)
    print(f"Scheduler active. Running daily at {args.time}.")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
