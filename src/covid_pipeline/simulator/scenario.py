"""Scenarios: a place, a pathogen and a response, translated into engine inputs.

Mirrored by ``dashboard/src/lib/sim/scenario.ts``. Sources and assumptions for every preset are in
``docs/simulator/RESEARCH.md`` section 5; values marked as assumptions there are listed in each
preset's ``assumptions`` so the app can label them.

Severity conventions
--------------------
* A pathogen's ``ifr`` and ``hosp`` are overall shares of infections in the **reference
  population** (the world's 2019 age structure). Its ``age_profile`` spreads them across the five
  bands, so the same disease is deadlier per infection in an older country.
* The ``steep`` profile is the Levin et al. (2020) meta-regression for SARS-CoV-2:
  log10(IFR %) = -3.27 + 0.0524 * age, evaluated at each band's mean age.
* Hospitalisation follows a flatter shape (the IFR shape to the power 0.6, an assumption), and is
  never less than ifr / 0.95, so the fatality per hospital stay stays below 95%.
* A country's learned ``severity`` multiplier applies to the 60-79 and 80+ bands only: IFR below
  65 was consistent across countries (O'Driscoll et al. 2021).

Seasonality
-----------
A pathogen's ``seasonality`` is the amplitude of a yearly cosine in transmission at latitudes of 40
degrees or more, fading linearly to nothing at the edge of the tropics (23.5 degrees). Transmission peaks in early January in
the north and early July in the south (the timing is estimated in M1). ``None`` means "use the
amplitude learned for SARS-CoV-2" (calibrated from deaths in M2).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace

import numpy as np

from .engine import N_BANDS, EngineInputs
from .season import hemisphere_day, season_weight

BANDS = ["0-19", "20-39", "40-59", "60-79", "80+"]
# Day of the year each month starts (non-leap year). A table rather than arithmetic so the browser
# port gets identical numbers (Python's round() rounds half to even, JavaScript's doesn't).
MONTH_START_DAY = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
LEVIN_INTERCEPT, LEVIN_SLOPE = -3.27, 0.0524
OLDER_BANDS = np.array([0, 0, 0, 1, 1], dtype=bool)
HOSP_SHAPE_POWER = 0.6
MAX_FATALITY_PER_STAY = 0.95
# Salje et al. (2020): 2.6% of infections hospitalised and 0.53% died, a ratio of 4.9.
COVID_HOSP_PER_DEATH = 2.6 / 0.53

# The world's 2019 age structure (population-weighted World Bank shares) and mean age per band.
# Training recomputes these and exports them; these defaults keep the module usable on its own.
REFERENCE_SHARES = np.array([0.3428, 0.3013, 0.2253, 0.1121, 0.0185])
REFERENCE_MEANS = np.array([9.77, 29.78, 49.45, 68.12, 85.0])

# Relative fatality by band for profiles that aren't a formula (assumptions; see RESEARCH.md).
FIXED_PROFILES = {
    "w_shaped": np.array([1.5, 3.0, 1.0, 0.7, 0.7]),  # 1918: young adults hit hardest
    "young": np.array([2.0, 1.0, 1.0, 1.5, 2.0]),  # measles: young children and older adults
    "flat": np.ones(N_BANDS),
}


def levin_ifr(age: np.ndarray) -> np.ndarray:
    """SARS-CoV-2 infection fatality (as a share, not %) at a given age (Levin et al. 2020)."""
    return 10 ** (LEVIN_INTERCEPT + LEVIN_SLOPE * np.asarray(age, dtype=float)) / 100


def age_shape(profile: str, band_means: np.ndarray) -> np.ndarray:
    """Relative fatality by band (unnormalised)."""
    if profile == "steep":
        return levin_ifr(band_means)
    if profile == "rises":  # half the Levin slope: an assumption for influenza-like pathogens
        return 10 ** (LEVIN_SLOPE / 2 * np.asarray(band_means, dtype=float))
    return FIXED_PROFILES[profile]


@dataclass
class Pathogen:
    id: str
    name: str
    kind: str  # historical | hypothetical | blank
    r0: float
    latent_days: float
    infectious_days: float
    ifr: float  # overall, in the reference population
    hosp: float  # overall, in the reference population
    age_profile: str  # steep | rises | w_shaped | young | flat
    hosp_days: float = 8.0
    icu_share: float = 0.25
    immunity_days: float = 365.0
    seasonality: float | None = 0.0  # None: the learned SARS-CoV-2 amplitude
    # Vaccine defaults for this pathogen (the response decides whether and when it's used).
    vaccine_day: float = float("inf")
    ve_infection: float = 0.6
    ve_death: float = 0.9
    vaccine_immunity_days: float = 365.0
    assumptions: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


def _covid(id: str, name: str, r0: float, latent: float, death_mult: float, hosp_mult: float, **kw) -> Pathogen:
    ifr = float(REFERENCE_SHARES @ levin_ifr(REFERENCE_MEANS)) * death_mult
    return Pathogen(
        id=id,
        name=name,
        kind="historical",
        r0=r0,
        latent_days=latent,
        infectious_days=5.0,
        ifr=ifr,
        hosp=float(REFERENCE_SHARES @ levin_ifr(REFERENCE_MEANS)) * COVID_HOSP_PER_DEATH * hosp_mult,
        age_profile="steep",
        hosp_days=10.0,
        seasonality=None,  # learned
        **kw,
    )


PRESETS: dict[str, Pathogen] = {
    p.id: p
    for p in [
        Pathogen(
            "seasonal_flu", "Seasonal flu", "historical", 1.28, 1, 3, 0.0005, 0.007, "rises",
            hosp_days=5, immunity_days=365, seasonality=0.2, vaccine_day=0, ve_infection=0.4, ve_death=0.6,
            vaccine_immunity_days=180,
            assumptions=["latent_days", "infectious_days", "ifr", "hosp", "hosp_days", "seasonality", "vaccine"],
            sources=["Biggerstaff 2014", "CDC 2018-19 burden"],
        ),
        Pathogen(
            "flu_2009", "2009 H1N1 flu", "historical", 1.46, 1, 3, 0.00005, 0.002, "rises",
            hosp_days=5, seasonality=0.2, vaccine_day=180, ve_infection=0.6, ve_death=0.8,
            assumptions=["latent_days", "infectious_days", "hosp", "hosp_days", "seasonality", "vaccine"],
            sources=["Biggerstaff 2014", "Wong 2013"],
        ),
        Pathogen(
            "flu_1957", "1957 flu (H2N2)", "historical", 1.65, 1, 3, 0.001, 0.01, "rises",
            hosp_days=6, immunity_days=730, seasonality=0.2,
            assumptions=["latent_days", "infectious_days", "ifr", "hosp", "hosp_days", "seasonality"],
            sources=["Biggerstaff 2014", "Taubenberger & Morens 2006", "Viboud 2016"],
        ),
        Pathogen(
            "flu_1968", "1968 flu (H3N2)", "historical", 1.80, 1, 3, 0.0005, 0.01, "rises",
            hosp_days=6, immunity_days=730, seasonality=0.2,
            assumptions=["latent_days", "infectious_days", "ifr", "hosp", "hosp_days", "seasonality"],
            sources=["Biggerstaff 2014", "Taubenberger & Morens 2006"],
        ),
        Pathogen(
            "flu_1918", "1918 flu", "historical", 1.80, 1, 3, 0.02, 0.05, "w_shaped",
            hosp_days=8, immunity_days=730, seasonality=0.2,
            assumptions=["latent_days", "infectious_days", "ifr", "hosp", "hosp_days", "age_profile", "seasonality"],
            sources=["Biggerstaff 2014", "Taubenberger & Morens 2006"],
        ),
        _covid(
            "covid_ancestral", "SARS-CoV-2 (2020)", 2.79, 3, 1.0, 1.0,
            vaccine_day=330, ve_infection=0.6, ve_death=0.9, vaccine_immunity_days=240,
            assumptions=["latent_days", "hosp_days", "icu_share", "immunity_days", "vaccine"],
            sources=["Liu & Rocklöv 2021", "Lauer 2020", "Levin 2020", "Salje 2020"],
        ),
        _covid(
            "covid_delta", "SARS-CoV-2 Delta", 5.08, 3, 2.21, 2.05,
            vaccine_day=0, ve_infection=0.6, ve_death=0.9, vaccine_immunity_days=240,
            assumptions=["latent_days", "hosp_days", "icu_share", "immunity_days", "vaccine"],
            sources=["Liu & Rocklöv 2021", "Fisman & Tuite 2021", "Levin 2020"],
        ),
        _covid(
            "covid_omicron", "SARS-CoV-2 Omicron", 8.2, 2, 2.21 * 0.31, 2.05 * 0.41,
            immunity_days=180, vaccine_day=0, ve_infection=0.3, ve_death=0.8, vaccine_immunity_days=120,
            assumptions=["latent_days", "hosp_days", "icu_share", "immunity_days", "vaccine"],
            sources=["Liu & Rocklöv 2022", "Nyberg 2022", "Fisman & Tuite 2021", "Levin 2020"],
        ),
        Pathogen(
            "sars_2003", "SARS (2003)", "historical", 2.7, 4, 7, 0.096, 0.7, "rises",
            hosp_days=21, icu_share=0.3, immunity_days=730,
            assumptions=["latent_days", "infectious_days", "ifr", "hosp", "hosp_days", "icu_share", "age_profile"],
            sources=["CDC MMWR 2003", "Riley 2003"],
        ),
        Pathogen(
            "mers", "MERS-like", "historical", 0.65, 5, 7, 0.36, 0.6, "rises",
            hosp_days=21, icu_share=0.4, immunity_days=730,
            assumptions=["latent_days", "infectious_days", "hosp", "hosp_days", "icu_share", "age_profile"],
            sources=["Breban 2013", "WHO EMRO 2025"],
        ),
        Pathogen(
            "h5n1_hypothetical", "H5N1-like (hypothetical)", "hypothetical", 1.8, 2, 4, 0.10, 0.30, "rises",
            hosp_days=14, icu_share=0.4, vaccine_day=180, ve_infection=0.6, ve_death=0.8,
            assumptions=["r0", "latent_days", "infectious_days", "ifr", "hosp", "hosp_days", "icu_share", "age_profile", "vaccine"],
            sources=["WHO WPRO 2026"],
        ),
        Pathogen(
            "smallpox", "Smallpox-like", "historical", 4.5, 12, 9, 0.30, 0.5, "flat",
            hosp_days=14, icu_share=0.2, immunity_days=float("inf"), vaccine_day=14, ve_infection=0.95, ve_death=0.98,
            vaccine_immunity_days=float("inf"),
            assumptions=["latent_days", "infectious_days", "ifr", "hosp", "hosp_days", "icu_share", "age_profile", "vaccine"],
            sources=["Gani & Leach 2001", "Merck Manual"],
        ),
        Pathogen(
            "measles", "Measles-like", "historical", 15.0, 10, 8, 0.002, 0.2, "young",
            hosp_days=5, icu_share=0.1, immunity_days=float("inf"), vaccine_day=0, ve_infection=0.95, ve_death=0.98,
            vaccine_immunity_days=float("inf"),
            assumptions=["latent_days", "infectious_days", "hosp_days", "icu_share", "age_profile", "vaccine"],
            sources=["Guerra 2017", "CDC", "Portnoy 2019"],
        ),
        Pathogen(
            "disease_x", "Disease X (blank slate)", "blank", 2.5, 3, 5, 0.005, 0.03, "rises",
            vaccine_day=365, ve_infection=0.6, ve_death=0.85,
            assumptions=["r0", "latent_days", "infectious_days", "ifr", "hosp", "age_profile", "vaccine"],
        ),
    ]
}


@dataclass
class Place:
    """A country or region: who lives there, its health system and its learned behaviour."""

    population: float
    age_shares: list[float]
    age_means: list[float]
    beds_per_thousand: float
    latitude: float | None = None  # None: no seasonality
    bed_availability: float = 0.5  # share of beds that can be given to the epidemic (assumption)
    icu_share_of_beds: float = 0.05  # assumption: no source publishes ICU beds for most countries
    transmission: float = 1.0  # learned multiplier on R0
    severity: float = 1.0  # learned multiplier on IFR in the 60+ bands
    adherence: float = 1.0  # learned multiplier on the lockdown effect
    awareness: float = 1.0  # learned multiplier on the awareness threshold (higher: tolerates more deaths)
    access: float = 0.75  # access to care, 0-1 (UHC service coverage / 100)
    death_reporting: float = 1.0  # learned share of deaths reported
    vaccine_acceptance: float = 0.8  # learned ceiling for adults
    vaccine_capacity: float = 0.005  # learned people vaccinated per day, share of population


@dataclass
class Segment:
    start_day: int
    end_day: int
    level: float  # stringency 0-100


@dataclass
class Response:
    segments: list[Segment] = field(default_factory=list)
    adaptive: bool = False
    adaptive_on: float = 0.8
    adaptive_off: float = 0.4
    adaptive_level: float = 70.0
    adaptive_min_days: float = 21.0
    fatigue: bool = True
    awareness: bool = True  # people cut contacts as reported deaths rise
    isolation: float = 0.0  # share of transmission removed by testing and isolation
    border_delay_days: float = 0.0
    surge: float = 0.0  # extra beds as a share of the normal epidemic allocation
    vaccine: bool = True
    vaccine_day: float | None = None  # None: the pathogen's default
    vaccine_oldest_first: bool = True
    treatment_day: float = float("inf")
    treatment_effect: float = 0.2  # share of hospital deaths averted with full access to care
    case_detection: float = 0.2
    seed_per_million: float = 2.0
    start_month: int = 1  # month the first infections arrive (sets the seasonal phase)


@dataclass
class Variant:
    day: float = float("inf")
    transmission: float = 1.0
    severity: float = 1.0
    escape: float = 0.0


@dataclass
class ModelConstants:
    """Learned, place-independent constants exported by training."""

    npi_coef: float = -0.0125  # log transmission per stringency point, first year
    fatigue_ratio: float = 0.55  # late effect / early effect
    fatigue_start: float = 270.0
    fatigue_end: float = 450.0
    awareness_deaths_pm: float = float("inf")  # learned in calibration
    covid_seasonality: float = 0.0  # learned in calibration
    season_peak_day_north: float = 8.0  # learned in M1 (day of year)
    awareness_power: float = 2.0  # assumption: how sharply people react around the threshold
    icu_death_share: float = 0.5  # assumption
    unmet_multiplier: float = 3.0  # assumption
    child_acceptance_ratio: float = 0.7  # assumption: children's uptake relative to adults'
    reference_shares: list[float] = field(default_factory=lambda: REFERENCE_SHARES.tolist())
    reference_means: list[float] = field(default_factory=lambda: REFERENCE_MEANS.tolist())


def band_severity(pathogen: Pathogen, place: Place, constants: ModelConstants) -> tuple[np.ndarray, np.ndarray]:
    """Per-band IFR and hospitalisation share for this pathogen in this place."""
    ref_shares, ref_means = np.array(constants.reference_shares), np.array(constants.reference_means)
    shape = age_shape(pathogen.age_profile, np.array(place.age_means))
    ref_shape = age_shape(pathogen.age_profile, ref_means)
    ifr = pathogen.ifr * shape / float(ref_shares @ ref_shape)
    ifr = np.where(OLDER_BANDS, ifr * place.severity, ifr)

    hosp_shape = shape**HOSP_SHAPE_POWER
    hosp = pathogen.hosp * hosp_shape / float(ref_shares @ ref_shape**HOSP_SHAPE_POWER)
    hosp = np.maximum(hosp, ifr / MAX_FATALITY_PER_STAY)
    return np.minimum(ifr, MAX_FATALITY_PER_STAY), np.minimum(hosp, 1.0)


def seasonal_terms(pathogen: Pathogen, place: Place, response: Response, constants: ModelConstants) -> tuple[float, float]:
    """(amplitude, simulation day of peak transmission) for this pathogen, place and start month."""
    if place.latitude is None:
        return 0.0, 0.0
    base = constants.covid_seasonality if pathogen.seasonality is None else pathogen.seasonality
    amplitude = float(base * season_weight(place.latitude))
    start_day = MONTH_START_DAY[response.start_month - 1]
    # Peak day of year in this hemisphere (hemisphere_day maps both ways: it's a half-year shift).
    peak = float(hemisphere_day(constants.season_peak_day_north, place.latitude))
    return amplitude, (peak - start_day) % 365


def stringency_series(response: Response, days: int) -> np.ndarray:
    series = np.zeros(days)
    for seg in response.segments:
        series[max(seg.start_day, 0) : min(seg.end_day, days)] = seg.level
    return series


def build_inputs(
    place: Place,
    pathogen: Pathogen,
    response: Response,
    days: int,
    constants: ModelConstants | None = None,
    variant: Variant | None = None,
    stringency: np.ndarray | None = None,
) -> EngineInputs:
    """Engine inputs for one scenario. ``stringency`` overrides the response's segments (calibration)."""
    c = constants or ModelConstants()
    v = variant or Variant()
    ifr, hosp = band_severity(pathogen, place, c)
    beds = place.beds_per_thousand * place.population / 1000 * place.bed_availability * (1 + response.surge)
    npi_coef = c.npi_coef * place.adherence
    vaccine_day = (pathogen.vaccine_day if response.vaccine_day is None else response.vaccine_day) if response.vaccine else float("inf")
    acceptance = np.full(N_BANDS, place.vaccine_acceptance)
    acceptance[0] *= c.child_acceptance_ratio
    seasonality, season_peak_day = seasonal_terms(pathogen, place, response, c)
    return EngineInputs.broadcast(
        days,
        population=place.population,
        age_shares=np.array(place.age_shares),
        r0=pathogen.r0 * place.transmission,
        latent_days=pathogen.latent_days,
        infectious_days=pathogen.infectious_days,
        ifr=ifr,
        hosp=hosp,
        hosp_days=pathogen.hosp_days,
        icu_share=pathogen.icu_share,
        immunity_days=pathogen.immunity_days,
        seed_per_million=response.seed_per_million,
        seed_day=response.border_delay_days,
        seasonality=seasonality,
        season_peak_day=season_peak_day,
        npi_coef=npi_coef,
        npi_coef_late=npi_coef * (c.fatigue_ratio if response.fatigue else 1.0),
        fatigue_start=c.fatigue_start,
        fatigue_end=c.fatigue_end,
        isolation=response.isolation,
        awareness_deaths_pm=c.awareness_deaths_pm * place.awareness if response.awareness else float("inf"),
        awareness_power=c.awareness_power,
        stringency=stringency_series(response, days) if stringency is None else stringency,
        adaptive=float(response.adaptive),
        adaptive_on=response.adaptive_on,
        adaptive_off=response.adaptive_off,
        adaptive_level=response.adaptive_level,
        adaptive_min_days=response.adaptive_min_days,
        variant_day=v.day,
        variant_transmission=v.transmission,
        variant_severity=v.severity,
        variant_escape=v.escape,
        vaccine_day=vaccine_day,
        vaccine_capacity=place.vaccine_capacity,
        vaccine_acceptance=acceptance,
        ve_infection=pathogen.ve_infection,
        ve_death=max(pathogen.ve_death, pathogen.ve_infection),
        vaccine_immunity_days=pathogen.vaccine_immunity_days,
        vaccine_oldest_first=float(response.vaccine_oldest_first),
        treatment_day=response.treatment_day,
        treatment_effect=response.treatment_effect * place.access,
        beds=beds,
        icu_beds=beds * place.icu_share_of_beds,
        icu_death_share=c.icu_death_share,
        unmet_multiplier=c.unmet_multiplier,
        death_reporting=place.death_reporting,
        case_detection=response.case_detection,
    )


def preset(id: str, **overrides) -> Pathogen:
    return replace(PRESETS[id], **overrides)


def pathogen_dict(p: Pathogen) -> dict:
    """JSON-safe preset. Infinities become None ("never"/"lifelong"); seasonality None is "learned"."""
    return {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in asdict(p).items()}
