from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import (
    OWID_URL,
    RAW_MERGED_PATH,
    RAW_OWID_PATH,
    RAW_WHO_PATH,
    WHO_URL,
    ensure_directories,
)


def _read_csv_with_fallback(url: str, fallback_path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(url, low_memory=False)
    except Exception:
        if fallback_path.exists():
            return pd.read_csv(fallback_path, low_memory=False)
        raise


def _load_owid() -> pd.DataFrame:
    df = _read_csv_with_fallback(OWID_URL, RAW_OWID_PATH)
    keep_cols = [
        "iso_code",
        "continent",
        "location",
        "date",
        "new_cases",
        "new_deaths",
        "total_cases",
        "total_deaths",
        "people_vaccinated",
        "people_fully_vaccinated",
        "population",
        "hospital_beds_per_thousand",
        "aged_65_older",
        "gdp_per_capita",
    ]
    existing_cols = [c for c in keep_cols if c in df.columns]
    df = df[existing_cols].copy()
    df["source_priority"] = "owid"
    return df


def _load_who() -> pd.DataFrame:
    try:
        df = _read_csv_with_fallback(WHO_URL, RAW_WHO_PATH)
    except Exception:
        return pd.DataFrame(
            columns=[
                "iso_code",
                "location",
                "date",
                "new_cases",
                "new_deaths",
                "total_cases",
                "total_deaths",
                "source_priority",
            ]
        )
    rename_map = {
        "Date_reported": "date",
        "Country_code": "iso_code",
        "Country": "location",
        "WHO_region": "who_region",
        "New_cases": "new_cases",
        "Cumulative_cases": "total_cases",
        "New_deaths": "new_deaths",
        "Cumulative_deaths": "total_deaths",
    }
    df = df.rename(columns=rename_map)
    required = ["iso_code", "location", "date", "new_cases", "new_deaths", "total_cases", "total_deaths"]
    df = df[[c for c in required if c in df.columns]].copy()
    df["source_priority"] = "who"
    return df


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["iso_code"] = df["iso_code"].astype("string")
    df["location"] = df["location"].astype("string")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def _merge_sources(owid: pd.DataFrame, who: pd.DataFrame) -> pd.DataFrame:
    owid = _normalize(owid)
    who = _normalize(who)

    merged = owid.merge(
        who[["iso_code", "date", "new_cases", "new_deaths", "total_cases", "total_deaths"]],
        on=["iso_code", "date"],
        how="left",
        suffixes=("", "_who"),
    )

    for metric in ["new_cases", "new_deaths", "total_cases", "total_deaths"]:
        merged[metric] = pd.to_numeric(merged[metric], errors="coerce")
        merged[f"{metric}_who"] = pd.to_numeric(merged[f"{metric}_who"], errors="coerce")
        merged[metric] = merged[metric].fillna(merged[f"{metric}_who"])

    drop_cols = [f"{m}_who" for m in ["new_cases", "new_deaths", "total_cases", "total_deaths"]]
    merged = merged.drop(columns=drop_cols)
    return merged


def ingest_raw_data(save: bool = True) -> pd.DataFrame:
    ensure_directories()
    owid = _load_owid()
    who = _load_who()
    merged = _merge_sources(owid, who)

    if save:
        owid.to_csv(RAW_OWID_PATH, index=False)
        who.to_csv(RAW_WHO_PATH, index=False)
        merged.to_csv(RAW_MERGED_PATH, index=False)

    return merged


def ingest_from_local(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["date"], low_memory=False)
