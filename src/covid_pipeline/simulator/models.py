"""Learned models that turn a country's characteristics into simulator settings.

* M1 ``fit_npi_panel``: panel regression of log Rt on lockdown stringency (fatigue and adherence).
* M3 ``fit_ridge``: maps country features to the calibrated transmission and severity multipliers.
* M4 ``fit_vaccine_rollout``: logistic curves of first-dose coverage, then ceiling and speed vs features.
* M5 ``fit_reporting``: share of deaths reported (reported vs excess deaths) vs features.
* M6 ``fit_wave_classifier``: classifies historical waves into severity classes.
* M7 ``fit_archetypes``: k-means country archetypes, PCA map and nearest-neighbour analogs.

M2, the per-country calibration of the engine, is in ``calibrate.py``.

Every model that the browser re-evaluates (when a visitor edits a country) is linear, so it
exports as coefficients. Tree ensembles are fitted alongside as a benchmark, and the metrics
report both.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from scipy.signal import find_peaks
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, RidgeCV
from sklearn.metrics import confusion_matrix, f1_score, log_loss, mean_absolute_error, r2_score, roc_auc_score, silhouette_score
from sklearn.model_selection import GroupKFold, KFold, cross_val_predict

from .season import SEASON_FULL_LATITUDE, SEASON_TROPIC_LATITUDE, hemisphere_day, season_weight

log = logging.getLogger(__name__)

RANDOM_STATE = 42
MIN_POPULATION = 1_000_000

# Country features shared by every model: (name, source column, transform).
FEATURES = [
    ("log_gdp_per_capita", "gdp_per_capita", "log"),
    ("log_health_exp_per_capita", "health_exp_per_capita", "log"),
    ("share_65_plus", "share_65_plus", "identity"),
    ("uhc_index", "uhc_index", "identity"),
    ("physicians_per_thousand", "physicians_per_thousand", "identity"),
    ("hospital_beds_per_thousand", "hospital_beds_per_thousand", "identity"),
    ("urban_share", "urban_share", "identity"),
    ("log_population_density", "population_density", "log"),
    ("diabetes_prevalence", "diabetes_prevalence", "identity"),
    ("basic_sanitation", "basic_sanitation", "identity"),
    ("extreme_poverty", "extreme_poverty", "identity"),
    ("out_of_pocket_share", "out_of_pocket_share", "identity"),
    ("measles_immunization", "measles_immunization", "identity"),
]
FEATURE_NAMES = [f[0] for f in FEATURES]
ALPHAS = np.logspace(-2, 3, 30)


@dataclass
class Standardizer:
    """Median imputation then z-scores; exported so the browser can apply the same transform."""

    medians: pd.Series
    means: pd.Series
    stds: pd.Series

    @classmethod
    def fit(cls, raw: pd.DataFrame) -> Standardizer:
        medians = raw.median()
        filled = raw.fillna(medians)
        return cls(medians, filled.mean(), filled.std(ddof=0).replace(0, 1.0))

    def transform(self, raw: pd.DataFrame) -> pd.DataFrame:
        return (raw.fillna(self.medians) - self.means) / self.stds

    def to_dict(self) -> dict:
        return {
            "names": FEATURE_NAMES,
            "sources": [f[1] for f in FEATURES],
            "transforms": [f[2] for f in FEATURES],
            "medians": _floats(self.medians),
            "means": _floats(self.means),
            "stds": _floats(self.stds),
        }


def _floats(values) -> list[float]:
    return [round(float(v), 6) for v in values]


def raw_features(profile: pd.DataFrame) -> pd.DataFrame:
    """The model features before imputation, indexed like ``profile``."""
    out = pd.DataFrame(index=profile.index)
    for name, column, transform in FEATURES:
        values = pd.to_numeric(profile[column], errors="coerce")
        out[name] = np.log(values.where(values > 0)) if transform == "log" else values
    return out


# --------------------------------------------------------------------------- linear models


def fit_ridge(X: pd.DataFrame, y: pd.Series, name: str, n_splits: int = 5) -> tuple[dict, dict]:
    """Ridge with CV-chosen alpha, benchmarked against gradient boosting under the same folds.

    Returns (exportable model, metrics). Metrics are out-of-fold: every prediction comes from a
    model that never saw that country.
    """
    folds = KFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_STATE)
    ridge = RidgeCV(alphas=ALPHAS)
    oof_ridge = cross_val_predict(ridge, X, y, cv=folds)
    gbm = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_depth=3, min_samples_leaf=10, random_state=RANDOM_STATE)
    oof_gbm = cross_val_predict(gbm, X, y, cv=folds)
    baseline = cross_val_predict(DummyRegressor(), X, y, cv=folds)
    ridge.fit(X, y)
    residual_sd = float(np.sqrt(np.mean((y - oof_ridge) ** 2)))
    metrics = {
        "n": int(len(y)),
        "cv_r2_ridge": round(float(r2_score(y, oof_ridge)), 3),
        "cv_r2_gbm": round(float(r2_score(y, oof_gbm)), 3),
        "cv_mae_ridge": round(float(mean_absolute_error(y, oof_ridge)), 4),
        "cv_mae_gbm": round(float(mean_absolute_error(y, oof_gbm)), 4),
        "cv_mae_mean_only": round(float(mean_absolute_error(y, baseline)), 4),
        "alpha": round(float(ridge.alpha_), 4),
        "residual_sd": round(residual_sd, 4),
    }
    model = {
        "name": name,
        "intercept": round(float(ridge.intercept_), 6),
        "coef": dict(zip(X.columns, _floats(ridge.coef_), strict=True)),
        "residual_sd": round(residual_sd, 4),
    }
    log.info("%s: CV R2 ridge %.3f, GBM %.3f (n=%s)", name, metrics["cv_r2_ridge"], metrics["cv_r2_gbm"], metrics["n"])
    return model, metrics


def predict_linear(model: dict, Z: pd.DataFrame) -> pd.Series:
    coef = pd.Series(model["coef"])
    return model["intercept"] + Z[coef.index] @ coef


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def expit(x):
    return 1 / (1 + np.exp(-x))


# --------------------------------------------------------------------------- M1: lockdowns and Rt


def fit_npi_panel(sim_weekly: pd.DataFrame, profile: pd.DataFrame, lag_weeks: int = 2) -> dict:
    """Panel regression of log Rt on stringency by period, with adherence and seasonality terms.

    log Rt[c,t] = country FE + variant era + vaccination
                  + stringency[c,t-lag] x period + stringency[c,t-lag] x share 65+ (z)
                  + w(lat) x [a cos(2 pi d/365) + b sin(2 pi d/365)]

    where d is the day of year (shifted half a year in the Southern Hemisphere) and w(lat) scales
    seasonality from 0 inside the tropics to 1 at 40 degrees. Northern and southern countries have
    opposite seasons, which separates seasonality from the global timing of waves.

    Rt comes from case growth, and governments tighten when Rt is high, so the level of the lockdown
    effect is biased toward zero. The simulator takes that level from the deaths-based calibration
    (M2) and uses this model for how the effect fades over time (fatigue), how it varies with the
    share of older people (adherence), and the seasonal cycle.
    """
    import statsmodels.formula.api as smf

    big = profile.loc[profile["population"] >= MIN_POPULATION, ["iso_code", "share_65_plus", "latitude"]]
    z65 = (big["share_65_plus"] - big["share_65_plus"].mean()) / big["share_65_plus"].std()
    panel = sim_weekly[sim_weekly["iso_code"].isin(big["iso_code"])].sort_values(["iso_code", "week_end"]).copy()
    panel["s"] = panel.groupby("iso_code")["stringency_index"].shift(lag_weeks) / 10
    panel["z65"] = panel["iso_code"].map(dict(zip(big["iso_code"], z65, strict=True)))
    # Unknown latitude (Kosovo isn't on the map) counts as no seasonality.
    latitude = panel["iso_code"].map(dict(zip(big["iso_code"], big["latitude"], strict=True))).fillna(0.0)
    angle = 2 * np.pi * hemisphere_day(panel["week_end"].dt.dayofyear, latitude) / 365
    panel["season_cos"] = season_weight(latitude) * np.cos(angle)
    panel["season_sin"] = season_weight(latitude) * np.sin(angle)
    panel["vax"] = panel["first_dose_rate"].fillna(0)
    panel["era"] = np.select([panel["week_end"] < "2021-01-01", panel["week_end"] < "2021-06-01"], ["ancestral", "alpha"], "delta")
    panel["period"] = np.select(
        [panel["week_end"] < "2020-07-01", panel["week_end"] < "2021-01-01"], ["2020H1", "2020H2"], "2021H1"
    )
    rt = panel["reproduction_rate"]
    panel["log_rt"] = np.log(rt.where(rt.between(0.05, 5)))
    # Rt from case growth is noise when a country has only a handful of cases.
    sample = panel[(panel["new_cases"] >= 100) & panel["week_end"].between("2020-02-15", "2021-06-30")].dropna(
        subset=["s", "log_rt", "z65"]
    )
    groups = pd.factorize(sample["iso_code"])[0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # statsmodels warns about the rank of the FE Wald test
        fit = smf.ols("log_rt ~ s:C(period) + s:z65 + vax + C(era) + season_cos + season_sin + C(iso_code)", data=sample).fit(
            cov_type="cluster", cov_kwds={"groups": groups}
        )
    ci = fit.conf_int()

    def term(name: str, key: str = "coef_per_10") -> dict:
        return {key: round(float(fit.params[name]), 5), "ci95": [round(float(v), 5) for v in ci.loc[name]]}

    periods = {p: term(f"s:C(period)[{p}]") for p in ("2020H1", "2020H2", "2021H1")}
    early = np.mean([periods["2020H1"]["coef_per_10"], periods["2020H2"]["coef_per_10"]])
    fatigue_ratio = float(np.clip(periods["2021H1"]["coef_per_10"] / early, 0.2, 1.0))
    adherence_per_sd = float(fit.params["s:z65"] / early)
    a, b = float(fit.params["season_cos"]), float(fit.params["season_sin"])
    amplitude = float(np.hypot(a, b))
    # a cos(x) + b sin(x) = amplitude * cos(x - phase): transmission peaks at day ``phase`` (north).
    peak_day = float((np.degrees(np.arctan2(b, a)) / 360 * 365) % 365)
    return {
        "spec": (
            f"log Rt ~ stringency(lag {lag_weeks}w) x period + stringency x z(share 65+) + vaccination + era "
            "+ latitude-weighted seasonal harmonic + country FE"
        ),
        "n": int(fit.nobs),
        "countries": int(sample["iso_code"].nunique()),
        "r2": round(float(fit.rsquared), 3),
        "periods": periods,
        "adherence_interaction": term("s:z65"),
        "fatigue_ratio": round(fatigue_ratio, 3),
        "adherence_per_sd_65_plus": round(adherence_per_sd, 3),
        "z65_mean": round(float(big["share_65_plus"].mean()), 5),
        "z65_std": round(float(big["share_65_plus"].std()), 5),
        "reduction_at_80": {p: round(1 - float(np.exp(8 * v["coef_per_10"])), 3) for p, v in periods.items()},
        "seasonality": {
            "cos": term("season_cos", "coef"),
            "sin": term("season_sin", "coef"),
            "amplitude_log_rt": round(amplitude, 4),
            "peak_day_of_year_north": round(peak_day, 1),
            "winter_to_summer_reduction": round(1 - float(np.exp(-2 * amplitude)), 3),
            "zero_below_latitude": SEASON_TROPIC_LATITUDE,
            "full_strength_latitude": SEASON_FULL_LATITUDE,
        },
    }


def adherence(share_65_plus: pd.Series, npi: dict) -> pd.Series:
    """Multiplier on the lockdown effect from M1's share-65+ interaction, clipped to [0.5, 1.5]."""
    z = (share_65_plus - npi["z65_mean"]) / npi["z65_std"]
    return (1 + npi["adherence_per_sd_65_plus"] * z).clip(0.5, 1.5)


