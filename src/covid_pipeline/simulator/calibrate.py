"""M2: calibrate the engine to each country's 2020 epidemic, and validate it out of sample.

For every country with population >= 1M, an age structure, a stringency series and at least 50
reported deaths in 2020, the engine replays 2020 with the ancestral SARS-CoV-2 preset, the
country's observed lockdown stringency, its latitude (seasonality) and its death-reporting share
(which drives awareness). Three country parameters are fitted:

* ``transmission``: multiplier on R0 (prior: log-normal, median 1, sd 0.5)
* ``severity``: multiplier on IFR in the 60+ bands (prior: log-normal, median 1, sd 0.35)
* ``seed_day``: when the first infections arrived (Jan 11 - Mar 21)
* ``awareness``: multiplier on the shared awareness threshold (prior: log-normal, median 1, sd 1).
  People in some countries tolerated far higher death rates before cutting contacts; with one
  threshold for everyone, the fit inflated those countries' severity to compensate.

against weekly deaths from March to December, scaled up by the country's death-reporting share
(M5). Three parameters are shared by every country and chosen by profile likelihood over a grid:

* the lockdown coefficient (estimating the policy effect from deaths rather than case-based Rt
  follows Flaxman et al. 2020);
* the awareness threshold: reported deaths per million per day at which people halve their
  contacts (Weitz et al. 2020);
* the seasonal amplitude at latitudes of 40 degrees or more (its timing comes from M1).

For every combination, every country is refitted and the total misfit compared (stage 1, with a
common awareness threshold). Each country is then refitted with its own awareness multiplier at the
chosen shared parameters (stage 2).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .engine import run
from .features import AGE_MEAN_COLUMNS, AGE_SHARE_COLUMNS
from .models import MIN_POPULATION, adherence, fit_ridge, predict_linear
from .scenario import PRESETS, ModelConstants, Place, Response, build_inputs

log = logging.getLogger(__name__)

YEAR_START = pd.Timestamp("2020-01-01")
DAYS = 366
TARGET_FROM = pd.Timestamp("2020-03-01")
TARGET_TO = pd.Timestamp("2020-12-31")
MIN_DEATHS = 50

TAU_GRID = np.geomspace(0.35, 1.8, 10)
SEED_GRID = np.arange(10, 81, 10, dtype=float)
LOG_S_GRID = np.linspace(np.log(0.15), np.log(6.0), 31)
# Shared-parameter grids. The misfit rises steeply outside them (see the surface in
# reports/simulator_metrics.json); an optimum on an edge is logged as a warning.
NPI_GRID = np.array([-0.004, -0.006, -0.008, -0.010, -0.012])
AWARENESS_GRID = np.array([0.5, 1.0, 2.0, 4.0, 8.0, np.inf])
SEASON_GRID = np.array([0.0, 0.2, 0.35, 0.5])
SIGMA_Y = 0.5  # sd of log1p(weekly deaths per million) around the model
PRIOR_SD_TAU = 0.5
PRIOR_SD_AWARE = 1.0
AWARE_MULT_GRID = np.array([0.25, 0.5, 1.0, 2.0, 4.0, 8.0])
# Deaths alone can't separate "many infections, low fatality" from "few infections, high fatality":
# with awareness, behaviour sets the death level whatever the IFR. The Levin age curve comes from
# seroprevalence studies, the best anchor on infections, so severity stays close to it unless a
# country's deaths strongly demand otherwise. (A looser prior, sd 0.7, gave the US an IFR of 2.6%.)
PRIOR_SD_S = 0.35
CHUNK = 2500


@dataclass(frozen=True)
class Shared:
    """Parameters shared by every country."""

    npi_coef: float
    awareness: float  # inf = off
    seasonality: float
    season_peak_day_north: float = 8.0  # from M1, not calibrated

    def constants(self) -> ModelConstants:
        return ModelConstants(
            npi_coef=self.npi_coef,
            awareness_deaths_pm=self.awareness,
            covid_seasonality=self.seasonality,
            season_peak_day_north=self.season_peak_day_north,
        )


@dataclass
class Country:
    iso: str
    place: Place
    stringency: np.ndarray  # (DAYS,)
    week_days: np.ndarray  # (weeks, 7) day indices for each target week
    observed: np.ndarray  # (weeks,) estimated true deaths per week (NaN = not reported)
    continent: str


def place_from_profile(
    row: pd.Series,
    npi: dict | None = None,
    beds_median: float = 2.5,
    uhc_median: float = 60.0,
    reporting: float = 1.0,
) -> Place:
    beds = row.get("hospital_beds_per_thousand")
    uhc = row.get("uhc_index")
    latitude = row.get("latitude")
    return Place(
        population=float(row["population"]),
        age_shares=[float(row[c]) for c in AGE_SHARE_COLUMNS],
        age_means=[float(row[c]) for c in AGE_MEAN_COLUMNS],
        beds_per_thousand=float(beds) if pd.notna(beds) else beds_median,
        latitude=float(latitude) if pd.notna(latitude) else None,
        access=(float(uhc) if pd.notna(uhc) else uhc_median) / 100,
        adherence=float(adherence(pd.Series([row["share_65_plus"]]), npi).iloc[0]) if npi else 1.0,
        death_reporting=reporting,
    )


def calibration_set(profile: pd.DataFrame, sim_weekly: pd.DataFrame, reporting: pd.Series, npi: dict) -> list[Country]:
    """Countries to calibrate, with their 2020 stringency path and reporting-adjusted deaths."""
    eligible = profile[(profile["population"] >= MIN_POPULATION) & profile[AGE_SHARE_COLUMNS].notna().all(axis=1)]
    beds_median = float(eligible["hospital_beds_per_thousand"].median())
    uhc_median = float(eligible["uhc_index"].median())
    weekly = sim_weekly[sim_weekly["week_end"].between(YEAR_START, TARGET_TO + pd.Timedelta(days=6))]
    daily_index = pd.date_range(YEAR_START, periods=DAYS)
    countries = []
    for row in eligible.itertuples(index=False):
        row = pd.Series(row._asdict())
        frame = weekly[weekly["iso_code"] == row["iso_code"]].set_index("week_end").sort_index()
        if frame["stringency_index"].notna().sum() < 26 or frame["new_deaths"].sum() < MIN_DEATHS:
            continue
        # Weekly stringency, held for each day of its week; 0 before the index starts.
        week_of_day = daily_index + pd.to_timedelta((6 - daily_index.weekday) % 7, unit="D")
        stringency = frame["stringency_index"].reindex(week_of_day).ffill().fillna(0)
        target = frame[(frame.index >= TARGET_FROM) & (frame.index <= TARGET_TO + pd.Timedelta(days=6))]
        target = target[target.index - pd.Timedelta(days=6) >= YEAR_START]
        week_days = np.array([np.arange(7) + (w - pd.Timedelta(days=6) - YEAR_START).days for w in target.index])
        keep = week_days.max(axis=1) < DAYS
        share = float(reporting.get(row["iso_code"], np.nan))
        observed = target["new_deaths"].to_numpy(dtype=float)[keep] / share
        countries.append(
            Country(
                iso=row["iso_code"],
                place=place_from_profile(row, npi, beds_median, uhc_median, share),
                stringency=stringency.to_numpy(dtype=float),
                week_days=week_days[keep],
                observed=observed,
                continent=str(row["continent"]),
            )
        )
    log.info("Calibrating %s countries", len(countries))
    return countries


# --------------------------------------------------------------------------- simulation + fit


def _stack(inputs: list) -> object:
    first = inputs[0]
    stacked = {f: np.concatenate([getattr(x, f) for x in inputs], axis=0) for f in first.__dataclass_fields__}
    return type(first)(**stacked)


Lane = tuple[int, float, float, float, float]  # country index, transmission, severity, seed day, awareness


def _simulate(countries: list[Country], lanes: list[Lane], shared: Shared) -> list[np.ndarray]:
    """Run lanes in chunks; return each lane's weekly deaths over the target weeks."""
    constants = shared.constants()
    response = Response(vaccine=False, fatigue=False, start_month=1)
    pathogen = PRESETS["covid_ancestral"]
    results: list[np.ndarray] = []
    for start in range(0, len(lanes), CHUNK):
        chunk = lanes[start : start + CHUNK]
        inputs = [
            build_inputs(
                replace(countries[i].place, transmission=tau, severity=s, awareness=aware),
                pathogen,
                replace(response, border_delay_days=seed),
                DAYS,
                constants,
                stringency=countries[i].stringency,
            )
            for i, tau, s, seed, aware in chunk
        ]
        deaths = run(_stack(inputs), DAYS).deaths
        for j, (i, *_rest) in enumerate(chunk):
            results.append(deaths[j, countries[i].week_days].sum(axis=1))
    return results


