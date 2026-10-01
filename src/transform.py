from __future__ import annotations

import pandas as pd

from .config import CLEAN_DAILY_PATH, CLEAN_WEEKLY_PATH, DEFAULT_END_DATE, DEFAULT_START_DATE, ensure_directories


EXCLUDE_ISO_PREFIXES = ("OWID",)


def clean_and_feature_engineer(
    df: pd.DataFrame,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
    save: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ensure_directories()

    data = df.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["iso_code"] = data["iso_code"].astype("string")

    mask_country = ~data["iso_code"].str.startswith(EXCLUDE_ISO_PREFIXES, na=True)
    mask_date = data["date"].between(pd.Timestamp(start_date), pd.Timestamp(end_date))
    data = data[mask_country & mask_date].copy()

    for col in ["new_cases", "new_deaths"]:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)

    cum_cols = ["total_cases", "total_deaths", "people_vaccinated", "people_fully_vaccinated", "population"]
    for col in cum_cols:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")

    data = data.sort_values(["location", "date"])

    for col in ["people_vaccinated", "people_fully_vaccinated", "population", "total_cases", "total_deaths"]:
        if col not in data.columns:
            data[col] = pd.NA

    fill_forward_cols = [c for c in ["total_cases", "total_deaths", "people_vaccinated", "people_fully_vaccinated", "population"] if c in data.columns]
    if fill_forward_cols:
        data[fill_forward_cols] = data.groupby("location")[fill_forward_cols].ffill()

    data["cases_per_million"] = (data["total_cases"] / data["population"]) * 1_000_000
    data["deaths_per_million"] = (data["total_deaths"] / data["population"]) * 1_000_000
    data["case_fatality_rate"] = data["total_deaths"] / data["total_cases"]
    data["case_fatality_rate"] = data["case_fatality_rate"].replace([float("inf")], pd.NA)
    data["vaccination_rate"] = data["people_fully_vaccinated"] / data["population"]

    data["rolling_7d_cases"] = data.groupby("location")["new_cases"].transform(
        lambda s: s.rolling(window=7, min_periods=1).sum()
    )
    data["rolling_7d_deaths"] = data.groupby("location")["new_deaths"].transform(
        lambda s: s.rolling(window=7, min_periods=1).sum()
    )

    weekly = (
        data.set_index("date")
        .groupby("location")
        .resample("W-SUN")
        .agg(
            {
                "iso_code": "first",
                "continent": "first",
                "population": "first",
                "new_cases": "sum",
                "new_deaths": "sum",
                "rolling_7d_cases": "mean",
                "rolling_7d_deaths": "mean",
                "cases_per_million": "max",
                "deaths_per_million": "max",
                "case_fatality_rate": "max",
                "vaccination_rate": "max",
            }
        )
        .reset_index()
    )

    if save:
        data.to_csv(CLEAN_DAILY_PATH, index=False)
        weekly.to_csv(CLEAN_WEEKLY_PATH, index=False)

    return data, weekly