# --------------------------------------------------------------------------- M5: reporting


def reporting_targets(profile: pd.DataFrame, min_excess_pm: float = 200.0) -> pd.Series:
    """Observed share of deaths reported, where excess mortality gives a usable denominator.

    Countries with little or negative excess mortality (Australia, New Zealand, ...) say nothing
    about reporting and are left out. Where reported deaths exceed excess deaths, reporting is
    treated as complete.
    """
    big = profile[profile["population"] >= MIN_POPULATION].set_index("iso_code")
    usable = big[big["excess_deaths_pm_2021"] >= min_excess_pm]
    return (usable["reported_deaths_pm_2021"] / usable["excess_deaths_pm_2021"]).clip(0.02, 0.99).rename("reporting")


def fit_reporting(profile: pd.DataFrame, Z: pd.DataFrame) -> tuple[dict, dict, pd.Series]:
    observed = reporting_targets(profile)
    model, metrics = fit_ridge(Z.loc[observed.index], logit(observed), "reporting (logit share of deaths reported)")
    metrics["median_observed"] = round(float(observed.median()), 3)
    return model, metrics, observed


# --------------------------------------------------------------------------- M4: vaccine rollout


def _logistic(t, K, r, t0):
    return K / (1 + np.exp(-r * (t - t0)))


