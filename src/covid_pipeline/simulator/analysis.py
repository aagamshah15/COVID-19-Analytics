"""Scenario analysis on the reference engine: Monte Carlo ranges and Sobol sensitivity.

The browser runs 200 draws and a one-at-a-time sensitivity chart. This module is the heavier
version the cloud API serves: thousands of draws, and variance-based (Sobol) indices that also
capture how the uncertain inputs interact. NumPy and SciPy only.

A ``ScenarioRun`` is the same JSON the browser's engine consumes (``montecarlo.ts``): a place, a
pathogen, a response, a variant, the learned constants, where each learned place value came from,
and the spreads to draw from. ``null`` in that JSON means infinity ("never", "lifelong", "off"),
except ``response.vaccine_day`` (the pathogen's default), ``pathogen.seasonality`` (the amplitude
learned for SARS-CoV-2) and ``place.latitude`` (no seasonality).

Uncertain inputs are perturbed exactly as the browser does: log-normal or logit-normal jitter with
a spread that depends on the value's source ("user" values are fixed). Draws are expressed as
standard normal z-scores, one per factor, so Monte Carlo and Sobol share one mapping.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields, replace

import numpy as np
from scipy import stats

from .engine import EngineInputs, EngineOutputs, run
from .scenario import ModelConstants, Pathogen, Place, Response, Segment, Variant, build_inputs

QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)
CHUNK = 400  # lanes per engine call: a three-year run then needs roughly 90 MB of working memory
SUMMARY_KEYS = (
    "deaths",
    "reported_deaths",
    "infections",
    "attack_rate",
    "peak_hospital",
    "peak_hospital_day",
    "days_over_capacity",
    "peak_deaths_day",
    "vaccinated",
)
WEEKLY_SERIES = {"deaths": True, "hospital": False, "infections": True}  # name -> is a flow (summed over the week)

# The learned place values, the spread that applies to each and the scale it is drawn on.
PLACE_FACTORS = {
    "transmission": ("log_transmission_sd", "log"),
    "severity": ("log_severity_sd", "log"),
    "awareness": ("log_awareness_country_sd", "log"),
    "death_reporting": ("logit_reporting_sd", "logit"),
    "vaccine_acceptance": ("logit_vaccine_acceptance_sd", "logit"),
    "vaccine_capacity": ("log_vaccine_capacity_sd", "log"),
}
SOURCE_KEYS = {"death_reporting": "reporting"}  # place field -> key in ``sources``, where they differ
# A draw never leaves the range the engine is defined for, however wide a spread it is given.
# These are the upper bounds the API puts on the same values in a request.
CEILINGS = {"r0": 50.0, "ifr": 1.0, "transmission": 1000.0, "severity": 1000.0, "awareness": 1000.0, "vaccine_capacity": 1.0}
MAX_NPI_COEF = 1.0
MAX_AWARENESS_DEATHS_PM = 1e9
FACTOR_LABELS = {
    "r0": "How contagious it is",
    "ifr": "How deadly it is",
    "transmission": "How easily it spreads here",
    "severity": "How badly older people are hit",
    "awareness": "How careful people here are",
    "death_reporting": "Share of deaths reported",
    "vaccine_acceptance": "How many take the vaccine",
    "vaccine_capacity": "How fast vaccines are given",
    "npi": "How well restrictions work",
    "awareness_threshold": "How careful people are in general",
    "seasonality": "How strong the seasons are",
}


@dataclass
class ScenarioRun:
    place: Place
    pathogen: Pathogen
    response: Response
    variant: Variant
    constants: ModelConstants
    days: int
    sources: dict[str, str] = field(default_factory=dict)
    uncertainty: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> ScenarioRun:
        """Build from the shared JSON, restoring infinity where it carried null."""

        def inf(values: dict, *names: str) -> dict:
            return values | {n: math.inf for n in names if values.get(n) is None}

        response = inf(dict(data["response"]), "treatment_day")
        response["segments"] = [Segment(int(g["start_day"]), int(g["end_day"]), float(g["level"])) for g in response.get("segments", [])]
        response["start_month"] = int(response.get("start_month", 1))
        return cls(
            place=Place(**data["place"]),
            pathogen=Pathogen(**inf(dict(data["pathogen"]), "immunity_days", "vaccine_day", "vaccine_immunity_days")),
            response=Response(**response),
            variant=Variant(**inf(dict(data.get("variant") or {}), "day")),
            constants=ModelConstants(**inf(dict(data["constants"]), "awareness_deaths_pm")),
            days=int(data["days"]),
            sources=dict(data.get("sources") or {}),
            uncertainty=dict(data.get("uncertainty") or {}),
        )

    def capacity(self) -> float:
        """Hospital beds available to the epidemic."""
        return self.place.beds_per_thousand * self.place.population / 1000 * self.place.bed_availability * (1 + self.response.surge)

    def inputs(self) -> EngineInputs:
        return build_inputs(self.place, self.pathogen, self.response, self.days, self.constants, self.variant)


def without_response(s: ScenarioRun) -> ScenarioRun:
    """The same place and disease with no policy response (people still react to deaths)."""
    return replace(s, response=Response(vaccine=False, start_month=s.response.start_month, seed_per_million=s.response.seed_per_million))


# --------------------------------------------------------------------------- uncertain inputs


def _spread(source: str | None, sd) -> float:
    """The spread for a value from this source: none if the visitor set it, wider if it was predicted."""
    if source == "user" or sd is None:
        return 0.0
    if isinstance(sd, (int, float)):
        return float(sd)
    if source == "predicted":
        return float(sd.get("predicted", 0.0))
    return float(sd.get("calibrated", sd.get("observed", sd.get("predicted", 0.0))))


def factors(s: ScenarioRun, output: str | None = None) -> dict[str, float]:
    """Uncertain inputs that can change this scenario's ``output`` (any output if None), with the spread of each."""
    u = s.uncertainty
    out = {"r0": _spread(None, u.get("log_r0_sd")), "ifr": _spread(None, u.get("log_ifr_sd"))}
    for name, (sd_key, _) in PLACE_FACTORS.items():
        out[name] = _spread(s.sources.get(SOURCE_KEYS.get(name, name)), u.get(sd_key))
    out["npi"] = _spread(None, u.get("npi_coef_sd"))
    out["awareness_threshold"] = _spread(None, u.get("log_awareness_sd"))
    out["seasonality"] = _spread(None, u.get("seasonality_sd"))

    aware = s.response.awareness and math.isfinite(s.constants.awareness_deaths_pm)
    seasonal = s.pathogen.seasonality is None and s.place.latitude is not None
    relevant = {
        "npi": bool(s.response.segments) or s.response.adaptive,
        "awareness": aware,
        "awareness_threshold": aware,
        # Reporting changes the reported count; it changes anything else only through people's caution.
        "death_reporting": aware or output in (None, "reported_deaths"),
        "vaccine_acceptance": s.response.vaccine,
        "vaccine_capacity": s.response.vaccine,
        "seasonality": seasonal,
    }
    return {k: sd for k, sd in out.items() if sd > 0 and relevant.get(k, True)}


