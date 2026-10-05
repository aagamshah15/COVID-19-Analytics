"""Curated layer: clean country-day records and derive daily + weekly healthcare burden features.

Metric naming convention
------------------------
* ``cumulative_*``  running totals (only ever grow) - use the latest value, never average them over time.
* ``weekly_*``      flows within one week - safe to sum/average across weeks and compare across countries.
* ``*_rate``        shares of population (0-1).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .config import DAILY_PATH, DEFAULT_END_DATE, DEFAULT_START_DATE, WEEKLY_PATH, ensure_directories

log = logging.getLogger(__name__)

FLOW_COLS = ["new_cases", "new_deaths"]
CUMULATIVE_COLS = ["total_cases", "total_deaths", "people_vaccinated", "people_fully_vaccinated", "total_boosters"]
VACCINATION_COLS = ["people_vaccinated", "people_fully_vaccinated", "total_boosters"]
OCCUPANCY_COLS = ["hosp_patients", "icu_patients"]
STATIC_COLS = [
    "population",
    "hospital_beds_per_thousand",
    "median_age",
    "gdp_per_capita",
    "life_expectancy",
    "human_development_index",
]
# No COVID-19 vaccine was administered outside trials before this date, so missing
# vaccination counts before it are true zeros rather than unknowns.
VACCINATION_START = pd.Timestamp("2020-12-01")


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.where(denominator > 0)
    return (numerator / denominator).replace([np.inf, -np.inf], np.nan)


def clean_daily(df: pd.DataFrame, start_date: str = DEFAULT_START_DATE, end_date: str = DEFAULT_END_DATE) -> pd.DataFrame:
    data = df.copy()
    data["date"] = pd.to_datetime(data["date"])

    # Aggregates such as "World", "Europe" or income groups carry no continent.
    is_country = data["continent"].notna() & data["iso_code"].notna()
    in_window = data["date"].between(pd.Timestamp(start_date), pd.Timestamp(end_date))
    data = data[is_country & in_window].sort_values(["iso_code", "date"]).reset_index(drop=True)

    for col in FLOW_COLS + CUMULATIVE_COLS + OCCUPANCY_COLS + STATIC_COLS:
        if col not in data.columns:
            data[col] = np.nan
        data[col] = pd.to_numeric(data[col], errors="coerce")

    # Negative daily counts are back-dated revisions; clip them and keep a flag for the DQ report.
    data["revision_clipped"] = (data[FLOW_COLS] < 0).any(axis=1)
    data[FLOW_COLS] = data[FLOW_COLS].clip(lower=0).fillna(0)

    by_country = data.groupby("iso_code", sort=False)
    data[CUMULATIVE_COLS] = by_country[CUMULATIVE_COLS].ffill()
    data[STATIC_COLS] = by_country[STATIC_COLS].transform(lambda s: s.ffill().bfill())
    pre_rollout = data["date"] < VACCINATION_START
    data.loc[pre_rollout, VACCINATION_COLS] = data.loc[pre_rollout, VACCINATION_COLS].fillna(0)
    for col in ("continent", "location", "who_region"):
        if col in data.columns:
            data[col] = by_country[col].transform(lambda s: s.ffill().bfill())

    population = data["population"]
    by_country = data.groupby("iso_code", sort=False)
    data["rolling_7d_cases"] = by_country["new_cases"].transform(lambda s: s.rolling(7, min_periods=1).sum())
    data["rolling_7d_deaths"] = by_country["new_deaths"].transform(lambda s: s.rolling(7, min_periods=1).sum())
    data["rolling_7d_deaths_per_million"] = _safe_ratio(data["rolling_7d_deaths"], population) * 1e6
    data["cumulative_cases_per_million"] = _safe_ratio(data["total_cases"], population) * 1e6
    data["cumulative_deaths_per_million"] = _safe_ratio(data["total_deaths"], population) * 1e6
    # Some early-2020 series report more cumulative deaths than cases (e.g. France counted care-home
    # deaths before matching cases); CFR is undefined there, so null it and flag the row.
    data["cfr_inconsistent"] = data["total_deaths"] > data["total_cases"]
    data["case_fatality_rate"] = _safe_ratio(data["total_deaths"], data["total_cases"]).mask(data["cfr_inconsistent"])
    data["first_dose_rate"] = _safe_ratio(data["people_vaccinated"], population)
    data["vaccination_rate"] = _safe_ratio(data["people_fully_vaccinated"], population)
    data["booster_rate"] = _safe_ratio(data["total_boosters"], population)
    data["hosp_patients_per_million"] = _safe_ratio(data["hosp_patients"], population) * 1e6
    data["icu_patients_per_million"] = _safe_ratio(data["icu_patients"], population) * 1e6
    # Share of the country's total hospital bed capacity occupied by COVID-19 patients.
    bed_capacity = data["hospital_beds_per_thousand"] * population / 1000
    data["covid_bed_occupancy_share"] = _safe_ratio(data["hosp_patients"], bed_capacity)
    return data


def flag_reporting_gaps(
    weekly: pd.DataFrame,
    metric: str,
    min_run_weeks: int = 8,
    prior_weeks: int = 26,
    min_prior_mean: float = 10.0,
) -> pd.Series:
    """Flag weeks where a country stopped reporting ``metric`` rather than truly reaching zero.

    OWID records non-reporting as 0 (e.g. Brazil reports 0 deaths from mid-2023 onward). A run of at
    least ``min_run_weeks`` exact-zero weeks that follows a period averaging ``min_prior_mean`` or more
    per week is treated as a reporting gap. Small countries with genuinely quiet periods are unaffected.
    """
    gap = pd.Series(False, index=weekly.index)
    for _, s in weekly.sort_values("week_end").groupby("iso_code", sort=False)[metric]:
        values = s.to_numpy()
        is_zero = values == 0
        start = 0
        while start < len(values):
            if not is_zero[start]:
                start += 1
                continue
            end = start
            while end < len(values) and is_zero[end]:
                end += 1
            prior = values[max(0, start - prior_weeks) : start]
            if end - start >= min_run_weeks and len(prior) and np.nanmean(prior) >= min_prior_mean:
                gap.loc[s.index[start:end]] = True
            start = end
    return gap


def week_ending(dates: pd.Series) -> pd.Series:
    """The Sunday that ends each date's ISO week."""
    return dates + pd.to_timedelta((6 - dates.dt.weekday) % 7, unit="D")