def _nll(model_weekly: np.ndarray, country: Country, log_tau, log_s, log_aware=0.0) -> np.ndarray:
    """Negative log posterior, broadcasting over leading axes of ``model_weekly`` (..., weeks)."""
    per_million = 1e6 / country.place.population
    ok = np.isfinite(country.observed)
    y_obs = np.log1p(country.observed[ok] * per_million)
    y_mod = np.log1p(model_weekly[..., ok] * per_million)
    misfit = ((y_mod - y_obs) ** 2).sum(axis=-1) / (2 * SIGMA_Y**2)
    priors = np.square(log_tau) / (2 * PRIOR_SD_TAU**2) + np.square(log_s) / (2 * PRIOR_SD_S**2)
    return misfit + priors + np.square(log_aware) / (2 * PRIOR_SD_AWARE**2)


def _coarse(countries: list[Country], shared: Shared, tau_grid=TAU_GRID, seed_grid=SEED_GRID, aware_grid=(1.0,)) -> pd.DataFrame:
    """Grid over transmission x seed day (x awareness) at severity 1, with severity profiled analytically.

    Severity scales deaths in the 60+ bands, the large majority of COVID deaths, so scaling all
    deaths by it is a close approximation for the coarse search; ``_refine`` re-simulates with
    severity applied properly.
    """
    lanes = [(i, tau, 1.0, seed, a) for i in range(len(countries)) for tau in tau_grid for seed in seed_grid for a in aware_grid]
    rows = []
    for (i, tau, _, seed, a), weekly in zip(lanes, _simulate(countries, lanes, shared), strict=True):
        nll = _nll(np.exp(LOG_S_GRID)[:, None] * weekly[None, :], countries[i], np.log(tau), LOG_S_GRID, np.log(a))
        k = int(np.argmin(nll))
        rows.append({"i": i, "tau": tau, "seed_day": seed, "awareness": a, "severity": float(np.exp(LOG_S_GRID[k])), "nll": float(nll[k])})
    fits = pd.DataFrame(rows)
    return fits.loc[fits.groupby("i")["nll"].idxmin()].set_index("i").sort_index()