def _exp(x: float) -> float:
    """exp that saturates instead of overflowing."""
    return math.exp(min(x, 700.0))


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def perturbed(s: ScenarioRun, z: dict[str, float], spreads: dict[str, float]) -> ScenarioRun:
    """One draw: every factor moved ``z`` standard deviations on its own scale."""
    place = {}
    for name, (_, scale) in PLACE_FACTORS.items():
        if name not in z:
            continue
        value, step = getattr(s.place, name), z[name] * spreads[name]
        if scale == "log":
            place[name] = min(value * _exp(step), CEILINGS[name])
        else:
            place[name] = 1 / (1 + _exp(-(_logit(value) + step)))
    constants = {}
    if "npi" in z:
        constants["npi_coef"] = min(max(s.constants.npi_coef + z["npi"] * spreads["npi"], -MAX_NPI_COEF), MAX_NPI_COEF)
    if "awareness_threshold" in z:
        step = z["awareness_threshold"] * spreads["awareness_threshold"]
        constants["awareness_deaths_pm"] = min(s.constants.awareness_deaths_pm * _exp(step), MAX_AWARENESS_DEATHS_PM)
    if "seasonality" in z:
        constants["covid_seasonality"] = min(max(s.constants.covid_seasonality + z["seasonality"] * spreads["seasonality"], 0.0), 1.0)
    pathogen = {k: min(getattr(s.pathogen, k) * _exp(z[k] * spreads[k]), CEILINGS[k]) for k in ("r0", "ifr") if k in z}
    return replace(
        s,
        place=replace(s.place, **place),
        constants=replace(s.constants, **constants),
        pathogen=replace(s.pathogen, **pathogen),
    )