def fit_vaccine_curves(sim_weekly: pd.DataFrame, start: str = "2020-12-01") -> pd.DataFrame:
    """Logistic fit of first-dose coverage per country: ceiling K, speed r (per day), midpoint t0."""
    rows = []
    origin = pd.Timestamp(start)
    for iso, frame in sim_weekly.dropna(subset=["first_dose_rate"]).groupby("iso_code"):
        frame = frame[frame["week_end"] >= origin]
        if len(frame) < 12 or frame["first_dose_rate"].max() < 0.02:
            continue
        t = (frame["week_end"] - origin).dt.days.to_numpy(dtype=float)
        y = frame["first_dose_rate"].clip(upper=1.0).to_numpy()
        try:
            (K, r, t0), _ = curve_fit(_logistic, t, y, p0=[max(y.max(), 0.05), 0.02, 200], bounds=([0.01, 0.002, 0], [1.0, 0.3, 1000]))
        except RuntimeError:
            continue
        rmse = float(np.sqrt(np.mean((_logistic(t, K, r, t0) - y) ** 2)))
        rows.append({"iso_code": iso, "K": K, "r": r, "t0": t0, "rmse": rmse, "peak_daily": K * r / 4})
    return pd.DataFrame(rows).set_index("iso_code")


def fit_vaccine_rollout(sim_weekly: pd.DataFrame, Z: pd.DataFrame) -> tuple[dict, dict, pd.DataFrame]:
    """Vaccine acceptance (ceiling) and rollout speed (peak share vaccinated per day) vs features.

    The 2021 rollout reflected global vaccine supply as much as delivery capacity: low-income
    countries waited for doses. The speed model learns what happened, which the app says.
    """
    curves = fit_vaccine_curves(sim_weekly)
    curves = curves[curves.index.isin(Z.index)]
    ceiling, ceiling_metrics = fit_ridge(Z.loc[curves.index], logit(curves["K"]), "vaccine acceptance (logit ceiling)")
    speed, speed_metrics = fit_ridge(Z.loc[curves.index], np.log(curves["peak_daily"]), "vaccine speed (log peak share per day)")
    metrics = {
        "countries_fitted": int(len(curves)),
        "median_curve_rmse": round(float(curves["rmse"].median()), 4),
        "ceiling": ceiling_metrics,
        "speed": speed_metrics,
    }
    return {"ceiling": ceiling, "speed": speed}, metrics, curves


