"""Data quality gate for the curated layer.

Each check has a severity. The gate fails if any ``error`` check fails; ``warn`` checks are
reported but never block the run. Averaging pass rates into one score hides the failures that
matter (a stale extract still scores ~100%), so the score is reported for information only.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

import pandas as pd

from .config import DEFAULT_END_DATE, DEFAULT_START_DATE, DQ_REPORT_PATH, DQThresholds, ensure_directories

log = logging.getLogger(__name__)


@dataclass
class Check:
    name: str
    severity: str  # "error" | "warn"
    passed: bool
    observed: str
    expectation: str


@dataclass
class DQResult:
    checks: list[Check]

    @property
    def report(self) -> pd.DataFrame:
        return pd.DataFrame([asdict(c) for c in self.checks])

    @property
    def errors(self) -> list[Check]:
        return [c for c in self.checks if c.severity == "error" and not c.passed]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.severity == "warn" and not c.passed]

    @property
    def passed(self) -> bool:
        return not self.errors

    @property
    def score(self) -> float:
        """Share of checks passing, in percent (informational)."""
        return round(100 * sum(c.passed for c in self.checks) / max(len(self.checks), 1), 1)


def _pct(x: float) -> str:
    return f"{x:.2%}"


def run_checks(
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
    thresholds: DQThresholds | None = None,
) -> DQResult:
    t = thresholds or DQThresholds()
    checks: list[Check] = []

    def add(name: str, severity: str, passed: bool, observed: object, expectation: str) -> None:
        checks.append(Check(name, severity, bool(passed), str(observed), expectation))

    # --- completeness / coverage --------------------------------------------------------
    add("daily_not_empty", "error", len(daily) > 0, f"{len(daily):,} rows", "> 0 rows")

    max_date = daily["date"].max() if len(daily) else pd.NaT
    gap_days = (pd.Timestamp(end_date) - max_date).days if pd.notna(max_date) else None
    add(
        "coverage_reaches_end_date",
        "error",
        gap_days is not None and gap_days <= t.max_end_gap_days,
        f"latest date {max_date.date() if pd.notna(max_date) else 'n/a'}",
        f"within {t.max_end_gap_days} days of {end_date}",
    )
    min_date = daily["date"].min() if len(daily) else pd.NaT
    add(
        "coverage_starts_at_start_date",
        "error",
        pd.notna(min_date) and (min_date - pd.Timestamp(start_date)).days <= t.max_end_gap_days,
        f"earliest date {min_date.date() if pd.notna(min_date) else 'n/a'}",
        f"within {t.max_end_gap_days} days of {start_date}",
    )

    n_countries = daily["iso_code"].nunique()
    add("country_count", "error", n_countries >= t.min_countries, n_countries, f">= {t.min_countries}")

    # --- keys -----------------------------------------------------------------------------
    null_keys = int(daily[["iso_code", "date", "location"]].isna().any(axis=1).sum())
    add("daily_keys_not_null", "error", null_keys == 0, f"{null_keys} rows", "0 rows with null iso_code/date/location")

    dup_daily = int(daily.duplicated(["iso_code", "date"]).sum())
    add("daily_unique_iso_date", "error", dup_daily == 0, f"{dup_daily} duplicates", "0")

    dup_weekly = int(weekly.duplicated(["iso_code", "week_end"]).sum())
    add("weekly_unique_iso_week", "error", dup_weekly == 0, f"{dup_weekly} duplicates", "0")

    # --- validity -------------------------------------------------------------------------
    negative = int((daily[["new_cases", "new_deaths"]] < 0).any(axis=1).sum())
    add("flows_non_negative", "error", negative == 0, f"{negative} rows", "0 negative new_cases/new_deaths")

    cumulative_drop = int((daily.groupby("iso_code")["total_deaths"].diff() < 0).sum())
    add("total_deaths_monotonic", "warn", cumulative_drop == 0, f"{cumulative_drop} decreases", "cumulative deaths never decrease")

    clipped = int(daily.get("revision_clipped", pd.Series(dtype=bool)).sum())
    add("negative_revisions_clipped", "warn", clipped == 0, f"{clipped} rows clipped to 0", "no negative revisions in source")

    over = daily.loc[daily["vaccination_rate"] > t.max_vaccination_rate, "location"].unique()
    add(
        "vaccination_rate_plausible",
        "warn",
        len(over) == 0,
        ", ".join(sorted(over)) or "none",
        f"vaccination_rate <= {t.max_vaccination_rate}",
    )

    cfr_bad = int((daily["case_fatality_rate"] > 1).sum())
    add("case_fatality_rate_lte_1", "error", cfr_bad == 0, f"{cfr_bad} rows", "case_fatality_rate <= 1")

    inconsistent = daily.loc[daily.get("cfr_inconsistent", pd.Series(False, index=daily.index)), "location"]
    add(
        "cumulative_deaths_lte_cases",
        "warn",
        inconsistent.empty,
        f"{len(inconsistent)} rows ({', '.join(sorted(inconsistent.unique()))})" if len(inconsistent) else "0 rows",
        "source never reports more deaths than cases (CFR nulled where it does)",
    )

    # --- source integration ---------------------------------------------------------------
    if "who_matched" in daily.columns:
        match_rate = float(daily["who_matched"].mean())
        add("who_join_match_rate", "warn", match_rate >= t.min_who_match_rate, _pct(match_rate), f">= {_pct(t.min_who_match_rate)}")

    if "deaths_reported" in weekly.columns:
        final_week = weekly[weekly["week_end"] == weekly["week_end"].max()]
        stopped = final_week.loc[~final_week["deaths_reported"], "location"]
        gap_weeks = int((~weekly["deaths_reported"]).sum())
        add(
            "death_reporting_active_at_end",
            "warn",
            stopped.empty,
            f"{len(stopped)} countries stopped reporting ({gap_weeks} gap weeks nulled)",
            "every country still reporting deaths in the final week",
        )

    year_2022 = weekly[weekly["week_end"].dt.year == 2022]
    vax_coverage = float(year_2022["vaccination_rate"].notna().mean()) if len(year_2022) else 0.0
    add(
        "vaccination_coverage_2022",
        "warn",
        vax_coverage >= t.min_vaccination_coverage_2022,
        _pct(vax_coverage),
        f">= {_pct(t.min_vaccination_coverage_2022)} of 2022 country-weeks",
    )

    return DQResult(checks)


def run_dq(daily: pd.DataFrame, weekly: pd.DataFrame, save: bool = True, **kwargs) -> DQResult:
    result = run_checks(daily, weekly, **kwargs)
    for check in result.errors:
        log.error("DQ FAILED %s: observed %s, expected %s", check.name, check.observed, check.expectation)
    for check in result.warnings:
        log.warning("DQ warning %s: observed %s, expected %s", check.name, check.observed, check.expectation)
    if save:
        ensure_directories()
        result.report.to_csv(DQ_REPORT_PATH, index=False)
    return result
