/**
 * The trained simulator (simulator.json, written by `covid-pipeline sim-train`) and the learned
 * models the browser re-evaluates when a visitor edits a country.
 *
 * Every learned setting is a linear model on standardised country features plus the country's own
 * residual: an unedited country gets exactly its calibrated or observed value, and an edit shifts
 * it by what the model learned about that feature.
 */
import type { Bands } from "./engine";
import { fromJson, type ModelConstants, type Pathogen, type Place } from "./scenario";

export type Source = "calibrated" | "observed" | "predicted";

export interface Learned {
  value: number;
  source: Source;
  residual: number;
}

export interface LinearModel {
  name: string;
  intercept: number;
  coef: Record<string, number>;
  residual_sd: number;
}

export type SignalName =
  | "median_age"
  | "share_65_plus"
  | "gdp_per_capita"
  | "health_exp_per_capita"
  | "out_of_pocket_share"
  | "uhc_index"
  | "physicians_per_thousand"
  | "hospital_beds_per_thousand"
  | "urban_share"
  | "population_density"
  | "diabetes_prevalence"
  | "basic_sanitation"
  | "extreme_poverty"
  | "handwashing_facilities"
  | "measles_immunization"
  | "life_expectancy";

export type Signals = Record<SignalName, number | null>;
export type LearnedName = "transmission" | "severity" | "awareness" | "reporting" | "vaccine_acceptance" | "vaccine_capacity" | "adherence";

export interface CountryProfile {
  iso: string;
  name: string;
  continent: string | null;
  population: number;
  age_shares: Bands;
  age_means: Bands;
  age_source: "worldbank" | "imputed_from_median_age" | null;
  latitude: number | null;
  signals: Signals;
  z: number[];
  learned: Record<LearnedName, Learned>;
  seed_day_2020: number | null;
  fit_rmse_log: number | null;
  archetype: { cluster: number; pc1: number; pc2: number };
  outcomes: {
    reported_deaths_pm_2021: number | null;
    excess_deaths_pm_2021: number | null;
    peak_weekly_deaths_pm_2021: number | null;
    stringency_mean_2021: number | null;
    first_dose_peak: number | null;
  };
}

export interface Score {
  mae_weekly_deaths_pm: number;
  median_country_mae: number;
  wape: number;
  mae_cumulative_deaths_pm: number;
  spearman_cumulative: number;
  median_peak_week_error: number | null;
  countries: number;
}

export interface SimModel {
  version: string;
  trained_at: string;
  bands: string[];
  constants: ModelConstants;
  uncertainty: {
    log_transmission_sd: { calibrated: number; predicted: number };
    log_severity_sd: { calibrated: number; predicted: number };
    log_awareness_country_sd: { calibrated: number; predicted: number };
    logit_reporting_sd: { observed: number; predicted: number };
    logit_vaccine_acceptance_sd: { observed: number; predicted: number };
    log_vaccine_capacity_sd: { observed: number; predicted: number };
    npi_coef_sd: number;
    log_awareness_sd: number | null;
    seasonality_sd: number;
    log_r0_sd: number;
    log_ifr_sd: number;
  };
  presets: Pathogen[];
  features: { names: string[]; sources: SignalName[]; transforms: ("log" | "identity")[]; medians: number[]; means: number[]; stds: number[] };
  models: {
    transmission: LinearModel;
    severity: LinearModel;
    awareness: LinearModel;
    reporting: LinearModel;
    vaccine_acceptance: LinearModel;
    vaccine_capacity: LinearModel;
    npi: { fatigue_ratio: number; adherence_per_sd_65_plus: number; z65_mean: number; z65_std: number };
    season_tropic_latitude: number;
    season_full_latitude: number;
    waves: {
      classes: string[];
      thresholds_peak_dpm: number[];
      features: string[];
      dynamic: string[];
      dynamic_mean: number[];
      dynamic_std: number[];
      coef: number[][];
      intercept: number[];
    };
    archetypes: {
      k: number;
      centroids: number[][];
      pca_components: number[][];
      pca_mean: number[];
      nn_distance_median: number;
      nn_distance_p95: number;
    };
  };
  countries: CountryProfile[];
  validation: { temporal_holdout: Record<string, Score>; cross_country_hindcast: Record<string, Score>; reading: string };
  byIso: Map<string, CountryProfile>;
}

