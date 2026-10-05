"""Reference simulation engine: an age-structured SEIR model with vaccination and hospital care.

This is the reference implementation. ``dashboard/src/lib/sim/engine.ts`` mirrors it line for line,
and golden-scenario tests hold the two within 1e-9. Any change here must be made there too.

Compartments, for each of the five age bands (0-19, 20-39, 40-59, 60-79, 80+):

    S  susceptible            V  vaccinated, not infected
    Em exposed, will recover  Es exposed, will need hospital care
    Im infectious, mild       Is infectious, will need hospital care
    H  in hospital (ward + ICU; ICU demand is a fixed share of H)
    R  recovered              D  died

* Mixing is homogeneous across ages (a stated v1 limitation): one force of infection for everyone.
* Severity is decided at infection: a share ``hosp`` of new infections enters the Es/Is/H path.
  Infections of vaccinated people are scaled by ``(1 - ve_death) / (1 - ve_infection)``, so the
  vaccine's protection against death is ``ve_death`` overall.
* Deaths happen in hospital. The fatality per hospital stay is ``ifr / hosp``, raised when ICU
  demand nears or exceeds capacity (Bravata et al. 2021) and lowered once treatment is available.
* Infection uses the exact probability ``1 - exp(-force * dt)`` (computed with expm1). Stage exits use ``dt / duration``
  per sub-step, which keeps each stage's mean duration exact (an exponential exit probability
  would stretch a 5-day infectious period to 5.13 days and inflate R0). No compartment can go
  negative. Four sub-steps per day; every duration must be at least ``dt``.
* Awareness (Weitz et al., PNAS 2020): people cut contacts as reported deaths rise. Transmission
  is divided by ``1 + (D / awareness_deaths_pm) ** awareness_power``, where D is a 7-day moving
  average of reported daily deaths per million. Without it, the model overshoots real epidemics.
* Every array has a leading "lane" axis, so one call runs many scenarios at once (calibration
  grids, Monte Carlo draws). Per-lane scalars have shape (lanes,), per-band values (lanes, 5) and
  time series (lanes, days).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields

import numpy as np

N_BANDS = 5
SUBSTEPS = 4
COMPARTMENTS = ("S", "V", "Em", "Es", "Im", "Is", "H", "R", "D")

# ICU strain -> mortality multiplier for ICU-level patients, from Bravata et al. (JAMA Netw Open
# 2021): HR 0.99 at 25-50% COVID ICU demand, 1.19 at 50-75% and 1.94 at 75-100%, placed at the
# band midpoints. Above capacity, unmet patients get ``unmet_multiplier`` (an assumption).
OVERLOAD_POINTS = np.array([[0.0, 1.0], [0.5, 1.0], [0.625, 1.19], [0.875, 1.94], [1.0, 1.94]])


@dataclass
class EngineInputs:
    """Everything one simulation needs. Shapes: scalars (L,), per-band (L, 5), per-day (L, days)."""

    population: np.ndarray  # total people
    age_shares: np.ndarray  # (L, 5), sums to 1
    r0: np.ndarray
    latent_days: np.ndarray
    infectious_days: np.ndarray
    ifr: np.ndarray  # (L, 5) infection fatality, unvaccinated, normal care
    hosp: np.ndarray  # (L, 5) share of infections needing hospital care; >= ifr
    hosp_days: np.ndarray
    icu_share: np.ndarray  # share of hospital patients who need ICU
    immunity_days: np.ndarray  # mean duration of infection-acquired immunity (inf = lifelong)
    seed_per_million: np.ndarray  # infectious people introduced on ``seed_day``
    seed_day: np.ndarray  # day the first infections arrive (border measures delay it)
    # Transmission modifiers.
    seasonality: np.ndarray  # amplitude, 0 = none
    season_peak_day: np.ndarray  # simulation day of peak transmission
    npi_coef: np.ndarray  # log change in transmission per stringency point (negative)
    # Pandemic fatigue: the coefficient moves linearly to ``npi_coef_late`` between these days.
    npi_coef_late: np.ndarray
    fatigue_start: np.ndarray
    fatigue_end: np.ndarray
    isolation: np.ndarray  # share of transmission removed by testing and isolation
    awareness_deaths_pm: np.ndarray  # reported daily deaths per million that halve transmission (inf = off)
    awareness_power: np.ndarray
    stringency: np.ndarray  # (L, days) scheduled stringency, 0-100
    # Adaptive policy: switch to ``adaptive_level`` when hospital occupancy reaches ``adaptive_on``
    # (share of COVID-available beds) and release below ``adaptive_off`` after ``adaptive_min_days``.
    adaptive: np.ndarray  # 0/1
    adaptive_on: np.ndarray
    adaptive_off: np.ndarray
    adaptive_level: np.ndarray
    adaptive_min_days: np.ndarray
    # Variant arriving mid-epidemic.
    variant_day: np.ndarray  # inf = none
    variant_transmission: np.ndarray  # multiplier on transmission
    variant_severity: np.ndarray  # multiplier on hospitalisation and death
    variant_escape: np.ndarray  # share of the immune who become susceptible again
    # Vaccination.
    vaccine_day: np.ndarray  # inf = no vaccine
    vaccine_capacity: np.ndarray  # people vaccinated per day, as a share of the population
    vaccine_acceptance: np.ndarray  # (L, 5) share of each band who will take it
    ve_infection: np.ndarray
    ve_death: np.ndarray  # >= ve_infection
    vaccine_immunity_days: np.ndarray
    vaccine_oldest_first: np.ndarray  # 1 = oldest bands first, 0 = everyone in proportion
    # Care.
    treatment_day: np.ndarray  # inf = never
    treatment_effect: np.ndarray  # share of hospital deaths averted, already scaled by access
    beds: np.ndarray  # hospital beds available to the epidemic
    icu_beds: np.ndarray
    icu_death_share: np.ndarray  # share of hospital deaths that are among ICU-level patients
    unmet_multiplier: np.ndarray  # mortality multiplier for ICU-level patients beyond capacity
    # Reporting.
    death_reporting: np.ndarray  # share of deaths that are reported
    case_detection: np.ndarray  # share of infections that become reported cases

    @property
    def lanes(self) -> int:
        return int(np.shape(self.population)[0])

    @classmethod
    def broadcast(cls, days: int, **values) -> EngineInputs:
        """Build inputs from scalars or arrays, broadcasting everything to a common lane count.

        A leading axis is the lane axis: 1-D for scalars, 2-D for per-band values and the
        stringency series. A 1-D per-band value or stringency series is shared by every lane.
        """
        lanes = 1
        for name, value in values.items():
            arr = np.asarray(value, dtype=float)
            per_lane_ndim = 2 if name in _BANDED or name == "stringency" else 1
            if arr.ndim == per_lane_ndim:
                lanes = max(lanes, arr.shape[0])
        out = {}
        for f in fields(cls):
            arr = np.asarray(values[f.name], dtype=float)
            if f.name in _BANDED:
                shape = (lanes, N_BANDS)
            elif f.name == "stringency":
                shape = (lanes, days)
            else:
                shape = (lanes,)
            out[f.name] = np.broadcast_to(arr, shape).copy()
        return cls(**out)


_BANDED = {"age_shares", "ifr", "hosp", "vaccine_acceptance"}


@dataclass
class EngineOutputs:
    """Daily series, shape (lanes, days), plus end-of-run deaths by age band (lanes, 5)."""

    infections: np.ndarray
    admissions: np.ndarray
    hospital: np.ndarray  # occupancy at the end of each day
    icu: np.ndarray
    deaths: np.ndarray
    reported_deaths: np.ndarray
    reported_cases: np.ndarray
    rt: np.ndarray  # effective reproduction number at the start of each day
    stringency: np.ndarray  # stringency actually applied (schedule or adaptive)
    vaccinated: np.ndarray  # cumulative people vaccinated
    susceptible: np.ndarray  # S at the end of each day
    infected: np.ndarray  # E + I at the end of each day
    immune: np.ndarray  # R + V at the end of each day
    dead: np.ndarray  # cumulative deaths
    deaths_by_age: np.ndarray = field(default_factory=lambda: np.zeros((0, N_BANDS)))


def overload_multiplier(ratio: np.ndarray, unmet: np.ndarray) -> np.ndarray:
    """Mortality multiplier for ICU-level patients at a given demand/capacity ratio."""
    within = np.interp(np.minimum(ratio, 1.0), OVERLOAD_POINTS[:, 0], OVERLOAD_POINTS[:, 1])
    over = np.maximum(ratio - 1.0, 0.0)
    # Above capacity: patients up to capacity get the 100%-strain multiplier, the rest ``unmet``.
    return np.where(ratio > 1.0, (OVERLOAD_POINTS[-1, 1] + unmet * over) / np.maximum(ratio, 1.0), within)


def _p(rate: np.ndarray, dt: float) -> np.ndarray:
    """Probability of being infected within dt at a constant force of infection.

    expm1 keeps precision when the force is tiny (1 - exp(-x) cancels catastrophically).
    """
    return -np.expm1(-rate * dt)


def _exit(duration: np.ndarray, dt: float) -> np.ndarray:
    """Per-sub-step exit probability that gives a stage a mean duration of exactly ``duration``."""
    return np.minimum(dt / duration, 1.0)


def run(inputs: EngineInputs, days: int) -> EngineOutputs:
    x = inputs
    L = x.lanes
    dt = 1.0 / SUBSTEPS
    pop_band = x.population[:, None] * x.age_shares  # (L, 5)

    seed = np.minimum(x.seed_per_million * x.population / 1e6, x.population * 0.01)[:, None] * x.age_shares
    seed_day = np.floor(x.seed_day)
    S = pop_band.copy()
    V = np.zeros((L, N_BANDS))
    Em = np.zeros((L, N_BANDS))
    Es = np.zeros((L, N_BANDS))
    Im = np.zeros((L, N_BANDS))
    Is = np.zeros((L, N_BANDS))
    H = np.zeros((L, N_BANDS))
    R = np.zeros((L, N_BANDS))
    D = np.zeros((L, N_BANDS))
    vaccinated = np.zeros((L, N_BANDS))  # people ever vaccinated, per band

    fatality = np.minimum(x.ifr / np.maximum(x.hosp, 1e-12), 1.0)  # per hospital stay
    vaccine_severity = (1 - x.ve_death) / np.maximum(1 - x.ve_infection, 1e-12)
    beta0 = x.r0 / x.infectious_days
    p_latent = _exit(x.latent_days, dt)[:, None]
    p_infectious = _exit(x.infectious_days, dt)[:, None]
    p_discharge = _exit(x.hosp_days, dt)[:, None]
    p_wane = _exit(x.immunity_days, dt)[:, None]  # inf -> 0
    p_vaccine_wane = _exit(x.vaccine_immunity_days, dt)[:, None]
    oldest_first = x.vaccine_oldest_first > 0.5
    eligible_cap = x.vaccine_acceptance * pop_band

    out = {name: np.zeros((L, days)) for name in EngineOutputs.__dataclass_fields__ if name != "deaths_by_age"}
    adaptive_on = np.zeros(L, dtype=bool)
    adaptive_since = np.zeros(L)
    escaped = np.zeros(L, dtype=bool)
    recent_deaths_pm = np.zeros(L)  # moving average of reported daily deaths per million

    for day in range(days):
        # --- once per day: seeding, policy, variant escape, effective reproduction number ----
        seeding = (seed_day == day)[:, None]
        if seeding.any():
            arriving = np.where(seeding, np.minimum(seed, S), 0.0)
            S = S - arriving
            Im = Im + arriving * (1 - x.hosp)
            Is = Is + arriving * x.hosp

        occupancy = H.sum(axis=1) / np.maximum(x.beds, 1e-12)
        switch_on = (x.adaptive > 0.5) & ~adaptive_on & (occupancy >= x.adaptive_on)
        switch_off = adaptive_on & (occupancy <= x.adaptive_off) & (day - adaptive_since >= x.adaptive_min_days)
        adaptive_on = (adaptive_on | switch_on) & ~switch_off
        adaptive_since = np.where(switch_on, day, adaptive_since)
        stringency = np.where(adaptive_on, np.maximum(x.stringency[:, day], x.adaptive_level), x.stringency[:, day])

        variant = day >= x.variant_day
        escape_now = variant & ~escaped
        if escape_now.any():
            moved_r = R * (x.variant_escape * escape_now)[:, None]
            moved_v = V * (x.variant_escape * escape_now)[:, None]
            R = R - moved_r
            V = V - moved_v
            S = S + moved_r + moved_v
            escaped = escaped | escape_now
        transmission = np.where(variant, x.variant_transmission, 1.0)
        severity = np.where(variant, x.variant_severity, 1.0)[:, None]
        season = 1.0 + x.seasonality * np.cos(2 * np.pi * (day - x.season_peak_day) / 365.0)
        fatigue = np.clip((day - x.fatigue_start) / np.maximum(x.fatigue_end - x.fatigue_start, 1e-12), 0.0, 1.0)
        npi_coef = x.npi_coef + (x.npi_coef_late - x.npi_coef) * fatigue
        awareness = 1.0 / (1.0 + (recent_deaths_pm / x.awareness_deaths_pm) ** x.awareness_power)
        beta = beta0 * season * np.exp(npi_coef * stringency) * (1 - x.isolation) * transmission * awareness
        treated = day >= x.treatment_day
        care = np.where(treated, 1 - x.treatment_effect, 1.0)[:, None]
        vaccinating = day >= x.vaccine_day

        alive = (S + V + Em + Es + Im + Is + H + R).sum(axis=1)
        out["rt"][:, day] = beta * x.infectious_days * (S.sum(axis=1) + (1 - x.ve_infection) * V.sum(axis=1)) / alive
        out["stringency"][:, day] = stringency

        new_inf = np.zeros(L)
        new_adm = np.zeros(L)
        new_dead = np.zeros(L)
        for _ in range(SUBSTEPS):
            alive = (S + V + Em + Es + Im + Is + H + R).sum(axis=1)
            force = beta * (Im + Is).sum(axis=1) / np.maximum(alive, 1e-12)  # (L,)
            inf_s = S * _p(force, dt)[:, None]
            inf_v = V * _p(force * (1 - x.ve_infection), dt)[:, None]
            severe_share = np.minimum(x.hosp * severity, 1.0)
            to_es = inf_s * severe_share + inf_v * np.minimum(severe_share * vaccine_severity[:, None], 1.0)
            to_em = inf_s + inf_v - to_es

            onset_m = Em * p_latent
            onset_s = Es * p_latent
            recover_m = Im * p_infectious
            admit = Is * p_infectious

            icu_ratio = np.maximum(
                x.icu_share * H.sum(axis=1) / np.maximum(x.icu_beds, 1e-12),
                H.sum(axis=1) / np.maximum(x.beds, 1e-12),
            )
            strain = 1 + x.icu_death_share * (overload_multiplier(icu_ratio, x.unmet_multiplier) - 1)
            discharge = H * p_discharge
            die = discharge * np.minimum(fatality * strain[:, None] * care, 1.0)

            wane_r = R * p_wane
            wane_v = V * p_vaccine_wane

            S = S - inf_s + wane_r + wane_v
            V = V - inf_v - wane_v
            Em = Em + to_em - onset_m
            Es = Es + to_es - onset_s
            Im = Im + onset_m - recover_m
            Is = Is + onset_s - admit
            H = H + admit - discharge
            R = R + recover_m + (discharge - die) - wane_r
            D = D + die

            # Vaccination: doses go to people who accept and haven't been vaccinated yet. Only S
            # and R are reachable; the S share of a band's doses moves S to V.
            capacity = np.where(vaccinating, x.vaccine_capacity * x.population * dt, 0.0)
            remaining = np.maximum(eligible_cap - vaccinated, 0.0)
            doses = _allocate(capacity, remaining, oldest_first)
            reachable = S + R
            to_v = doses * np.where(reachable > 0, S / np.maximum(reachable, 1e-12), 0.0)
            to_v = np.minimum(to_v, S)
            S = S - to_v
            V = V + to_v
            vaccinated = vaccinated + doses

            new_inf += (inf_s + inf_v).sum(axis=1)
            new_adm += admit.sum(axis=1)
            new_dead += die.sum(axis=1)

        recent_deaths_pm = recent_deaths_pm + (new_dead * x.death_reporting * 1e6 / x.population - recent_deaths_pm) / 7.0

        out["infections"][:, day] = new_inf
        out["admissions"][:, day] = new_adm
        out["deaths"][:, day] = new_dead
        out["reported_deaths"][:, day] = new_dead * x.death_reporting
        out["reported_cases"][:, day] = new_inf * x.case_detection
        out["hospital"][:, day] = H.sum(axis=1)
        out["icu"][:, day] = x.icu_share * H.sum(axis=1)
        out["vaccinated"][:, day] = vaccinated.sum(axis=1)
        out["susceptible"][:, day] = S.sum(axis=1)
        out["infected"][:, day] = (Em + Es + Im + Is).sum(axis=1)
        out["immune"][:, day] = (R + V).sum(axis=1)
        out["dead"][:, day] = D.sum(axis=1)

    return EngineOutputs(**out, deaths_by_age=D)


def _allocate(capacity: np.ndarray, remaining: np.ndarray, oldest_first: np.ndarray) -> np.ndarray:
    """Split each lane's doses across bands: oldest band first, or in proportion to who's left."""
    total = remaining.sum(axis=1)
    proportional = remaining * np.where(total > 0, np.minimum(capacity / np.maximum(total, 1e-12), 1.0), 0.0)[:, None]
    ordered = np.zeros_like(remaining)
    left = capacity.copy()
    for band in range(N_BANDS - 1, -1, -1):
        take = np.minimum(left, remaining[:, band])
        ordered[:, band] = take
        left = left - take
    return np.where(oldest_first[:, None], ordered, proportional)