def build_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """Aggregate to ISO weeks ending Sunday, keeping only complete 7-day weeks."""
    data = daily.copy()
    data["week_end"] = week_ending(data["date"])

    weekly = (
        data.groupby(["iso_code", "week_end"], sort=True)
        .agg(
            location=("location", "last"),
            continent=("continent", "last"),
            who_region=("who_region", "last"),
            population=("population", "last"),
            median_age=("median_age", "last"),
            hospital_beds_per_thousand=("hospital_beds_per_thousand", "last"),
            gdp_per_capita=("gdp_per_capita", "last"),
            days_observed=("date", "nunique"),
            new_cases=("new_cases", "sum"),
            new_deaths=("new_deaths", "sum"),
            total_cases=("total_cases", "last"),
            total_deaths=("total_deaths", "last"),
            cumulative_cases_per_million=("cumulative_cases_per_million", "last"),
            cumulative_deaths_per_million=("cumulative_deaths_per_million", "last"),
            case_fatality_rate=("case_fatality_rate", "last"),
            first_dose_rate=("first_dose_rate", "last"),
            vaccination_rate=("vaccination_rate", "last"),
            booster_rate=("booster_rate", "last"),
            hosp_patients_per_million=("hosp_patients_per_million", "mean"),
            icu_patients_per_million=("icu_patients_per_million", "mean"),
            covid_bed_occupancy_share=("covid_bed_occupancy_share", "mean"),
        )
        .reset_index()
    )
    weekly = weekly[weekly["days_observed"] == 7].drop(columns="days_observed").reset_index(drop=True)
    for metric in FLOW_COLS:
        gap = flag_reporting_gaps(weekly, metric)
        weekly[f"{metric.removeprefix('new_')}_reported"] = ~gap
        weekly.loc[gap, metric] = np.nan
    weekly["weekly_cases_per_million"] = _safe_ratio(weekly["new_cases"], weekly["population"]) * 1e6
    weekly["weekly_deaths_per_million"] = _safe_ratio(weekly["new_deaths"], weekly["population"]) * 1e6
    return weekly


def transform(
    merged: pd.DataFrame,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
    save: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = clean_daily(merged, start_date=start_date, end_date=end_date)
    weekly = build_weekly(daily)
    log.info("Curated %s daily / %s weekly rows for %s countries", f"{len(daily):,}", f"{len(weekly):,}", daily["iso_code"].nunique())
    if save:
        ensure_directories()
        daily.to_parquet(DAILY_PATH, index=False)
        weekly.to_parquet(WEEKLY_PATH, index=False)
    return daily, weekly


def load_curated() -> tuple[pd.DataFrame, pd.DataFrame]:
    return pd.read_parquet(DAILY_PATH), pd.read_parquet(WEEKLY_PATH)