/** Load and normalise simulator.json (null -> Infinity where JSON couldn't carry it). */
export async function loadSimulator(url = `${import.meta.env.BASE_URL}data/simulator.json`): Promise<SimModel> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Couldn't load simulator.json (HTTP ${res.status}). Run \`covid-pipeline sim-train\` and \`web-export\`.`);
  return prepare(await res.json());
}

export function prepare(raw: Omit<SimModel, "byIso">): SimModel {
  return {
    ...raw,
    constants: fromJson.constants(raw.constants),
    presets: raw.presets.map(fromJson.pathogen),
    byIso: new Map(raw.countries.map((c) => [c.iso, c])),
  };
}

// --------------------------------------------------------------------------- features + linear models

/** Standardised feature vector for a set of signals (missing values take the training median). */
export function featureVector(model: SimModel, signals: Partial<Signals>): number[] {
  const f = model.features;
  return f.names.map((_, i) => {
    const raw = signals[f.sources[i]];
    let value = raw === null || raw === undefined || (f.transforms[i] === "log" && raw <= 0) ? null : raw;
    if (value !== null && f.transforms[i] === "log") value = Math.log(value);
    return ((value ?? f.medians[i]) - f.means[i]) / f.stds[i];
  });
}

export function predictLinear(m: LinearModel, model: SimModel, z: number[]): number {
  return model.features.names.reduce((s, name, i) => s + (m.coef[name] ?? 0) * z[i], m.intercept);
}

const logit = (p: number) => {
  const q = Math.min(Math.max(p, 1e-6), 1 - 1e-6);
  return Math.log(q / (1 - q));
};
const expit = (x: number) => 1 / (1 + Math.exp(-x));
const LINKS: Record<Exclude<LearnedName, "adherence">, "log" | "logit"> = {
  transmission: "log",
  severity: "log",
  awareness: "log",
  reporting: "logit",
  vaccine_acceptance: "logit",
  vaccine_capacity: "log",
};

export function adherence(model: SimModel, share65: number | null): number {
  if (share65 === null) return 1;
  const npi = model.models.npi;
  const z = (share65 - npi.z65_mean) / npi.z65_std;
  return Math.min(Math.max(1 + npi.adherence_per_sd_65_plus * z, 0.5), 1.5);
}

/**
 * Learned settings for a country whose signals may have been edited. Unedited, every value is the
 * country's own; edited, each moves by the model's prediction for the new signals, keeping the
 * country's residual (what the features can't explain about it).
 */
export function learnedFor(model: SimModel, country: CountryProfile, signals: Signals): Record<LearnedName, Learned> {
  const z = featureVector(model, signals);
  const out = {} as Record<LearnedName, Learned>;
  for (const [name, link] of Object.entries(LINKS) as [Exclude<LearnedName, "adherence">, "log" | "logit"][]) {
    const base = country.learned[name];
    const edited = model.features.names.some((_, i) => Math.abs(z[i] - country.z[i]) > 1e-3);
    if (!edited) {
      out[name] = base;
      continue;
    }
    const eta = predictLinear(model.models[name], model, z) + base.residual;
    out[name] = { value: link === "log" ? Math.exp(eta) : expit(eta), source: base.source, residual: base.residual };
  }
  out.adherence = { value: adherence(model, signals.share_65_plus), source: "predicted", residual: 0 };
  return out;
}

export { expit, logit };

// --------------------------------------------------------------------------- age structure

/** Age structure for an edited median age: the average of the five countries closest in median age. */
export function ageStructureFor(model: SimModel, medianAge: number): { shares: Bands; means: Bands; share65: number } {
  const known = model.countries.filter((c) => c.signals.median_age !== null && c.age_source === "worldbank");
  const nearest = [...known].sort((a, b) => Math.abs(a.signals.median_age! - medianAge) - Math.abs(b.signals.median_age! - medianAge)).slice(0, 5);
  const avg = (pick: (c: CountryProfile) => number[]) => pick(nearest[0]).map((_, b) => nearest.reduce((s, c) => s + pick(c)[b], 0) / nearest.length);
  const shares = avg((c) => c.age_shares);
  const total = shares.reduce((a, b) => a + b, 0);
  const share65 = nearest.reduce((s, c) => s + (c.signals.share_65_plus ?? 0), 0) / nearest.length;
  return { shares: shares.map((s) => s / total), means: avg((c) => c.age_means), share65 };
}

// --------------------------------------------------------------------------- place

export interface PlaceSettings {
  population: number;
  age_shares: Bands;
  age_means: Bands;
  latitude: number | null;
  signals: Signals;
  icu_share_of_beds: number;
  bed_availability: number;
}