def _stack(inputs: list[EngineInputs]) -> EngineInputs:
    return EngineInputs(**{f.name: np.concatenate([getattr(x, f.name) for x in inputs]) for f in fields(EngineInputs)})


# --------------------------------------------------------------------------- running draws


def summarise(out: EngineOutputs, population: float, capacity: np.ndarray | float) -> dict[str, np.ndarray]:
    """Headline numbers per lane (the browser's ``summarise``)."""
    infections = out.infections.sum(axis=1)
    return {
        "deaths": out.deaths.sum(axis=1),
        "reported_deaths": out.reported_deaths.sum(axis=1),
        "infections": infections,
        "attack_rate": infections / population,
        "peak_hospital": out.hospital.max(axis=1),
        "peak_hospital_day": out.hospital.argmax(axis=1).astype(float),
        "days_over_capacity": (out.hospital > np.reshape(capacity, (-1, 1))).sum(axis=1).astype(float),
        "peak_deaths_day": out.deaths.argmax(axis=1).astype(float),
        "vaccinated": out.vaccinated[:, -1],
    }


def _weekly(values: np.ndarray, flow: bool) -> np.ndarray:
    """(lanes, days) -> (lanes, weeks): weekly totals for flows, the week's last day for stocks."""
    days = values.shape[1]
    starts = np.arange(0, days, 7)
    if flow:
        return np.add.reduceat(values, starts, axis=1)
    return values[:, np.minimum(starts + 6, days - 1)]