# --------------------------------------------------------------------------- M6: waves


SEVERITY_CLASSES = ["low", "moderate", "high", "severe"]
ERAS = ["ancestral", "alpha", "delta", "omicron"]


def era_of(dates: pd.Series) -> pd.Series:
    return pd.Series(
        np.select([dates < "2021-01-01", dates < "2021-06-01", dates < "2021-12-15"], ERAS[:3], ERAS[3]), index=dates.index
    )


def detect_waves(sim_weekly: pd.DataFrame, min_prominence: float = 1.0, min_gap_weeks: int = 8) -> pd.DataFrame:
    """Waves in each country's smoothed weekly deaths per million.

    A wave is a peak with prominence of at least ``min_prominence`` deaths per million per week
    (and a quarter of the country's own maximum), at least ``min_gap_weeks`` from the next. It
    starts at the lowest point since the previous peak.
    """
    rows = []
    data = sim_weekly[sim_weekly["population"] >= MIN_POPULATION]
    for iso, frame in data.sort_values("week_end").groupby("iso_code"):
        frame = frame.reset_index(drop=True)
        series = frame["weekly_deaths_per_million"].interpolate(limit=3).rolling(3, center=True, min_periods=1).mean()
        if series.isna().all() or series.max() <= 0:
            continue
        values = series.fillna(0).to_numpy()
        prominence = max(min_prominence, 0.25 * values.max())
        peaks, props = find_peaks(values, prominence=prominence, distance=min_gap_weeks)
        previous = 0
        for peak, left in zip(peaks, props["left_bases"], strict=True):
            start = int(left) if left >= previous else previous
            start = start + int(np.argmin(values[start : peak + 1]))
            rows.append(
                {
                    "iso_code": iso,
                    "start": frame.at[start, "week_end"],
                    "peak": frame.at[peak, "week_end"],
                    "peak_dpm": float(values[peak]),
                    "weeks_to_peak": int(peak - start),
                    "start_index": start,
                }
            )
            previous = peak
    return pd.DataFrame(rows)


