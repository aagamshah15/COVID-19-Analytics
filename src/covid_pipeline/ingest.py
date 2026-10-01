"""Raw-layer ingestion: download OWID + WHO files and merge them into one country-day frame.

Raw files are stored exactly as downloaded. A failed download is an error unless the
caller explicitly opts into offline mode, so a stale cache can never masquerade as fresh data.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pycountry

from .config import OWID_URL, PROJECT_ROOT, RAW_MANIFEST_PATH, RAW_OWID_PATH, RAW_WHO_PATH, WHO_URL, ensure_directories

log = logging.getLogger(__name__)

OWID_COLUMNS = {
    "code": "iso_code",
    "country": "location",
    "continent": "continent",
    "date": "date",
    "population": "population",
    "new_cases": "new_cases",
    "new_deaths": "new_deaths",
    "total_cases": "total_cases",
    "total_deaths": "total_deaths",
    "people_vaccinated": "people_vaccinated",
    "people_fully_vaccinated": "people_fully_vaccinated",
    "total_boosters": "total_boosters",
    "hosp_patients": "hosp_patients",
    "icu_patients": "icu_patients",
    "hospital_beds_per_thousand": "hospital_beds_per_thousand",
    "median_age": "median_age",
    "gdp_per_capita": "gdp_per_capita",
    "life_expectancy": "life_expectancy",
    "human_development_index": "human_development_index",
}

WHO_COLUMNS = {
    "Date_reported": "date",
    "Country_code": "iso2_code",
    "Country": "who_country",
    "WHO_region": "who_region",
    "New_cases": "new_cases",
    "New_deaths": "new_deaths",
}

# WHO codes that pycountry cannot resolve. "X*" codes other than Kosovo are
# international conveyances (cruise ships etc.) and are intentionally dropped.
ISO2_OVERRIDES = {"XK": "OWID_KOS"}


# --------------------------------------------------------------------------- download


def _download(url: str, dest: Path, timeout: int = 300) -> None:
    """Stream ``url`` to ``dest`` atomically (no partial files left behind on failure)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "covid19-healthcare-burden-pipeline"})
    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False, suffix=".part") as tmp:
        tmp_path = Path(tmp.name)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                shutil.copyfileobj(response, tmp)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
    tmp_path.replace(dest)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_sources(offline: bool = False) -> dict:
    """Download both sources into the raw layer and write a manifest.

    With ``offline=True`` nothing is downloaded and the existing raw files are used.
    """
    ensure_directories()
    sources = {"owid": (OWID_URL, RAW_OWID_PATH), "who": (WHO_URL, RAW_WHO_PATH)}

    if offline:
        missing = [str(path) for _, path in sources.values() if not path.exists()]
        if missing:
            raise FileNotFoundError(f"Offline mode but raw files are missing: {missing}")
        log.warning("Offline mode: using cached raw files without refreshing them")
        if RAW_MANIFEST_PATH.exists():
            return json.loads(RAW_MANIFEST_PATH.read_text())
        return {}

    manifest = {}
    for name, (url, path) in sources.items():
        log.info("Downloading %s from %s", name, url)
        _download(url, path)
        manifest[name] = {
            "url": url,
            "path": str(path.relative_to(PROJECT_ROOT)),
            "fetched_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
    RAW_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    return manifest


# --------------------------------------------------------------------------- load + merge


def load_owid(path: Path = RAW_OWID_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=lambda c: c in OWID_COLUMNS, low_memory=False)
    df = df.rename(columns=OWID_COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    return df


def iso2_to_iso3(code: str) -> str | None:
    if code in ISO2_OVERRIDES:
        return ISO2_OVERRIDES[code]
    country = pycountry.countries.get(alpha_2=code)
    return country.alpha_3 if country else None


def load_who(path: Path = RAW_WHO_PATH) -> pd.DataFrame:
    # utf-8-sig strips the BOM on the first header; keep_default_na=False stops
    # Namibia's ISO code "NA" from being parsed as a missing value.
    df = pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False, na_values=[""], low_memory=False)
    df = df.rename(columns=WHO_COLUMNS)[list(WHO_COLUMNS.values())]
    df["date"] = pd.to_datetime(df["date"])

    codes = {code: iso2_to_iso3(code) for code in df["iso2_code"].unique()}
    df["iso_code"] = df["iso2_code"].map(codes)
    unmapped = sorted(code for code, iso3 in codes.items() if iso3 is None)
    if unmapped:
        log.info("Dropping WHO rows with no ISO3 mapping (international conveyances): %s", unmapped)
    return df.dropna(subset=["iso_code"]).drop(columns=["iso2_code"])


def merge_sources(owid: pd.DataFrame, who: pd.DataFrame) -> pd.DataFrame:
    """Left-join WHO onto OWID by ISO3 code + date.

    OWID is the primary source; WHO fills gaps in daily cases/deaths and supplies the WHO region.
    """
    who_regions = who.drop_duplicates("iso_code").set_index("iso_code")["who_region"]
    who_metrics = who[["iso_code", "date", "new_cases", "new_deaths"]]

    merged = owid.merge(who_metrics, on=["iso_code", "date"], how="left", suffixes=("", "_who"), indicator="_who_join")
    merged["who_matched"] = merged.pop("_who_join").eq("both")

    for metric in ("new_cases", "new_deaths"):
        who_col = f"{metric}_who"
        merged[f"{metric}_filled_from_who"] = merged[metric].isna() & merged[who_col].notna()
        merged[metric] = merged[metric].fillna(merged[who_col])
        merged = merged.drop(columns=who_col)

    merged["who_region"] = merged["iso_code"].map(who_regions)
    return merged


def ingest(offline: bool = False) -> pd.DataFrame:
    fetch_sources(offline=offline)
    owid = load_owid()
    who = load_who()
    merged = merge_sources(owid, who)
    log.info("Merged %s OWID rows with %s WHO rows", f"{len(owid):,}", f"{len(who):,}")
    return merged
