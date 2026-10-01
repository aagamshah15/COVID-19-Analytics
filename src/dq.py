from __future__ import annotations

from dataclasses import dataclass, asdict

import pandas as pd

from .config import DQ_REPORT_PATH, ensure_directories


@dataclass
class DQCheck:
    check_name: str
    passed: bool
    failed_rows: int
    total_rows: int

    @property
    def pass_rate(self) -> float:
        if self.total_rows == 0:
            return 1.0
        return (self.total_rows - self.failed_rows) / self.total_rows


def _non_null_ratio(series: pd.Series) -> float:
    if len(series) == 0:
        return 1.0
    return series.notna().mean()


def run_dq_checks(daily: pd.DataFrame, weekly: pd.DataFrame, save: bool = True) -> tuple[pd.DataFrame, float]:
    checks: list[DQCheck] = []

    dupes_daily = daily.duplicated(subset=["iso_code", "date"]).sum()
    checks.append(DQCheck("daily_unique_iso_date", dupes_daily == 0, int(dupes_daily), len(daily)))

    dupes_weekly = weekly.duplicated(subset=["iso_code", "location", "date"]).sum()
    checks.append(DQCheck("weekly_unique_iso_location_date", dupes_weekly == 0, int(dupes_weekly), len(weekly)))

    null_location = daily["location"].isna().sum()
    checks.append(DQCheck("daily_location_not_null", null_location == 0, int(null_location), len(daily)))

    null_iso = daily["iso_code"].isna().sum()
    checks.append(DQCheck("daily_iso_not_null", null_iso == 0, int(null_iso), len(daily)))

    invalid_vax = daily["vaccination_rate"].dropna().gt(1).sum()
    checks.append(DQCheck("vaccination_rate_lte_1", invalid_vax == 0, int(invalid_vax), len(daily)))

    negative_deaths = daily["new_deaths"].lt(0).sum()
    checks.append(DQCheck("new_deaths_non_negative", negative_deaths == 0, int(negative_deaths), len(daily)))

    negative_cases = daily["new_cases"].lt(0).sum()
    checks.append(DQCheck("new_cases_non_negative", negative_cases == 0, int(negative_cases), len(daily)))

    key_null_ratio = (_non_null_ratio(daily["iso_code"]) + _non_null_ratio(daily["date"]) + _non_null_ratio(daily["location"])) / 3
    checks.append(DQCheck("daily_key_non_null_ratio_ge_99_5", key_null_ratio >= 0.995, 0 if key_null_ratio >= 0.995 else 1, 1))

    report = pd.DataFrame(
        [
            {
                **asdict(c),
                "pass_rate": round(c.pass_rate, 6),
            }
            for c in checks
        ]
    )

    quality_score = round(report["pass_rate"].mean() * 100, 3)

    if save:
        ensure_directories()
        report.to_csv(DQ_REPORT_PATH, index=False)

    return report, quality_score