def _refine(countries: list[Country], best: pd.DataFrame, shared: Shared, rounds: int = 2, fit_awareness: bool = False) -> pd.DataFrame:
    """Local grid around each country's best point, re-simulating with severity applied properly."""
    aware_steps = (0.7, 1.0, 1.4) if fit_awareness else (1.0,)
    for _ in range(rounds):
        lanes = [
            (i, row.tau * ft, row.severity * fs, float(np.clip(row.seed_day + ds, 1, 120)), row.awareness * fa)
            for i, row in best.iterrows()
            for ft in (0.9, 1.0, 1.1)
            for fs in (0.75, 1.0, 1.33)
            for ds in (-5.0, 0.0, 5.0)
            for fa in aware_steps
        ]
        rows = []
        for (i, tau, s, seed, a), weekly in zip(lanes, _simulate(countries, lanes, shared), strict=True):
            nll = float(_nll(weekly, countries[i], np.log(tau), np.log(s), np.log(a)))
            rows.append({"i": i, "tau": tau, "severity": s, "seed_day": seed, "awareness": a, "nll": nll, "weekly": weekly})
        fits = pd.DataFrame(rows)
        best = fits.loc[fits.groupby("i")["nll"].idxmin()].set_index("i").sort_index()
    return best


def fit_countries(
    countries: list[Country], shared: Shared, tau_grid=TAU_GRID, seed_grid=SEED_GRID, fit_awareness: bool = True
) -> pd.DataFrame:
    """Every country's best parameters (and fitted weekly deaths) for given shared parameters."""
    aware_grid = AWARE_MULT_GRID if fit_awareness and np.isfinite(shared.awareness) else (1.0,)
    coarse = _coarse(countries, shared, tau_grid, seed_grid, aware_grid)
    best = _refine(countries, coarse, shared, fit_awareness=len(aware_grid) > 1)
    fitted = pd.DataFrame(
        {
            "iso_code": [countries[i].iso for i in best.index],
            "continent": [countries[i].continent for i in best.index],
            "transmission": best["tau"].to_numpy(),
            "severity": best["severity"].to_numpy(),
            "awareness": best["awareness"].to_numpy(),
            "seed_day": best["seed_day"].to_numpy(),
            "nll": best["nll"].to_numpy(),
            "weekly": list(best["weekly"]),
        }
    )
    fitted["fit_rmse_log"] = [
        float(np.sqrt(np.nanmean((np.log1p(w * 1e6 / c.place.population) - np.log1p(c.observed * 1e6 / c.place.population)) ** 2)))
        for c, w in zip(countries, fitted["weekly"], strict=True)
    ]
    return fitted


