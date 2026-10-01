"""Static data files for the web dashboard (``dashboard/public/data``).

The dashboard never recomputes the headline numbers: they come from the SQL pack results
exported here, so the dashboard, the notebooks and the SQL pack always agree. The weekly
series are exported column-wise per country so the browser can re-aggregate any region and
period with the same population-weighted formulas as the SQL.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd
import pycountry

from .config import (
    DQ_REPORT_PATH,
    DUCKDB_PATH,
    FORECAST_METRICS_PATH,
    FORECAST_PATH,
    PROJECT_ROOT,
    RAW_MANIFEST_PATH,
    WEEKLY_PATH,
)
from .warehouse import load_query_pack

log = logging.getLogger(__name__)

WEB_DATA_DIR = PROJECT_ROOT / "dashboard" / "public" / "data"

# Short keys keep weekly.json small; the dashboard maps them back to names in one place.
WEEKLY_SERIES = {
    "d": ("new_deaths", 0),
    "c": ("new_cases", 0),
    "dpm": ("weekly_deaths_per_million", 3),
    "cdpm": ("cumulative_deaths_per_million", 1),
    "cfr": ("case_fatality_rate", 5),
    "v1": ("first_dose_rate", 4),
    "v": ("vaccination_rate", 4),
    "vb": ("booster_rate", 4),
    "h": ("hosp_patients_per_million", 1),
    "icu": ("icu_patients_per_million", 1),
    "occ": ("covid_bed_occupancy_share", 4),
}
# q21 returns thousands of rows the dashboard reads from forecast.json instead.
SKIP_QUERIES = {"q21_forecast_outlook"}


def _clean(value):
    """JSON-safe scalar: NaN/inf -> None, numpy/pandas types -> Python, dates -> ISO strings."""
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "isoformat") and not isinstance(value, (int, float, str)):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _series(values: pd.Series, digits: int) -> list:
    out = []
    for v in values.tolist():
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out.append(None)
        elif digits == 0:
            out.append(int(round(v)))
        else:
            out.append(round(float(v), digits))
    return out


def _iso_numeric(iso3: str) -> str | None:
    country = pycountry.countries.get(alpha_3=iso3)
    return country.numeric if country else None


def build_countries(weekly: pd.DataFrame) -> list[dict]:
    latest = weekly.sort_values("week_end").groupby("iso_code").last().reset_index()
    rows = []
    for r in latest.itertuples():
        rows.append(
            {
                "iso": r.iso_code,
                "numeric": _iso_numeric(r.iso_code),
                "name": r.location,
                "continent": _clean(r.continent),
                "whoRegion": _clean(r.who_region),
                "population": _clean(round(r.population)) if pd.notna(r.population) else None,
                "beds": _clean(round(r.hospital_beds_per_thousand, 2)),
                "medianAge": _clean(round(r.median_age, 1)),
                "gdp": _clean(round(r.gdp_per_capita)) if pd.notna(r.gdp_per_capita) else None,
            }
        )
    return sorted(rows, key=lambda r: r["name"])


def build_weekly(weekly: pd.DataFrame) -> dict:
    weeks = sorted(weekly["week_end"].unique())
    index = pd.DatetimeIndex(weeks)
    series = {}
    for iso, frame in weekly.groupby("iso_code"):
        frame = frame.set_index("week_end").reindex(index)
        series[iso] = {key: _series(frame[col], digits) for key, (col, digits) in WEEKLY_SERIES.items()}
    return {
        "weeks": [pd.Timestamp(w).strftime("%Y-%m-%d") for w in weeks],
        "keys": {k: v[0] for k, v in WEEKLY_SERIES.items()},
        "series": series,
    }


def build_forecast(forecasts: pd.DataFrame) -> dict:
    out = {}
    for iso, frame in forecasts.sort_values("horizon_weeks").groupby("iso_code"):
        out[iso] = {
            "origin": pd.Timestamp(frame["origin_date"].iloc[0]).strftime("%Y-%m-%d"),
            "focus": bool(frame["is_focus_country"].iloc[0]),
            "points": [
                {
                    "week": pd.Timestamp(r.target_date).strftime("%Y-%m-%d"),
                    "h": int(r.horizon_weeks),
                    "p": round(float(r.predicted_deaths), 1),
                    "lo": round(float(r.lower_80), 1),
                    "hi": round(float(r.upper_80), 1),
                }
                for r in frame.itertuples()
            ],
        }
    return out


def build_sql_results(db_path: Path = DUCKDB_PATH) -> dict:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        results = {}
        for name, sql in load_query_pack().items():
            if name in SKIP_QUERIES:
                continue
            df = con.execute(sql).fetchdf()
            results[name] = [{k: _clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]
        return results
    finally:
        con.close()


def export_web_data(out_dir: Path = WEB_DATA_DIR) -> dict[str, int]:
    """Write every file the dashboard needs. Returns {file name: bytes}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    weekly = pd.read_parquet(WEEKLY_PATH)
    forecasts = pd.read_csv(FORECAST_PATH, parse_dates=["origin_date", "target_date"])
    quality = {
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "checks": pd.read_csv(DQ_REPORT_PATH).to_dict(orient="records"),
        "sources": json.loads(RAW_MANIFEST_PATH.read_text()) if RAW_MANIFEST_PATH.exists() else {},
    }
    files = {
        "countries.json": build_countries(weekly),
        "weekly.json": build_weekly(weekly),
        "forecast.json": build_forecast(forecasts),
        "model.json": json.loads(FORECAST_METRICS_PATH.read_text()),
        "quality.json": quality,
        "sql.json": build_sql_results(),
    }
    sizes = {}
    for name, payload in files.items():
        path = out_dir / name
        path.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False))
        sizes[name] = path.stat().st_size
    log.info("Web data written to %s: %s", out_dir, {k: f"{v / 1024:.0f} KB" for k, v in sizes.items()})
    return sizes
