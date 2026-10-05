"""World Bank WDI indicators: the pre-pandemic country profile the simulator starts from.

Every indicator is static per country: the latest non-missing value in ``YEARS`` (2010-2019, so the
profile describes each country going into the pandemic). The raw API responses are stored verbatim
in one JSON file and fingerprinted in the manifest like the OWID and WHO sources.

Age structure comes from the WDI 5-year age groups by sex, aggregated to the simulator's five bands,
so no age pyramid has to be guessed from the median age.

The API has outages, and a failed download would cancel the whole pipeline run. Because these are
historical values that no longer change, ``data/reference/worldbank_wdi_snapshot.json`` keeps a
versioned copy (each country's latest value per indicator, which is all the loader reads).
``fetch_worldbank`` uses it when the API is unavailable; refresh it with
``covid-pipeline worldbank-snapshot`` after adding an indicator.
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import RAW_WORLDBANK_PATH, WORLDBANK_SNAPSHOT_PATH, WORLDBANK_URL

log = logging.getLogger(__name__)

YEARS = "2010:2019"
# A healthy API serves every indicator in about a minute. Past this, treat it as down.
FETCH_BUDGET_SECONDS = 300

# Simulator name -> WDI code.
STATIC_INDICATORS = {
    "urban_share": "SP.URB.TOTL.IN.ZS",
    "hospital_beds_wb": "SH.MED.BEDS.ZS",
    "physicians_per_thousand": "SH.MED.PHYS.ZS",
    "health_exp_per_capita": "SH.XPD.CHEX.PC.CD",
    "out_of_pocket_share": "SH.XPD.OOPC.CH.ZS",
    "uhc_index": "SH_UHC_SCI",
    "basic_sanitation": "SH.STA.BASS.ZS",
    "measles_immunization": "SH.IMM.MEAS",
    "dtp3_immunization": "SH.IMM.IDPT",
    "female_share": "SP.POP.TOTL.FE.ZS",
}
AGE_GROUPS = [f"{lo:02d}{lo + 4:02d}" for lo in range(0, 80, 5)] + ["80UP"]
AGE_INDICATORS = {f"age_{g}_{sex.lower()}": f"SP.POP.{g}.{sex}.5Y" for g in AGE_GROUPS for sex in ("FE", "MA")}
INDICATORS = {**STATIC_INDICATORS, **AGE_INDICATORS}

# The simulator's five age bands, each built from four 5-year groups (80+ is one open group).
AGE_BANDS = {
    "0_19": ["0004", "0509", "1014", "1519"],
    "20_39": ["2024", "2529", "3034", "3539"],
    "40_59": ["4044", "4549", "5054", "5559"],
    "60_79": ["6064", "6569", "7074", "7579"],
    "80_plus": ["80UP"],
}
# Midpoint of each 5-year group; 80+ is open-ended, so 85 is an assumption.
GROUP_MIDPOINT = {g: (int(g[:2]) + 2.5 if g != "80UP" else 85.0) for g in AGE_GROUPS}

# WDI codes that differ from OWID's ISO3 codes.
ISO3_OVERRIDES = {"XKX": "OWID_KOS"}


def _get_json(url: str, timeout: int = 30, attempts: int = 3) -> list:
    """One API page. Kept short: a hanging API should reach the snapshot fallback in a couple of minutes."""
    request = urllib.request.Request(url, headers={"User-Agent": "covid19-healthcare-burden-pipeline"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def _fetch_indicator(code: str) -> list[dict]:
    """All rows for one indicator, following pagination. Raises if the API reports an error."""
    rows: list[dict] = []
    page, pages = 1, 1
    while page <= pages:
        payload = _get_json(WORLDBANK_URL.format(indicator=code, years=YEARS) + f"&page={page}")
        if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
            raise ValueError(f"World Bank API returned no data for {code}: {str(payload)[:200]}")
        pages = int(payload[0].get("pages", 1))
        rows.extend(payload[1])
        page += 1
    return rows


def _write_atomically(payload: dict, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=dest.parent, delete=False, suffix=".part") as tmp:
        json.dump(payload, tmp, separators=(",", ":"))
    Path(tmp.name).replace(dest)


def fetch_worldbank(
    dest: Path = RAW_WORLDBANK_PATH, snapshot_path: Path = WORLDBANK_SNAPSHOT_PATH, budget: float = FETCH_BUDGET_SECONDS
) -> str:
    """Download every indicator and write them to ``dest`` atomically (all or nothing).

    Returns "live", or "snapshot" if the API was unavailable (down, or too slow to finish within
    ``budget`` seconds) and the versioned copy was used instead.
    """
    started = time.monotonic()
    try:
        indicators = {}
        for code in INDICATORS.values():
            if time.monotonic() - started > budget:
                raise TimeoutError(f"only {len(indicators)} of {len(INDICATORS)} indicators after {budget:.0f} seconds")
            indicators[code] = _fetch_indicator(code)
    except (OSError, ValueError) as error:  # network errors and timeouts are OSErrors; bad payloads are ValueErrors
        if not snapshot_path.exists():
            raise
        payload = json.loads(snapshot_path.read_text())
        missing = sorted(set(INDICATORS.values()) - set(payload["indicators"]))
        if missing:
            raise ValueError(f"World Bank API unavailable and the snapshot lacks {missing}") from error
        log.warning("World Bank API unavailable (%s). Using the snapshot fetched %s", error, payload.get("fetched_at_utc"))
        _write_atomically(payload, dest)
        return "snapshot"
    _write_atomically({"fetched_at_utc": datetime.now(UTC).isoformat(timespec="seconds"), "years": YEARS, "indicators": indicators}, dest)
    log.info("World Bank: %s indicators written to %s", len(indicators), dest)
    return "live"


def snapshot(payload: dict) -> dict:
    """The smallest payload that loads to the same profile: each country's latest value per indicator."""
    slim = {}
    for code, rows in payload["indicators"].items():
        latest: dict[str, dict] = {}
        for r in rows:
            iso = r.get("countryiso3code")
            if not iso or r.get("value") is None:
                continue
            if iso not in latest or int(r["date"]) > int(latest[iso]["date"]):
                latest[iso] = {"countryiso3code": iso, "date": r["date"], "value": r["value"]}
        slim[code] = [latest[iso] for iso in sorted(latest)]
    return {"fetched_at_utc": payload["fetched_at_utc"], "years": payload["years"], "snapshot": True, "indicators": slim}


