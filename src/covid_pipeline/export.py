"""Denormalised dashboard extract: weekly actuals + forecasts in one long table (Tableau / Power BI)."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .config import TABLEAU_EXTRACT_PATH, ensure_directories

log = logging.getLogger(__name__)

COLUMNS = [
    "record_type",
    "week_end",
    "iso_code",
    "location",
    "continent",
    "who_region",
    "population",
    "median_age",
    "hospital_beds_per_thousand",
    "gdp_per_capita",
    "new_cases",
    "new_deaths",
    "cases_reported",
    "deaths_reported",
    "weekly_cases_per_million",
    "weekly_deaths_per_million",
    "cumulative_cases_per_million",
    "cumulative_deaths_per_million",
    "case_fatality_rate",
    "first_dose_rate",
    "vaccination_rate",
    "booster_rate",
    "hosp_patients_per_million",
    "icu_patients_per_million",
    "covid_bed_occupancy_share",
    "predicted_deaths",
    "lower_80",
    "upper_80",
    "horizon_weeks",
    "is_focus_country",
]


def build_extract(
    weekly: pd.DataFrame,
    forecasts: pd.DataFrame | None = None,
    output_path: Path = TABLEAU_EXTRACT_PATH,
    save: bool = True,
) -> pd.DataFrame:
    actual = weekly.assign(record_type="actual")
    frames = [actual]

    if forecasts is not None and not forecasts.empty:
        focus = set(forecasts.loc[forecasts["is_focus_country"], "iso_code"])
        actual["is_focus_country"] = actual["iso_code"].isin(focus)
        # Carry each country's static attributes onto its forecast rows so filters work across both.
        attrs = (
            weekly.sort_values("week_end")
            .groupby("iso_code")
            .last()[["continent", "who_region", "population", "median_age", "hospital_beds_per_thousand", "gdp_per_capita"]]
        )
        fc = (
            forecasts.rename(columns={"target_date": "week_end"})
            .drop(columns=["origin_date", "model"])
            .join(attrs, on="iso_code")
            .assign(record_type="forecast")
        )
        frames.append(fc)
    else:
        actual["is_focus_country"] = False

    extract = pd.concat(frames, ignore_index=True).reindex(columns=COLUMNS)
    extract = extract.sort_values(["location", "week_end", "record_type"]).reset_index(drop=True)
    if save:
        ensure_directories()
        extract.to_csv(output_path, index=False)
        log.info("Dashboard extract written to %s (%s rows)", output_path, f"{len(extract):,}")
    return extract
