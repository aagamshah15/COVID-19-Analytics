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
            # Simulator signals: a lockdown in spring 2020, then moderate measures until the index ends.
            "stringency_index": np.select(
                [dates < "2020-03-15", dates < "2020-06-01", dates <= "2022-12-31"], [0.0, 75.0, 40.0], default=np.nan
            ),
            "reproduction_rate": 1 + 0.4 * np.sin(2 * np.pi * t / 120),
            "population_density": 100.0,
            "diabetes_prevalence": 7.0,
            "extreme_poverty": np.nan if continent == "Europe" else 5.0,
            "handwashing_facilities": np.nan,
        }
    )
    df["total_cases"] = df["new_cases"].cumsum()
    df["total_deaths"] = df["new_deaths"].cumsum()
    # Excess deaths are reported weekly (Sundays) and run 50% above reported deaths; Cland has none.
    sundays = df["date"].dt.weekday == 6
    df["excess_mortality_cumulative_absolute"] = np.where(sundays & (iso != "CCC"), df["total_deaths"] * 1.5, np.nan)
    if iso == "CCC":
        # The Kalman-filter Rt dips fractionally below zero when there are almost no cases.
        df.loc[df["date"] < "2020-01-15", "reproduction_rate"] = -0.001
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


def worldbank_payload(isos: list[str]) -> dict:
    """Raw World Bank payload (as stored by fetch_worldbank) for the given ISO3 codes.

    For the first country, women: every 5-year group 0-79 is 5.5% and 80+ is 12%. Men: groups 0-19
    are 7% each, 20-79 are 5.5% each and 80+ is 6%. Half the population is female, so the 0-19 band
    is 25% and 80+ is 9%. Later countries are progressively older, and their other indicators differ
    too, so the models have variation to learn from.
    """
    from covid_pipeline.worldbank import AGE_GROUPS, STATIC_INDICATORS

    def rows(values: dict[str, float], year: str = "2019") -> list[dict]:
        return [{"countryiso3code": iso, "date": year, "value": v} for iso, v in values.items()]

    indicators = {code: rows({iso: 10.0 + 2 * i for i, iso in enumerate(isos)}) for code in STATIC_INDICATORS.values()}
    indicators["SP.POP.TOTL.FE.ZS"] = rows({iso: 50.0 for iso in isos})
    # An older year and a regional aggregate must not leak into the latest value.
    indicators["SH.MED.PHYS.ZS"] += rows({isos[0]: 99.0}, year="2012") + rows({"WLD": 1.0})
    indicators["SH.MED.BEDS.ZS"] = rows({iso: 2.0 for iso in isos})
    for group in AGE_GROUPS:
        female = 12.0 if group == "80UP" else 5.5
        male = 6.0 if group == "80UP" else (7.0 if group in {"0004", "0509", "1014", "1519"} else 5.5)
        # Each later country moves i points of women from ages 0-4 to 80+.
        shift = {"80UP": 1.0, "0004": -1.0}.get(group, 0.0)
        indicators[f"SP.POP.{group}.FE.5Y"] = rows({iso: female + shift * i for i, iso in enumerate(isos)})
        indicators[f"SP.POP.{group}.MA.5Y"] = rows({iso: male for iso in isos})
    return {"fetched_at_utc": "2026-10-01T00:00:00+00:00", "years": "2010:2019", "indicators": indicators}


@pytest.fixture(scope="session")
def worldbank(tmp_path_factory):
    """Parsed World Bank frame for the synthetic countries, except Namibia (no World Bank data)."""
    import json

    from covid_pipeline.worldbank import load_worldbank

    path = tmp_path_factory.mktemp("wb") / "worldbank_wdi.json"
    path.write_text(json.dumps(worldbank_payload([c[0] for c in COUNTRIES if c[0] != "NAM"])))
    return load_worldbank(path)


# Synthetic countries aren't on the world map: give them latitudes in both hemispheres.
LATITUDES = {"AAA": 50.0, "BBB": 30.0, "CCC": -5.0, "DDD": -20.0, "EEE": 45.0}


@pytest.fixture(scope="session")
def sim_tables(curated, worldbank):
    from covid_pipeline.simulator.features import build_sim_tables

    profile, sim_weekly = build_sim_tables(*curated, worldbank, save=False)
    profile["latitude"] = profile["latitude"].fillna(profile["iso_code"].map(LATITUDES))
    return profile, sim_weekly
