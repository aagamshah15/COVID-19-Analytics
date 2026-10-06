"""Request schemas: the scenario JSON the browser's engine consumes, with bounds on every number.

These mirror the dataclasses in ``covid_pipeline.simulator.scenario`` and the TypeScript types in
``dashboard/src/lib/sim/scenario.ts``. ``scenario.schema.json`` is generated from them
(``python -m api.schemas``); a dashboard test checks the browser's scenarios against it, so the two
sides can't drift apart unnoticed.

In this JSON, null means infinity ("never", "lifelong", "off") except where noted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_PATH = Path(__file__).with_name("scenario.schema.json")
MAX_DAYS = 3 * 365
# Every stage duration must be at least one engine sub-step (a quarter of a day).
MIN_DURATION = 0.25

Share = Annotated[float, Field(ge=0, le=1)]
ShareBands = Annotated[list[Share], Field(min_length=5, max_length=5)]
AgeBands = Annotated[list[Annotated[float, Field(ge=0, le=120)]], Field(min_length=5, max_length=5)]
Duration = Annotated[float, Field(ge=MIN_DURATION, le=36500)]
Day = Annotated[float, Field(ge=0, le=36500)]
Multiplier = Annotated[float, Field(gt=0, le=1000)]
Spread = Annotated[float, Field(ge=0, le=3)]
Source = Literal["calibrated", "observed", "predicted", "user"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Place(Strict):
    population: float = Field(ge=1, le=2e10)
    age_shares: ShareBands
    age_means: AgeBands
    beds_per_thousand: float = Field(ge=0, le=100)
    latitude: float | None = Field(ge=-90, le=90, description="null: no seasonality")
    bed_availability: Share
    icu_share_of_beds: Share
    transmission: Multiplier
    severity: Multiplier
    adherence: float = Field(ge=0, le=10)
    awareness: Multiplier
    access: Share
    death_reporting: Share
    vaccine_acceptance: Share
    vaccine_capacity: Share

    @model_validator(mode="after")
    def shares_sum_to_one(self) -> Place:
        if abs(sum(self.age_shares) - 1) > 1e-3:
            raise ValueError("age_shares must sum to 1")
        return self


class Pathogen(Strict):
    id: str = Field(max_length=80)
    name: str = Field(max_length=120)
    kind: Literal["historical", "hypothetical", "blank"]
    r0: float = Field(gt=0, le=50)
    latent_days: Duration
    infectious_days: Duration
    ifr: Share
    hosp: Share
    age_profile: Literal["steep", "rises", "w_shaped", "young", "flat"]
    hosp_days: Duration
    icu_share: Share
    immunity_days: Duration | None
    seasonality: Share | None = Field(description="null: the amplitude learned for SARS-CoV-2")
    vaccine_day: Day | None
    ve_infection: Share
    ve_death: Share
    vaccine_immunity_days: Duration | None
    assumptions: list[Annotated[str, Field(max_length=80)]] = Field(default_factory=list, max_length=40)
    sources: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=40)


class Segment(Strict):
    start_day: int = Field(ge=0, le=MAX_DAYS)
    end_day: int = Field(ge=0, le=MAX_DAYS)
    level: float = Field(ge=0, le=100)


class Response(Strict):
    segments: list[Segment] = Field(max_length=24)
    adaptive: bool
    adaptive_on: float = Field(ge=0, le=10)
    adaptive_off: float = Field(ge=0, le=10)
    adaptive_level: float = Field(ge=0, le=100)
    adaptive_min_days: float = Field(ge=0, le=MAX_DAYS)
    fatigue: bool
    awareness: bool
    isolation: Share
    border_delay_days: float = Field(ge=0, le=MAX_DAYS)
    surge: float = Field(ge=0, le=10)
    vaccine: bool
    vaccine_day: Day | None = Field(description="null: the pathogen's default")
    vaccine_oldest_first: bool
    treatment_day: Day | None
    treatment_effect: Share
    case_detection: Share
    seed_per_million: float = Field(gt=0, le=1e5)
    start_month: int = Field(ge=1, le=12)


class Variant(Strict):
    day: Day | None
    transmission: Multiplier
    severity: Multiplier
    escape: Share


class Constants(Strict):
    npi_coef: float = Field(ge=-1, le=1)
    fatigue_ratio: float = Field(ge=0, le=10)
    fatigue_start: Day
    fatigue_end: Day
    awareness_deaths_pm: Annotated[float, Field(gt=0, le=1e9)] | None
    awareness_power: float = Field(ge=0, le=10)
    covid_seasonality: Share
    season_peak_day_north: float = Field(ge=0, le=366)
    icu_death_share: Share
    unmet_multiplier: float = Field(ge=0, le=100)
    child_acceptance_ratio: Share
    reference_shares: ShareBands
    reference_means: AgeBands

    @model_validator(mode="after")
    def shares_sum_to_one(self) -> Constants:
        if abs(sum(self.reference_shares) - 1) > 1e-3:
            raise ValueError("reference_shares must sum to 1")
        return self


class Sources(Strict):
    transmission: Source
    severity: Source
    awareness: Source
    reporting: Source
    vaccine_acceptance: Source
    vaccine_capacity: Source


class CalibratedSpread(Strict):
    calibrated: Spread
    predicted: Spread


class ObservedSpread(Strict):
    observed: Spread
    predicted: Spread


class Uncertainty(Strict):
    log_transmission_sd: CalibratedSpread
    log_severity_sd: CalibratedSpread
    log_awareness_country_sd: CalibratedSpread
    logit_reporting_sd: ObservedSpread
    logit_vaccine_acceptance_sd: ObservedSpread
    log_vaccine_capacity_sd: ObservedSpread
    npi_coef_sd: Spread
    log_awareness_sd: Spread | None
    seasonality_sd: Spread
    log_r0_sd: Spread
    log_ifr_sd: Spread
    notes: str = Field(default="", max_length=400, description="Free text from the model card; ignored")


class Scenario(Strict):
    """One scenario, as the browser's engine consumes it."""

    place: Place
    sources: Sources
    pathogen: Pathogen
    response: Response
    variant: Variant
    constants: Constants
    uncertainty: Uncertainty
    days: int = Field(ge=7, le=MAX_DAYS)


class SimulateRequest(Strict):
    scenario: Scenario
    draws: int = Field(default=0, ge=0, le=500, description="Monte Carlo draws for ranges; 0 runs the central scenario only")
    seed: int = Field(default=1, ge=0, le=2**31 - 1)
    series: bool = Field(default=True, description="Include the central run's daily series")


class DeepRequest(Strict):
    scenario: Scenario
    seed: int = Field(default=1, ge=0, le=2**31 - 1)


def scenario_schema() -> dict:
    return Scenario.model_json_schema()


if __name__ == "__main__":
    SCHEMA_PATH.write_text(json.dumps(scenario_schema(), indent=2) + "\n")
    print(f"wrote {SCHEMA_PATH}")