/** The engine's Place for a (possibly edited) country, plus where each learned value came from. */
export function buildPlace(model: SimModel, country: CountryProfile, s: PlaceSettings, overrides: Partial<Place> = {}) {
  const learned = learnedFor(model, country, s.signals);
  const beds = s.signals.hospital_beds_per_thousand ?? median(model, "hospital_beds_per_thousand");
  const uhc = s.signals.uhc_index ?? median(model, "uhc_index");
  const place: Place = {
    population: s.population,
    age_shares: s.age_shares,
    age_means: s.age_means,
    beds_per_thousand: beds,
    latitude: s.latitude,
    bed_availability: s.bed_availability,
    icu_share_of_beds: s.icu_share_of_beds,
    transmission: learned.transmission.value,
    severity: learned.severity.value,
    adherence: learned.adherence.value,
    awareness: learned.awareness.value,
    access: uhc / 100,
    death_reporting: learned.reporting.value,
    vaccine_acceptance: learned.vaccine_acceptance.value,
    vaccine_capacity: learned.vaccine_capacity.value,
    ...overrides,
  };
  return { place, learned };
}

function median(model: SimModel, signal: SignalName): number {
  const values = model.countries
    .map((c) => c.signals[signal])
    .filter((v): v is number => v !== null)
    .sort((a, b) => a - b);
  return values[Math.floor(values.length / 2)];
}

export function settingsFor(country: CountryProfile): PlaceSettings {
  return {
    population: country.population,
    age_shares: [...country.age_shares],
    age_means: [...country.age_means],
    latitude: country.latitude,
    signals: { ...country.signals },
    icu_share_of_beds: 0.05,
    bed_availability: 0.5,
  };
}

// --------------------------------------------------------------------------- analogs, archetypes, waves

const distance = (a: number[], b: number[]) => Math.sqrt(a.reduce((s, v, i) => s + (v - b[i]) ** 2, 0));

/** The real countries most like these features, and how unusual the features are overall. */
export function analogs(model: SimModel, z: number[], k = 5, minPopulation = 1_000_000) {
  const ranked = model.countries
    .filter((c) => c.population >= minPopulation)
    .map((c) => ({ country: c, distance: distance(z, c.z) }))
    .sort((a, b) => a.distance - b.distance);
  const nearest = ranked[0]?.distance ?? 0;
  const arch = model.models.archetypes;
  return {
    nearest: ranked.slice(0, k),
    /** 1 = as close to a real country as real countries are to each other. */
    unusualness: nearest / arch.nn_distance_median,
    outOfRange: nearest > arch.nn_distance_p95,
  };
}

export function archetypeOf(model: SimModel, z: number[]): number {
  const centroids = model.models.archetypes.centroids;
  let best = 0;
  for (let k = 1; k < centroids.length; k++) if (distance(z, centroids[k]) < distance(z, centroids[best])) best = k;
  return best;
}

export type Era = "ancestral" | "alpha" | "delta" | "omicron";
/** The SARS-CoV-2 presets the wave classifier (M6) can speak to, and the variant era each matches. */
export const PRESET_ERA: Record<string, Era> = { covid_ancestral: "ancestral", covid_delta: "delta", covid_omicron: "omicron" };

/** M6: probability of each wave-severity class for a COVID-like wave starting in these conditions. */
export function waveSeverity(
  model: SimModel,
  z: number[],
  start: { stringency_first_4w: number; vaccinated_at_start: number; log_prior_deaths_pm: number },
  era: Era,
): { classes: string[]; probabilities: number[]; thresholds: number[] } {
  const w = model.models.waves;
  const values: Record<string, number> = {};
  model.features.names.forEach((name, i) => (values[name] = z[i]));
  w.dynamic.forEach((name, i) => (values[name] = (start[name as keyof typeof start] - w.dynamic_mean[i]) / w.dynamic_std[i]));
  for (const e of ["alpha", "delta", "omicron"]) values[`era_${e}`] = era === e ? 1 : 0;
  const logits = w.coef.map((row, k) => w.features.reduce((s, name, i) => s + row[i] * (values[name] ?? 0), w.intercept[k]));
  const max = Math.max(...logits);
  const exps = logits.map((l) => Math.exp(l - max));
  const total = exps.reduce((a, b) => a + b, 0);
  return { classes: w.classes, probabilities: exps.map((e) => e / total), thresholds: w.thresholds_peak_dpm };
}