def _run_draws(
    s: ScenarioRun, z: np.ndarray, names: list[str], spreads: dict[str, float], weekly: bool
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Run one scenario per row of ``z`` (draws x factors), in chunks. Returns summaries and weekly series."""
    summaries: dict[str, list[np.ndarray]] = {k: [] for k in SUMMARY_KEYS}
    series: dict[str, list[np.ndarray]] = {k: [] for k in WEEKLY_SERIES} if weekly else {}
    for start in range(0, len(z), CHUNK):
        draws = [perturbed(s, dict(zip(names, row, strict=True)), spreads) for row in z[start : start + CHUNK]]
        out = run(_stack([d.inputs() for d in draws]), s.days)
        for k, v in summarise(out, s.place.population, np.array([d.capacity() for d in draws])).items():
            summaries[k].append(v)
        for k in series:
            series[k].append(_weekly(getattr(out, k), WEEKLY_SERIES[k]))
    return {k: np.concatenate(v) for k, v in summaries.items()}, {k: np.concatenate(v) for k, v in series.items()}


def central(s: ScenarioRun, capacity: float | None = None) -> tuple[EngineOutputs, dict[str, float]]:
    """The run with every input at its central value, and its headline numbers.

    ``capacity`` overrides the beds that "over capacity" is counted against (to compare a
    counterfactual with the scenario it came from).
    """
    out = run(s.inputs(), s.days)
    beds = s.capacity() if capacity is None else capacity
    return out, {k: float(v[0]) for k, v in summarise(out, s.place.population, beds).items()}


def monte_carlo(s: ScenarioRun, draws: int, seed: int = 1) -> dict:
    """Quantiles of the headline numbers and of the weekly series across ``draws`` random draws."""
    spreads = factors(s)
    names = list(spreads)
    z = np.random.default_rng(seed).standard_normal((draws, len(names)))
    summaries, series = _run_draws(s, z, names, spreads, weekly=True)
    return {
        "draws": draws,
        "quantile_levels": list(QUANTILES),
        "quantiles": {k: np.quantile(v, QUANTILES).tolist() for k, v in summaries.items()},
        "weekly": {k: np.quantile(v, QUANTILES, axis=0).tolist() for k, v in series.items()},
    }


def sobol_indices(func, d: int, n: int, seed: int = 1, confidence: float = 0.9, resamples: int = 200) -> dict[str, np.ndarray]:
    """First- and total-order Sobol indices of ``func`` for ``d`` independent standard normal inputs.

    ``func`` maps an array of inputs, one row per run, to one outcome per run. The design is
    Saltelli's (2010): two independent samples A and B of ``n`` rows from a scrambled Sobol
    sequence and, for each input, A with that input's column taken from B, ``n * (d + 2)`` runs
    in all. First-order indices use the Saltelli (2010) estimator, total-order ones Jansen (1999).
    Intervals are bootstrap percentiles over the ``n`` rows.

    ``scipy.stats.sobol_indices`` computes the same estimates, but its bootstrap can't be seeded
    and it fails with a single input; here the same seed always gives the same answer.
    """
    if n < 2 or n & (n - 1):
        raise ValueError("n must be a power of two")
    rng = np.random.default_rng(seed)
    uniform = stats.qmc.Sobol(d=2 * d, rng=rng).random(n)
    z = stats.norm.ppf(np.clip(uniform, 1e-12, 1 - 1e-12))
    a, b = z[:, :d], z[:, d:]
    swapped = [np.where(np.arange(d) == i, b, a) for i in range(d)]
    y = np.asarray(func(np.concatenate([a, b, *swapped])), dtype=float).reshape(d + 2, n)
    y = y - y[:2].mean()

    def estimate(rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Indices from the base rows ``rows``: (..., n) row numbers -> (..., d) indices."""
        f_a, f_b, f_ab = y[0][rows], y[1][rows], np.moveaxis(y[2:][:, rows], 0, -2)
        variance = np.concatenate([f_a, f_b], axis=-1).var(axis=-1)[..., None]
        with np.errstate(divide="ignore", invalid="ignore"):
            first = (f_b[..., None, :] * (f_ab - f_a[..., None, :])).mean(axis=-1) / variance
            total = 0.5 * ((f_a[..., None, :] - f_ab) ** 2).mean(axis=-1) / variance
        return first, total

    first, total = estimate(np.arange(n))
    boot_first, boot_total = estimate(rng.integers(0, n, size=(resamples, n)))
    tails = [(1 - confidence) / 2, (1 + confidence) / 2]
    return {
        "first": first,
        "total": total,
        "first_interval": np.quantile(boot_first, tails, axis=0).T,
        "total_interval": np.quantile(boot_total, tails, axis=0).T,
    }


def sobol(s: ScenarioRun, n: int = 256, seed: int = 1, output: str = "deaths", confidence: float = 0.9) -> dict:
    """Sobol indices of ``output`` with respect to each uncertain input of a scenario.

    The first-order index is the share of the outcome's variance an input explains on its own; the
    total-order index adds every interaction it takes part in.
    """
    spreads = factors(s, output)
    names = list(spreads)
    if not names:
        return {"output": output, "n": n, "evaluations": 0, "confidence": confidence, "factors": []}
    result = sobol_indices(lambda z: _run_draws(s, z, names, spreads, weekly=False)[0][output], len(names), n, seed, confidence)

    def share(v) -> float:
        # An outcome that never varies (an outbreak that can't start) has no variance to share out.
        return float(np.clip(np.nan_to_num(v), 0.0, 1.0))

    rows = [
        {
            "key": name,
            "label": FACTOR_LABELS[name],
            "first": share(result["first"][i]),
            "first_interval": [share(v) for v in result["first_interval"][i]],
            "total": share(result["total"][i]),
            "total_interval": [share(v) for v in result["total_interval"][i]],
        }
        for i, name in enumerate(names)
    ]
    rows.sort(key=lambda r: -r["total"])
    return {"output": output, "n": n, "evaluations": n * (len(names) + 2), "confidence": confidence, "factors": rows}