def wave_features(waves: pd.DataFrame, sim_weekly: pd.DataFrame, Z: pd.DataFrame) -> pd.DataFrame:
    """What was known at each wave's start: country features, early policy, vaccination, era."""
    out = []
    by_country = {iso: f.sort_values("week_end").reset_index(drop=True) for iso, f in sim_weekly.groupby("iso_code")}
    for wave in waves.itertuples():
        frame = by_country[wave.iso_code]
        i = wave.start_index
        early = frame.iloc[i : i + 4]
        prior = frame.iloc[:i]["weekly_deaths_per_million"].fillna(0).sum()
        out.append(
            {
                "stringency_first_4w": float(early["stringency_index"].mean()) if early["stringency_index"].notna().any() else np.nan,
                "vaccinated_at_start": float(frame.at[i, "first_dose_rate"]) if pd.notna(frame.at[i, "first_dose_rate"]) else 0.0,
                "log_prior_deaths_pm": float(np.log1p(prior)),
            }
        )
    feats = pd.DataFrame(out, index=waves.index)
    # The stringency index ends in 2022: later waves are treated as having no restrictions.
    feats["stringency_first_4w"] = feats["stringency_first_4w"].fillna(0.0)
    eras = era_of(waves["start"])
    for era in ERAS[1:]:
        feats[f"era_{era}"] = (eras == era).astype(float)
    static = Z.reindex(waves["iso_code"]).set_index(waves.index)
    return pd.concat([static, feats], axis=1)


def fit_wave_classifier(sim_weekly: pd.DataFrame, Z: pd.DataFrame, n_splits: int = 5) -> tuple[dict, dict, pd.DataFrame]:
    waves = detect_waves(sim_weekly)
    waves = waves[waves["iso_code"].isin(Z.index)].reset_index(drop=True)
    X = wave_features(waves, sim_weekly, Z)
    thresholds = np.quantile(waves["peak_dpm"], [0.25, 0.5, 0.75])
    y = np.digitize(waves["peak_dpm"], thresholds)
    groups = waves["iso_code"]

    dynamic = ["stringency_first_4w", "vaccinated_at_start", "log_prior_deaths_pm"]
    scale_mean = X[dynamic].mean()
    scale_std = X[dynamic].std(ddof=0).replace(0, 1)
    Xs = X.copy()
    Xs[dynamic] = (X[dynamic] - scale_mean) / scale_std

    cv = GroupKFold(n_splits=n_splits)
    logistic = LogisticRegression(C=0.5, max_iter=2000)
    gbm = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_depth=3, min_samples_leaf=15, random_state=RANDOM_STATE)
    era_cols = [c for c in Xs.columns if c.startswith("era_")]
    proba = {
        "logistic": cross_val_predict(logistic, Xs, y, cv=cv, groups=groups, method="predict_proba"),
        "gradient_boosting": cross_val_predict(gbm, Xs, y, cv=cv, groups=groups, method="predict_proba"),
        "era_only": cross_val_predict(LogisticRegression(max_iter=2000), Xs[era_cols], y, cv=cv, groups=groups, method="predict_proba"),
    }
    prior = np.bincount(y, minlength=4) / len(y)
    proba["class_frequencies"] = np.tile(prior, (len(y), 1))

    def score(p: np.ndarray) -> dict:
        pred = p.argmax(axis=1)
        return {
            "accuracy": round(float((pred == y).mean()), 3),
            "macro_f1": round(float(f1_score(y, pred, average="macro")), 3),
            "roc_auc_ovr": round(float(roc_auc_score(y, p, multi_class="ovr")), 3),
            "log_loss": round(float(log_loss(y, p, labels=[0, 1, 2, 3])), 3),
        }

    scores = {name: score(p) for name, p in proba.items()}
    # Reliability: predicted vs observed frequency of the "severe" class in probability deciles.
    p_severe = proba["logistic"][:, 3]
    bins = np.clip((p_severe * 10).astype(int), 0, 9)
    calibration = [
        {
            "bin": int(b),
            "predicted": round(float(p_severe[bins == b].mean()), 3),
            "observed": round(float((y[bins == b] == 3).mean()), 3),
            "n": int((bins == b).sum()),
        }
        for b in np.unique(bins)
    ]
    logistic.fit(Xs, y)
    model = {
        "classes": SEVERITY_CLASSES,
        "thresholds_peak_dpm": _floats(thresholds),
        "features": list(Xs.columns),
        "dynamic_mean": _floats(scale_mean),
        "dynamic_std": _floats(scale_std),
        "dynamic": dynamic,
        "coef": [_floats(row) for row in logistic.coef_],
        "intercept": _floats(logistic.intercept_),
    }
    metrics = {
        "waves": int(len(waves)),
        "countries": int(waves["iso_code"].nunique()),
        "class_thresholds_peak_weekly_deaths_per_million": _floats(thresholds),
        "cv": "GroupKFold by country (5 folds)",
        "scores": scores,
        "confusion_matrix_logistic": confusion_matrix(y, proba["logistic"].argmax(axis=1)).tolist(),
        "calibration_severe_logistic": calibration,
    }
    log.info(
        "Wave classifier: %s waves, macro-F1 logistic %.3f vs GBM %.3f",
        len(waves),
        scores["logistic"]["macro_f1"],
        scores["gradient_boosting"]["macro_f1"],
    )
    waves = waves.assign(severity=[SEVERITY_CLASSES[i] for i in y])
    return model, metrics, waves


