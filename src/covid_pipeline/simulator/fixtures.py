"""Golden scenarios: the contract between the Python reference engine and the browser engine.

``dashboard/src/lib/sim/golden.json`` holds, for each scenario, the high-level inputs (place,
pathogen, response, variant, constants), the engine inputs ``build_inputs`` derives from them, and
the engine's outputs. The TypeScript tests rebuild the inputs and rerun the engine and must match
to 1e-9; ``tests/test_sim_fixtures.py`` fails if the file is stale. Regenerate with
``covid-pipeline sim-fixtures`` after changing the engine or the scenario layer.

Infinity ("never", "lifelong", "off") is written as null, which JSON can carry.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, fields, replace

import numpy as np

from ..config import PROJECT_ROOT
from .engine import EngineInputs, run
from .scenario import PRESETS, ModelConstants, Place, Response, Segment, Variant, build_inputs, pathogen_dict

GOLDEN_PATH = PROJECT_ROOT / "dashboard" / "src" / "lib" / "sim" / "golden.json"
DAYS = 240
SERIES = ["infections", "admissions", "hospital", "deaths", "reported_deaths", "rt", "stringency", "vaccinated", "susceptible", "dead"]
SIGNIFICANT = 13

PLACE = Place(
    population=25_000_000,
    age_shares=[0.24, 0.27, 0.26, 0.19, 0.04],
    age_means=[9.8, 29.7, 49.6, 67.9, 85.0],
    beds_per_thousand=2.8,
    latitude=46.0,
    transmission=1.1,
    severity=0.8,
    adherence=1.2,
    awareness=1.6,
    access=0.8,
    death_reporting=0.6,
    vaccine_acceptance=0.75,
    vaccine_capacity=0.004,
)
CONSTANTS = ModelConstants(npi_coef=-0.0078, fatigue_ratio=0.8, awareness_deaths_pm=2.5, covid_seasonality=0.38, season_peak_day_north=2.0)


def _cases() -> dict[str, tuple]:
    covid = PRESETS["covid_ancestral"]
    return {
        "covid_lockdown_and_vaccine": (
            PLACE,
            covid,
            Response(segments=[Segment(20, 90, 75), Segment(90, 160, 40)], vaccine_day=120, start_month=3),
            Variant(),
            CONSTANTS,
        ),
        "adaptive_policy_variant_and_waning": (
            replace(PLACE, latitude=-33.0, beds_per_thousand=1.5),
            replace(PRESETS["covid_delta"], immunity_days=120.0),
            Response(
                adaptive=True,
                adaptive_on=0.5,
                adaptive_off=0.2,
                adaptive_level=80,
                isolation=0.1,
                border_delay_days=12,
                surge=0.3,
                treatment_day=60,
                treatment_effect=0.3,
                vaccine_day=30,
                vaccine_oldest_first=False,
                start_month=10,
            ),
            Variant(day=110, transmission=1.6, severity=0.5, escape=0.3),
            replace(CONSTANTS, awareness_deaths_pm=math.inf),
        ),
        "measles_in_the_south": (
            replace(PLACE, latitude=-20.0, age_shares=[0.45, 0.3, 0.15, 0.08, 0.02], age_means=[9.0, 28.0, 48.0, 66.0, 84.0]),
            PRESETS["measles"],
            Response(vaccine_day=10, start_month=7, fatigue=False),
            Variant(),
            CONSTANTS,
        ),
        "overwhelmed_hospitals": (
            replace(PLACE, beds_per_thousand=0.6, access=0.4),
            PRESETS["h5n1_hypothetical"],
            Response(vaccine=False, awareness=False),
            Variant(),
            CONSTANTS,
        ),
        "subcritical_mers": (
            PLACE,
            PRESETS["mers"],
            Response(seed_per_million=20),
            Variant(),
            CONSTANTS,
        ),
    }


def _round(value):
    """Round to SIGNIFICANT digits; infinity becomes None."""
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_round(v) for v in value]
    if isinstance(value, dict):
        return {k: _round(v) for k, v in value.items()}
    if isinstance(value, (bool, str)) or value is None:
        return value
    v = float(value)
    if not math.isfinite(v):
        return None
    return float(f"{v:.{SIGNIFICANT}g}")


def engine_inputs_dict(inputs: EngineInputs) -> dict:
    """One lane of engine inputs as plain JSON values."""
    out = {}
    for f in fields(inputs):
        arr = getattr(inputs, f.name)[0]
        out[f.name] = arr.tolist() if np.ndim(arr) else float(arr)
    return out


def golden_cases() -> dict:
    cases = {}
    for name, (place, pathogen, response, variant, constants) in _cases().items():
        inputs = build_inputs(place, pathogen, response, DAYS, constants, variant)
        outputs = run(inputs, DAYS)
        cases[name] = _round(
            {
                "days": DAYS,
                "place": asdict(place),
                "pathogen": pathogen_dict(pathogen),
                "response": asdict(response),
                "variant": asdict(variant),
                "constants": asdict(constants),
                "inputs": engine_inputs_dict(inputs),
                "outputs": {s: getattr(outputs, s)[0].tolist() for s in SERIES} | {"deaths_by_age": outputs.deaths_by_age[0].tolist()},
            }
        )
    return {"generated_by": "covid-pipeline sim-fixtures", "significant_digits": SIGNIFICANT, "cases": cases}


def write_golden() -> None:
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(golden_cases(), separators=(",", ":"), allow_nan=False) + "\n")