# --------------------------------------------------------------------------- shared parameters


@dataclass
class Grids:
    npi: np.ndarray = field(default_factory=lambda: NPI_GRID)
    awareness: np.ndarray = field(default_factory=lambda: AWARENESS_GRID)
    seasonality: np.ndarray = field(default_factory=lambda: SEASON_GRID)
    tau: np.ndarray = field(default_factory=lambda: TAU_GRID)
    seed: np.ndarray = field(default_factory=lambda: SEED_GRID)


def calibrate(
    countries: list[Country], grids: Grids | None = None, peak_day: float = 8.0, n_boot: int = 500, seed: int = 42
) -> tuple[pd.DataFrame, dict, Shared]:
    """Profile the shared parameters over their grid, then fit every country at the best point."""
    g = grids or Grids()
    shape = (len(g.npi), len(g.awareness), len(g.seasonality))
    per_country = np.zeros((*shape, len(countries)))
    for idx in np.ndindex(shape):
        point = Shared(float(g.npi[idx[0]]), float(g.awareness[idx[1]]), float(g.seasonality[idx[2]]), peak_day)
        per_country[idx] = _coarse(countries, point, g.tau, g.seed)["nll"].to_numpy()
        log.info(
            "npi %.3f, awareness %s, seasonality %.2f: misfit %.1f",
            *[point.npi_coef, point.awareness, point.seasonality],
            per_country[idx].sum(),
        )
    surface = per_country.sum(axis=-1)
    best = _surface_min(surface, g)
    edges = [
        name
        for name, k, n in zip(("npi", "awareness", "seasonality"), np.unravel_index(int(np.argmin(surface)), shape), shape, strict=True)
        if (k == 0 or k == n - 1) and not (name == "awareness" and k == n - 1)
    ]
    if edges:
        log.warning("Calibration optimum is on the edge of the grid for: %s", ", ".join(edges))

    # Bootstrap over countries: which point would a resampled set of countries choose?
    rng = np.random.default_rng(seed)
    boot = np.array(
        [_surface_min(per_country[..., rng.integers(0, len(countries), len(countries))].sum(axis=-1), g) for _ in range(n_boot)]
    )
    lo, hi = np.quantile(boot, 0.05, axis=0), np.quantile(boot, 0.95, axis=0)

    shared = Shared(best[0], best[1], best[2], peak_day)
    stage1 = fit_countries(countries, shared, g.tau, g.seed, fit_awareness=False)
    fitted = fit_countries(countries, shared, g.tau, g.seed, fit_awareness=True)
    summary = {
        "countries": len(countries),
        "npi_coef": round(shared.npi_coef, 5),
        "npi_coef_90ci": [round(float(lo[0]), 5), round(float(hi[0]), 5)],
        "reduction_at_80": round(1 - math.exp(80 * shared.npi_coef), 3),
        "reduction_at_80_90ci": [round(1 - math.exp(80 * float(hi[0])), 3), round(1 - math.exp(80 * float(lo[0])), 3)],
        "awareness_deaths_pm": _json_float(shared.awareness),
        "awareness_deaths_pm_90ci": [_json_float(lo[1]), _json_float(hi[1])],
        "seasonality": round(shared.seasonality, 4),
        "seasonality_90ci": [round(float(lo[2]), 4), round(float(hi[2]), 4)],
        "winter_to_summer_reduction": round(2 * shared.seasonality / (1 + shared.seasonality), 3),
        "season_peak_day_north": peak_day,
        "surface": {
            "npi_coef": np.asarray(g.npi).tolist(),
            "awareness_deaths_pm": [_json_float(a) for a in g.awareness],
            "seasonality": np.asarray(g.seasonality).tolist(),
            "total_misfit": surface.round(1).tolist(),
        },
        "median_fit_rmse_log": round(float(fitted["fit_rmse_log"].median()), 3),
        "transmission_range_p10_p90": [round(float(q), 3) for q in fitted["transmission"].quantile([0.1, 0.9])],
        "severity_range_p10_p90": [round(float(q), 3) for q in fitted["severity"].quantile([0.1, 0.9])],
        "awareness_multiplier_range_p10_p90": [round(float(q), 3) for q in fitted["awareness"].quantile([0.1, 0.9])],
        "stage1_median_fit_rmse_log": round(float(stage1["fit_rmse_log"].median()), 3),
    }
    return fitted, summary, shared