# --------------------------------------------------------------------------- M7: archetypes


def fit_archetypes(Z: pd.DataFrame, k_range: range = range(3, 9)) -> tuple[dict, dict, pd.DataFrame]:
    """k-means archetypes on standardized features (k by silhouette) and a 2-D PCA map."""
    silhouettes = {}
    for k in [k for k in k_range if k < len(Z)]:
        labels = KMeans(n_clusters=k, n_init=20, random_state=RANDOM_STATE).fit_predict(Z)
        silhouettes[k] = float(silhouette_score(Z, labels))
    best_k = max(silhouettes, key=silhouettes.get)
    kmeans = KMeans(n_clusters=best_k, n_init=20, random_state=RANDOM_STATE).fit(Z)
    pca = PCA(n_components=2, random_state=RANDOM_STATE).fit(Z)
    coords = pca.transform(Z)
    # Typical distance to the nearest other country: the yardstick for "unlike any real country".
    dist = np.sqrt(((Z.to_numpy()[:, None, :] - Z.to_numpy()[None, :, :]) ** 2).sum(axis=2))
    np.fill_diagonal(dist, np.inf)
    nn = dist.min(axis=1)
    assignments = pd.DataFrame({"cluster": kmeans.labels_, "pc1": coords[:, 0], "pc2": coords[:, 1], "nn_distance": nn}, index=Z.index)
    model = {
        "k": best_k,
        "centroids": [_floats(c) for c in kmeans.cluster_centers_],
        "pca_components": [_floats(c) for c in pca.components_],
        "pca_mean": _floats(pca.mean_),
        "nn_distance_median": round(float(np.median(nn)), 4),
        "nn_distance_p95": round(float(np.quantile(nn, 0.95)), 4),
    }
    metrics = {
        "silhouette_by_k": {str(k): round(v, 3) for k, v in silhouettes.items()},
        "k": best_k,
        "pca_explained_variance": _floats(pca.explained_variance_ratio_),
        "cluster_sizes": np.bincount(kmeans.labels_).tolist(),
    }
    return model, metrics, assignments


def assign_archetypes(model: dict, Z: pd.DataFrame) -> pd.DataFrame:
    """Cluster, PCA position and nearest-country distance for any countries (fitted or not)."""
    X = Z.to_numpy()
    centroids = np.array(model["centroids"])
    cluster = ((X[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
    coords = (X - np.array(model["pca_mean"])) @ np.array(model["pca_components"]).T
    return pd.DataFrame({"cluster": cluster, "pc1": coords[:, 0], "pc2": coords[:, 1]}, index=Z.index)
