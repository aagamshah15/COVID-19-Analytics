from __future__ import annotations

from pathlib import Path
import warnings

import pandas as pd

from .config import CLEAN_DAILY_PATH, CLEAN_WEEKLY_PATH, PROCESSED_DIR, TABLEAU_EXTRACT_PATH


def _latest_country_attributes(daily: pd.DataFrame) -> pd.DataFrame:
    keep_cols = [
        "iso_code",
        "hospital_beds_per_thousand",
        "aged_65_older",
        "gdp_per_capita",
    ]
    existing = [c for c in keep_cols if c in daily.columns]
    dim = (
        daily.sort_values("date")
        .dropna(subset=["iso_code"])
        .drop_duplicates(subset=["iso_code"], keep="last")
    )
    return dim[existing].copy()


def build_tableau_extract(
    weekly_path: Path | str = CLEAN_WEEKLY_PATH,
    daily_path: Path | str = CLEAN_DAILY_PATH,
    output_path: Path | str = TABLEAU_EXTRACT_PATH,
    include_top5_forecasts: bool = True,
) -> Path:
    weekly = pd.read_csv(weekly_path, parse_dates=["date"], low_memory=False)
    daily = pd.read_csv(daily_path, parse_dates=["date"], low_memory=False)

    attrs = _latest_country_attributes(daily)
    actual = weekly.merge(attrs, on="iso_code", how="left")
    actual["record_type"] = "actual"
    actual["pred_new_deaths"] = pd.NA

    top5_countries = (
        actual.groupby("location", as_index=False)["new_deaths"].sum().sort_values("new_deaths", ascending=False).head(5)["location"].tolist()
    )
    actual["top5_focus_country"] = actual["location"].isin(top5_countries)

    forecast_rows = []
    if include_top5_forecasts:
        for country in top5_countries:
            forecast_file = PROCESSED_DIR / f"forecast_{country.lower().replace(' ', '_')}.csv"
            if not forecast_file.exists():
                continue
            fc = pd.read_csv(forecast_file, parse_dates=["date"], low_memory=False)
            if fc.empty:
                continue

            base = actual[actual["location"] == country].sort_values("date").tail(1)
            if base.empty:
                continue

            for _, row in fc.iterrows():
                r = base.iloc[0].copy()
                r["date"] = row["date"]
                r["record_type"] = "forecast"
                r["pred_new_deaths"] = row["pred_new_deaths"]
                r["new_cases"] = pd.NA
                r["new_deaths"] = pd.NA
                r["rolling_7d_cases"] = pd.NA
                r["rolling_7d_deaths"] = pd.NA
                r["cases_per_million"] = pd.NA
                r["deaths_per_million"] = pd.NA
                r["case_fatality_rate"] = pd.NA
                forecast_rows.append(r)

    if forecast_rows:
        forecast_df = pd.DataFrame(forecast_rows)
        for col in actual.columns:
            if col not in forecast_df.columns:
                forecast_df[col] = pd.NA
        forecast_df = forecast_df[actual.columns]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            output = pd.concat([actual, forecast_df], ignore_index=True)
    else:
        output = actual

    output = output.sort_values(["location", "date", "record_type"]).reset_index(drop=True)
    output_path = Path(output_path)
    output.to_csv(output_path, index=False)
    return output_path
