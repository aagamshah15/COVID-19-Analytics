"""Synthetic OWID/WHO-shaped fixtures that reproduce the quirks the pipeline has to handle."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

COUNTRIES = [
    # iso3, name, continent, population, waves amplitude (deaths/week)
    ("AAA", "Aland", "Europe", 10_000_000, 400),
    ("BBB", "Bland", "Asia", 50_000_000, 900),
    ("CCC", "Cland", "Africa", 5_000_000, 60),
    ("DDD", "Dland", "South America", 20_000_000, 500),
    ("EEE", "Eland", "North America", 30_000_000, 700),
    ("NAM", "Namibia", "Africa", 2_500_000, 40),
]


def _country_frame(iso, name, continent, population, amplitude, dates, rng) -> pd.DataFrame:
    t = np.arange(len(dates))
    wave = 1.2 + np.sin(2 * np.pi * t / 240) + 0.6 * np.sin(2 * np.pi * t / 90)
    deaths = rng.poisson(np.clip(wave, 0.05, None) * amplitude / 7)
    cases = rng.poisson(np.clip(wave, 0.05, None) * amplitude * 60 / 7)
    vax_start = int((pd.Timestamp("2021-01-15") - dates[0]).days)
    vax = np.clip((t - vax_start) / 500, 0, 0.8) * population
    df = pd.DataFrame(
        {
            "iso_code": iso,
            "location": name,
            "continent": continent,
            "date": dates,
            "population": float(population),
            "new_cases": cases.astype(float),
            "new_deaths": deaths.astype(float),
            "people_vaccinated": np.where(t >= vax_start, vax * 1.1, np.nan),
            "people_fully_vaccinated": np.where(t >= vax_start, vax, np.nan),
            "total_boosters": np.nan,
            "hosp_patients": deaths * 8.0,
            "icu_patients": deaths * 1.5,
            "hospital_beds_per_thousand": 3.0,
            "median_age": 38.0,
            "gdp_per_capita": 20_000.0,
            "life_expectancy": 78.0,
            "human_development_index": 0.85,
        }
    )
    df["total_cases"] = df["new_cases"].cumsum()
    df["total_deaths"] = df["new_deaths"].cumsum()
    return df


@pytest.fixture(scope="session")
def owid() -> pd.DataFrame:
    """Daily OWID-like frame 2020-2023: six countries plus a 'World' aggregate row set."""
    rng = np.random.default_rng(7)
    dates = pd.date_range("2020-01-01", "2023-12-31", freq="D")
    frames = [_country_frame(*c, dates, rng) for c in COUNTRIES]
    data = pd.concat(frames, ignore_index=True)

    # A negative revision and a reporting stop (exact zeros) in the final 20 weeks for Dland.
    data.loc[(data["iso_code"] == "AAA") & (data["date"] == "2021-03-03"), "new_deaths"] = -25
    stop = (data["iso_code"] == "DDD") & (data["date"] >= "2023-08-14")
    data.loc[stop, ["new_cases", "new_deaths"]] = 0

    world = data.groupby("date", as_index=False)[["new_cases", "new_deaths", "population"]].sum()
    world = world.assign(iso_code="OWID_WRL", location="World", continent=np.nan)
    return pd.concat([data, world], ignore_index=True)


@pytest.fixture(scope="session")
def who_csv(tmp_path_factory) -> str:
    """WHO-style CSV with a BOM, ISO-2 codes, Namibia ('NA') and an international conveyance row."""
    path = tmp_path_factory.mktemp("raw") / "who.csv"
    rows = [
        "﻿Date_reported,Country_code,Country,WHO_region,New_cases,Cumulative_cases,New_deaths,Cumulative_deaths",
        "2020-03-01,NA,Namibia,AFR,5,5,1,1",
        "2020-03-01,XK,Kosovo,EUR,2,2,,0",
        "2020-03-01,XJ,International conveyance (Diamond Princess),OTHER,10,10,0,0",
        "2020-03-01,FR,France,EUR,100,100,2,2",
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return str(path)


@pytest.fixture(scope="session")
def curated(owid):
    from covid_pipeline.transform import build_weekly, clean_daily

    daily = clean_daily(owid.assign(who_region="EUR", who_matched=True))
    return daily, build_weekly(daily)