def _json_float(v: float) -> float | None:
    return None if not np.isfinite(v) else round(float(v), 4)


def _parabolic_min(x: np.ndarray, y: np.ndarray) -> float:
    """Minimum of a parabola through the lowest grid point and its neighbours (clamped to them)."""
    k = int(np.argmin(y))
    if k == 0 or k == len(x) - 1:
        return float(x[k])
    a, b, _ = np.polyfit(x[k - 1 : k + 2], y[k - 1 : k + 2], 2)
    lo, hi = sorted((x[k - 1], x[k + 1]))
    return float(np.clip(-b / (2 * a), lo, hi)) if a > 0 else float(x[k])


def _surface_min(surface: np.ndarray, g: Grids) -> tuple[float, float, float]:
    """Grid minimum, refined by a parabola along each axis through the minimum.

    Awareness is refined on a log scale over its finite values; an optimum at "off" stays there.
    """
    i, j, k = np.unravel_index(int(np.argmin(surface)), surface.shape)
    npi = _parabolic_min(np.asarray(g.npi), surface[:, j, k])
    season = _parabolic_min(np.asarray(g.seasonality), surface[i, j, :])
    finite = np.flatnonzero(np.isfinite(g.awareness))
    if j not in finite:
        return npi, math.inf, season
    aware = float(np.exp(_parabolic_min(np.log(np.asarray(g.awareness)[finite]), surface[i, finite, k])))
    return npi, aware, season


# --------------------------------------------------------------------------- validation


def hindcast(
    countries: list[Country], fitted: pd.DataFrame, Z: pd.DataFrame, shared: Shared, n_splits: int = 5, seed: int = 42
) -> tuple[dict, pd.DataFrame]:
    """Replay each country's 2020 from its features alone, trained without it, against baselines.

    Methods compared on weekly deaths per million (true scale), March-December 2020:
    * ``simulator``: M3 predicts transmission, severity and awareness from the country's features; seeding
      is the median fitted seed day of its continent; the engine replays its observed stringency.
    * ``simulator_no_features``: the same engine with every multiplier at 1, to show what
      the features add.
    * ``continent_average``: the mean observed curve of the other countries on its continent.
    * ``nearest_analog``: the observed curve of the most similar training country (feature space).
    """
    by_iso = {c.iso: c for c in countries}
    index = {c.iso: i for i, c in enumerate(countries)}
    fitted = fitted.set_index("iso_code")
    isos = np.array([c.iso for c in countries])
    folds = np.array_split(np.random.default_rng(seed).permutation(len(isos)), n_splits)
    rows = []
    for fold in folds:
        test = isos[fold]
        train = np.setdiff1d(isos, test)
        tau_model, _ = fit_ridge(Z.loc[train], np.log(fitted.loc[train, "transmission"]), "transmission", n_splits=3)
        sev_model, _ = fit_ridge(Z.loc[train], np.log(fitted.loc[train, "severity"]), "severity", n_splits=3)
        aware_model, _ = fit_ridge(Z.loc[train], np.log(fitted.loc[train, "awareness"]), "awareness", n_splits=3)
        seed_by_continent = fitted.loc[train].groupby("continent")["seed_day"].median()
        tau_hat = np.exp(predict_linear(tau_model, Z.loc[test]))
        sev_hat = np.exp(predict_linear(sev_model, Z.loc[test]))
        aware_hat = np.exp(predict_linear(aware_model, Z.loc[test]))
        lanes, null_lanes = [], []
        for iso in test:
            seed_day = float(seed_by_continent.get(by_iso[iso].continent, fitted.loc[train, "seed_day"].median()))
            lanes.append((index[iso], float(tau_hat[iso]), float(sev_hat[iso]), seed_day, float(aware_hat[iso])))
            null_lanes.append((index[iso], 1.0, 1.0, seed_day, 1.0))
        sim = _simulate(countries, lanes, shared)
        null = _simulate(countries, null_lanes, shared)
        for k, iso in enumerate(test):
            c = by_iso[iso]
            pm = 1e6 / c.place.population
            observed = c.observed * pm
            peers = [by_iso[t] for t in train if by_iso[t].continent == c.continent] or [by_iso[t] for t in train]
            continent_curve = np.nanmean([_align(p.observed * 1e6 / p.place.population, len(observed)) for p in peers], axis=0)
            nearest = min(train, key=lambda t: float(((Z.loc[t] - Z.loc[iso]) ** 2).sum()))
            analog_curve = _align(by_iso[nearest].observed * 1e6 / by_iso[nearest].place.population, len(observed))
            for method, curve in (
                ("simulator", sim[k] * pm),
                ("simulator_no_features", null[k] * pm),
                ("continent_average", continent_curve),
                ("nearest_analog", analog_curve),
            ):
                rows.append({"iso_code": iso, "method": method, "observed": observed, "predicted": curve})
    detail = pd.DataFrame(rows)
    return _score(detail), detail