def write_snapshot(raw: Path = RAW_WORLDBANK_PATH, dest: Path = WORLDBANK_SNAPSHOT_PATH) -> None:
    """Refresh the versioned copy from the last successful download."""
    payload = json.loads(Path(raw).read_text())
    if payload.get("snapshot"):
        raise ValueError(f"{raw} is itself the snapshot: download from the live API first (covid-pipeline ingest)")
    _write_atomically(snapshot(payload), dest)
    log.info("World Bank snapshot written to %s", dest)


def _latest(rows: list[dict]) -> pd.Series:
    """Latest non-missing value per ISO3 code."""
    frame = pd.DataFrame(
        [(r["countryiso3code"], int(r["date"]), r["value"]) for r in rows if r.get("value") is not None and r.get("countryiso3code")],
        columns=["iso3", "year", "value"],
    )
    if frame.empty:
        return pd.Series(dtype=float)
    frame["iso3"] = frame["iso3"].replace(ISO3_OVERRIDES)
    return frame.sort_values("year").groupby("iso3")["value"].last().astype(float)


def age_structure(raw: pd.DataFrame) -> pd.DataFrame:
    """Population share and mean age of each simulator band, from WDI 5-year shares by sex.

    WDI publishes each group as a share of that sex's population, so groups are weighted by the
    female share of the total population. Shares are renormalised to sum to exactly 1.
    """
    female = raw["female_share"] / 100
    groups = pd.DataFrame(
        {g: (female * raw[f"age_{g}_fe"] + (1 - female) * raw[f"age_{g}_ma"]) / 100 for g in AGE_GROUPS},
        index=raw.index,
    )
    out = pd.DataFrame(index=raw.index)
    total = groups.sum(axis=1)
    for band, members in AGE_BANDS.items():
        share = groups[members].sum(axis=1)
        out[f"age_{band}"] = share / total
        midpoints = np.array([GROUP_MIDPOINT[g] for g in members])
        out[f"age_mean_{band}"] = (groups[members] * midpoints).sum(axis=1) / share.where(share > 0)
    out["share_65_plus"] = groups[["6569", "7074", "7579", "80UP"]].sum(axis=1) / total
    return out.where(groups.notna().all(axis=1))


def load_worldbank(path: Path = RAW_WORLDBANK_PATH) -> pd.DataFrame:
    """One row per ISO3 code (index ``iso_code``) with each indicator's latest pre-pandemic value."""
    payload = json.loads(Path(path).read_text())
    raw = pd.DataFrame({name: _latest(payload["indicators"].get(code, [])) for name, code in INDICATORS.items()})
    raw.index.name = "iso_code"
    static = raw[list(STATIC_INDICATORS)].drop(columns="female_share")
    return pd.concat([static, age_structure(raw)], axis=1)
