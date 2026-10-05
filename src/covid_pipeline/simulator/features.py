"""Simulator training tables, built from the curated layer plus World Bank indicators.

* ``country_profile``: one row per country.
  - The signals a visitor can set for a simulated country (its pre-pandemic baseline).
  - What the country actually experienced up to the end of 2021, which the models use as targets
    and the app shows for analog countries.
* ``sim_weekly``: a country-week panel with lockdown stringency and Rt alongside deaths,
  vaccination and hospital load. It is the training data for the intervention-effect, calibration
  and wave models.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pycountry

from ..config import CENTROIDS_PATH, COUNTRY_PROFILE_PATH, SIM_WEEKLY_PATH, ensure_directories
from ..transform import week_ending
from ..worldbank import AGE_BANDS

# Population share of each simulator age band, and the mean age within it.
AGE_SHARE_COLUMNS = [f"age_{band}" for band in AGE_BANDS]
AGE_MEAN_COLUMNS = [f"age_mean_{band}" for band in AGE_BANDS]
AGE_COLUMNS = [*AGE_SHARE_COLUMNS, *AGE_MEAN_COLUMNS, "share_65_plus"]

log = logging.getLogger(__name__)

# Static OWID attributes carried into the profile (the latest non-missing value per country).
OWID_STATIC = [
    "median_age",
    "gdp_per_capita",
    "life_expectancy",
    "hospital_beds_per_thousand",
    "population_density",
    "diabetes_prevalence",
    "extreme_poverty",
    "handwashing_facilities",
]
# Time-varying OWID signals, averaged to weeks.
OWID_SIGNALS = ["stringency_index", "reproduction_rate"]

# Outcome window: up to the end of 2021 (before Omicron), when stringency and excess-mortality
# reporting were most complete and vaccination had not yet saturated.
OUTCOME_END = pd.Timestamp("2021-12-31")

WEEKLY_COLUMNS = [
    "iso_code",
    "week_end",
    "location",
    "continent",
    "population",
    "new_deaths",
    "new_cases",
    "weekly_deaths_per_million",
    "weekly_cases_per_million",
    "deaths_reported",
    "first_dose_rate",
    "vaccination_rate",
    "booster_rate",
    "hosp_patients_per_million",
    "icu_patients_per_million",
    "covid_bed_occupancy_share",
]


def _with_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """``frame`` with every column in ``columns`` present (missing ones as NaN)."""
    return frame.reindex(columns=list(dict.fromkeys([*frame.columns, *columns])))


def _per_million(values: pd.Series, population: pd.Series) -> pd.Series:
    return values / population.where(population > 0) * 1e6


def observed_outcomes(daily: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    """What each country experienced up to ``OUTCOME_END``, indexed by ISO code."""
    daily = _with_columns(daily, ["excess_mortality_cumulative_absolute", "stringency_index", "first_dose_rate"])
    window = weekly[weekly["week_end"] <= OUTCOME_END]
    by_country = window.groupby("iso_code")
    population = weekly.groupby("iso_code")["population"].last()

    daily_window = daily[daily["date"] <= OUTCOME_END]
    excess = daily_window.dropna(subset=["excess_mortality_cumulative_absolute"]).sort_values("date").groupby("iso_code")
    in_pandemic = daily_window[daily_window["date"] >= "2020-03-01"]

    out = pd.DataFrame(
        {
            "reported_deaths_pm_2021": _per_million(by_country["new_deaths"].sum(min_count=1), population),
            "excess_deaths_pm_2021": _per_million(excess["excess_mortality_cumulative_absolute"].last(), population),
            "excess_deaths_as_of": excess["date"].last(),
            "peak_weekly_deaths_pm_2021": by_country["weekly_deaths_per_million"].max(),
            "stringency_mean_2021": in_pandemic.groupby("iso_code")["stringency_index"].mean(),
            "first_dose_peak": daily.groupby("iso_code")["first_dose_rate"].max().clip(upper=1.0),
        }
    )
    out.index.name = "iso_code"
    return out


def impute_age_structure(profile: pd.DataFrame, k: int = 5) -> pd.DataFrame:
    """Fill missing World Bank age structures from the ``k`` countries closest in median age.

    The World Bank doesn't cover some territories (Taiwan, French overseas departments, ...), but
    OWID has their median age. ``age_source`` records which rows were imputed.
    """
    out = _with_columns(profile, AGE_COLUMNS)
    has_ages = out[AGE_SHARE_COLUMNS].notna().all(axis=1)
    known = out[has_ages & out["median_age"].notna()]
    missing = ~has_ages & out["median_age"].notna()
    out["age_source"] = np.where(has_ages, "worldbank", None)
    for iso in out.index[missing]:
        nearest = (known["median_age"] - out.at[iso, "median_age"]).abs().nsmallest(k).index
        out.loc[iso, AGE_COLUMNS] = known.loc[nearest, AGE_COLUMNS].mean()
        out.loc[iso, "age_source"] = "imputed_from_median_age"
    shares = out.loc[missing, AGE_SHARE_COLUMNS]
    out.loc[missing, AGE_SHARE_COLUMNS] = shares.div(shares.sum(axis=1), axis=0)
    return out


def country_latitudes(iso_codes: pd.Index) -> pd.Series:
    """Centroid latitude per ISO3 code (seasonality depends on it); missing where the map has no shape."""
    centroids = pd.read_csv(CENTROIDS_PATH, dtype={"iso_numeric": str}).set_index("iso_numeric")["latitude"]

    def numeric(iso3: str) -> str | None:
        country = pycountry.countries.get(alpha_3=iso3)
        return country.numeric if country else None

    return pd.Series([centroids.get(numeric(iso)) for iso in iso_codes], index=iso_codes, dtype=float, name="latitude")


def build_country_profile(daily: pd.DataFrame, weekly: pd.DataFrame, worldbank: pd.DataFrame) -> pd.DataFrame:
    """One row per country: identity, pre-pandemic signals, then observed outcomes."""
    daily = _with_columns(daily, OWID_STATIC)
    latest = weekly.sort_values("week_end").groupby("iso_code")
    identity = latest[["location", "continent", "who_region", "population"]].last()
    # GroupBy.last skips missing values, so this is the latest reported value per attribute.
    static = daily.sort_values("date").groupby("iso_code")[OWID_STATIC].last()

    profile = identity.join(static).join(worldbank, how="left")
    profile["latitude"] = country_latitudes(profile.index)
    # OWID's hospital beds are the primary source; the World Bank fills the countries it lacks.
    if "hospital_beds_wb" in profile.columns:
        owid_beds = profile["hospital_beds_per_thousand"]
        profile["beds_source"] = np.where(owid_beds.notna(), "owid", np.where(profile["hospital_beds_wb"].notna(), "worldbank", None))
        profile["hospital_beds_per_thousand"] = owid_beds.fillna(profile.pop("hospital_beds_wb"))

    profile = impute_age_structure(profile).join(observed_outcomes(daily, weekly))
    return profile.reset_index()


def build_sim_weekly(daily: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    """The curated weekly panel plus weekly-mean stringency and Rt and the latest excess-death count."""
    signals_daily = _with_columns(daily, [*OWID_SIGNALS, "excess_mortality_cumulative_absolute"])
    signals_daily = signals_daily[["iso_code", "date", *OWID_SIGNALS, "excess_mortality_cumulative_absolute"]].copy()
    signals_daily["week_end"] = week_ending(signals_daily["date"])
    signals = (
        signals_daily.groupby(["iso_code", "week_end"])
        .agg(
            stringency_index=("stringency_index", "mean"),
            reproduction_rate=("reproduction_rate", "mean"),
            excess_deaths_cumulative=("excess_mortality_cumulative_absolute", "last"),
        )
        .reset_index()
    )
    # OWID's Kalman-filter Rt dips fractionally below zero in weeks with almost no cases.
    signals["rt_clipped"] = signals["reproduction_rate"] < 0
    signals["reproduction_rate"] = signals["reproduction_rate"].clip(lower=0)
    panel = _with_columns(weekly, WEEKLY_COLUMNS)[WEEKLY_COLUMNS]
    return panel.merge(signals, on=["iso_code", "week_end"], how="left").sort_values(["iso_code", "week_end"]).reset_index(drop=True)


def build_sim_tables(
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    worldbank: pd.DataFrame,
    save: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    profile = build_country_profile(daily, weekly, worldbank)
    sim_weekly = build_sim_weekly(daily, weekly)
    log.info(
        "Simulator tables: %s country profiles (%s with an age structure), %s country-weeks",
        len(profile),
        int(profile.get("age_0_19", pd.Series(dtype=float)).notna().sum()),
        f"{len(sim_weekly):,}",
    )
    if save:
        ensure_directories()
        profile.to_parquet(COUNTRY_PROFILE_PATH, index=False)
        sim_weekly.to_parquet(SIM_WEEKLY_PATH, index=False)
    return profile, sim_weekly


def load_sim_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    return pd.read_parquet(COUNTRY_PROFILE_PATH), pd.read_parquet(SIM_WEEKLY_PATH)