def temporal_holdout(
    countries: list[Country], shared: Shared, split: str = "2020-07-31", tau_grid=TAU_GRID, seed_grid=SEED_GRID
) -> tuple[dict, pd.DataFrame]:
    """Does knowing the lockdown path help predict what comes next?

    Each country is calibrated on weeks up to ``split`` only, then the engine replays the rest of
    2020 with the country's observed stringency. Scored on the held-out weeks against:
    * ``persistence``: every later week equals the mean of the last four observed weeks;
    * ablations of the simulator without its lockdown effect, awareness or seasonality.
    """
    cutoff = (pd.Timestamp(split) - YEAR_START).days
    held_out = [c.week_days.min(axis=1) > cutoff for c in countries]
    truncated = [replace(c, observed=np.where(late, np.nan, c.observed)) for c, late in zip(countries, held_out, strict=True)]
    variants = {
        "simulator": shared,
        "no_policy_effect": replace(shared, npi_coef=0.0),
        "no_awareness": replace(shared, awareness=math.inf),
        "no_seasonality": replace(shared, seasonality=0.0),
    }
    rows = []
    for method, point in variants.items():
        fit_awareness = np.isfinite(point.awareness)
        aware_grid = AWARE_MULT_GRID if fit_awareness else (1.0,)
        best = _refine(truncated, _coarse(truncated, point, tau_grid, seed_grid, aware_grid), point, fit_awareness=fit_awareness)
        for i, row in best.iterrows():
            c, late = countries[i], held_out[i]
            pm = 1e6 / c.place.population
            rows.append({"iso_code": c.iso, "method": method, "observed": c.observed[late] * pm, "predicted": row["weekly"][late] * pm})
    for c, late in zip(countries, held_out, strict=True):
        pm = 1e6 / c.place.population
        recent = c.observed[~late][-4:] * pm
        level = float(np.nanmean(recent)) if np.isfinite(recent).any() else 0.0
        rows.append(
            {"iso_code": c.iso, "method": "persistence", "observed": c.observed[late] * pm, "predicted": np.full(late.sum(), level)}
        )
    detail = pd.DataFrame(rows)
    return _score(detail), detail


def _align(curve: np.ndarray, n: int) -> np.ndarray:
    out = np.full(n, np.nan)
    out[: min(n, len(curve))] = curve[:n]
    return out


def _score(detail: pd.DataFrame) -> dict:
    out = {}
    for method, frame in detail.groupby("method"):
        abs_err, totals_obs, totals_pred, peak_err = [], [], [], []
        for obs, pred in zip(frame["observed"], frame["predicted"], strict=True):
            ok = np.isfinite(obs) & np.isfinite(pred)
            abs_err.append(np.abs(obs[ok] - pred[ok]).sum())
            totals_obs.append(obs[ok].sum())
            totals_pred.append(pred[ok].sum())
            if np.nanmax(obs) >= 1:
                peak_err.append(abs(int(np.argmax(np.where(ok, obs, -1))) - int(np.argmax(np.where(ok, pred, -1)))))
        totals_obs, totals_pred = np.array(totals_obs), np.array(totals_pred)
        weeks = np.array([int((np.isfinite(o) & np.isfinite(p)).sum()) for o, p in zip(frame["observed"], frame["predicted"], strict=True)])
        n_weeks = weeks.sum()
        out[method] = {
            "mae_weekly_deaths_pm": round(float(np.sum(abs_err) / n_weeks), 3),
            # Robust to a few explosive countries: the typical country's error.
            "median_country_mae": round(float(np.median(np.array(abs_err)[weeks > 0] / weeks[weeks > 0])), 3),
            "wape": round(float(np.sum(abs_err) / totals_obs.sum()), 3),
            "mae_cumulative_deaths_pm": round(float(np.mean(np.abs(totals_obs - totals_pred))), 1),
            "spearman_cumulative": round(float(spearmanr(totals_obs, totals_pred).statistic), 3),
            "median_peak_week_error": float(np.median(peak_err)) if peak_err else None,
            "countries": int(len(frame)),
        }
    return out
