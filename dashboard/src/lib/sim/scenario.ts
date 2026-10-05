/**
 * Scenarios: a place, a pathogen and a response, translated into engine inputs.
 *
 * Mirrors src/covid_pipeline/simulator/scenario.py; field names stay snake_case so the same JSON
 * (golden fixtures, simulator.json, the cloud API) works on both sides. In that JSON, null means
 * Infinity for durations and days ("never", "lifelong", "off"); `fromJson` restores it.
 */
import { N_BANDS, type Bands, type EngineInputs } from "./engine";

export const BANDS = ["0-19", "20-39", "40-59", "60-79", "80+"];
export const MONTH_START_DAY = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
const LEVIN_INTERCEPT = -3.27;
const LEVIN_SLOPE = 0.0524;
const OLDER_BANDS = [false, false, false, true, true];
const HOSP_SHAPE_POWER = 0.6;
const MAX_FATALITY_PER_STAY = 0.95;
export const SEASON_TROPIC_LATITUDE = 23.5;
export const SEASON_FULL_LATITUDE = 40.0;

const FIXED_PROFILES: Record<string, Bands> = {
  w_shaped: [1.5, 3.0, 1.0, 0.7, 0.7],
  young: [2.0, 1.0, 1.0, 1.5, 2.0],
  flat: [1, 1, 1, 1, 1],
};

export type AgeProfile = "steep" | "rises" | "w_shaped" | "young" | "flat";

export interface Pathogen {
  id: string;
  name: string;
  kind: "historical" | "hypothetical" | "blank";
  r0: number;
  latent_days: number;
  infectious_days: number;
  ifr: number;
  hosp: number;
  age_profile: AgeProfile;
  hosp_days: number;
  icu_share: number;
  immunity_days: number;
  /** null = the amplitude learned for SARS-CoV-2 */
  seasonality: number | null;
  vaccine_day: number;
  ve_infection: number;
  ve_death: number;
  vaccine_immunity_days: number;
  assumptions: string[];
  sources: string[];
}

export interface Place {
  population: number;
  age_shares: Bands;
  age_means: Bands;
  beds_per_thousand: number;
  latitude: number | null;
  bed_availability: number;
  icu_share_of_beds: number;
  transmission: number;
  severity: number;
  adherence: number;
  /** Multiplier on the awareness threshold: above 1, people tolerate more deaths before pulling back. */
  awareness: number;
  access: number;
  death_reporting: number;
  vaccine_acceptance: number;
  vaccine_capacity: number;
}

export interface Segment {
  start_day: number;
  end_day: number;
  level: number;
}

export interface Response {
  segments: Segment[];
  adaptive: boolean;
  adaptive_on: number;
  adaptive_off: number;
  adaptive_level: number;
  adaptive_min_days: number;
  fatigue: boolean;
  awareness: boolean;
  isolation: number;
  border_delay_days: number;
  surge: number;
  vaccine: boolean;
  /** null = the pathogen's default */
  vaccine_day: number | null;
  vaccine_oldest_first: boolean;
  treatment_day: number;
  treatment_effect: number;
  case_detection: number;
  seed_per_million: number;
  start_month: number;
}

export interface Variant {
  day: number;
  transmission: number;
  severity: number;
  escape: number;
}

export interface ModelConstants {
  npi_coef: number;
  fatigue_ratio: number;
  fatigue_start: number;
  fatigue_end: number;
  awareness_deaths_pm: number;
  awareness_power: number;
  covid_seasonality: number;
  season_peak_day_north: number;
  icu_death_share: number;
  unmet_multiplier: number;
  child_acceptance_ratio: number;
  reference_shares: Bands;
  reference_means: Bands;
}

export const DEFAULT_RESPONSE: Response = {
  segments: [],
  adaptive: false,
  adaptive_on: 0.8,
  adaptive_off: 0.4,
  adaptive_level: 70,
  adaptive_min_days: 21,
  fatigue: true,
  awareness: true,
  isolation: 0,
  border_delay_days: 0,
  surge: 0,
  vaccine: true,
  vaccine_day: null,
  vaccine_oldest_first: true,
  treatment_day: Infinity,
  treatment_effect: 0.2,
  case_detection: 0.2,
  seed_per_million: 2,
  start_month: 1,
};

export const NO_VARIANT: Variant = { day: Infinity, transmission: 1, severity: 1, escape: 0 };

const inf = (v: number | null | undefined): number => (v === null || v === undefined ? Infinity : v);

/** Restore Infinity where JSON carried null. */
export const fromJson = {
  pathogen: (p: Pathogen): Pathogen => ({
    ...p,
    immunity_days: inf(p.immunity_days),
    vaccine_day: inf(p.vaccine_day),
    vaccine_immunity_days: inf(p.vaccine_immunity_days),
  }),
  response: (r: Response): Response => ({ ...r, treatment_day: inf(r.treatment_day) }),
  variant: (v: Variant): Variant => ({ ...v, day: inf(v.day) }),
  constants: (c: ModelConstants): ModelConstants => ({ ...c, awareness_deaths_pm: inf(c.awareness_deaths_pm) }),
};

/** Python's float modulo: the result takes the sign of the divisor. */
export function pymod(a: number, n: number): number {
  let r = a % n;
  if (r !== 0 && r < 0 !== n < 0) r += n;
  return r;
}

export function levinIfr(age: number): number {
  return 10 ** (LEVIN_INTERCEPT + LEVIN_SLOPE * age) / 100;
}

export function ageShape(profile: AgeProfile, bandMeans: Bands): Bands {
  if (profile === "steep") return bandMeans.map(levinIfr);
  if (profile === "rises") return bandMeans.map((a) => 10 ** ((LEVIN_SLOPE / 2) * a));
  return FIXED_PROFILES[profile];
}

const dot = (a: Bands, b: Bands) => a.reduce((s, v, i) => s + v * b[i], 0);

export function seasonWeight(latitude: number): number {
  const span = SEASON_FULL_LATITUDE - SEASON_TROPIC_LATITUDE;
  return Math.min(Math.max((Math.abs(latitude) - SEASON_TROPIC_LATITUDE) / span, 0.0), 1.0);
}

export function hemisphereDay(dayOfYear: number, latitude: number): number {
  return latitude < 0 ? pymod(dayOfYear + 182.5, 365) : dayOfYear;
}

/** Per-band IFR and hospitalisation share for this pathogen in this place. */
export function bandSeverity(pathogen: Pathogen, place: Place, c: ModelConstants): { ifr: Bands; hosp: Bands } {
  const shape = ageShape(pathogen.age_profile, place.age_means);
  const refShape = ageShape(pathogen.age_profile, c.reference_means);
  const refDot = dot(c.reference_shares, refShape);
  const refHospDot = dot(
    c.reference_shares,
    refShape.map((v) => v ** HOSP_SHAPE_POWER),
  );
  const ifr = shape.map((v, b) => {
    const base = (pathogen.ifr * v) / refDot;
    return OLDER_BANDS[b] ? base * place.severity : base;
  });
  const hosp = shape.map((v, b) => Math.max((pathogen.hosp * v ** HOSP_SHAPE_POWER) / refHospDot, ifr[b] / MAX_FATALITY_PER_STAY));
  return {
    ifr: ifr.map((v) => Math.min(v, MAX_FATALITY_PER_STAY)),
    hosp: hosp.map((v) => Math.min(v, 1.0)),
  };
}

/** [amplitude, simulation day of peak transmission] for this pathogen, place and start month. */
export function seasonalTerms(pathogen: Pathogen, place: Place, response: Response, c: ModelConstants): [number, number] {
  if (place.latitude === null) return [0.0, 0.0];
  const base = pathogen.seasonality === null ? c.covid_seasonality : pathogen.seasonality;
  const amplitude = base * seasonWeight(place.latitude);
  const startDay = MONTH_START_DAY[response.start_month - 1];
  const peak = hemisphereDay(c.season_peak_day_north, place.latitude);
  return [amplitude, pymod(peak - startDay, 365)];
}

export function stringencySeries(response: Response, days: number): number[] {
  const series = new Array<number>(days).fill(0);
  for (const seg of response.segments) {
    for (let d = Math.max(seg.start_day, 0); d < Math.min(seg.end_day, days); d++) series[d] = seg.level;
  }
  return series;
}

export function buildInputs(
  place: Place,
  pathogen: Pathogen,
  response: Response,
  days: number,
  c: ModelConstants,
  variant: Variant = NO_VARIANT,
): EngineInputs {
  const { ifr, hosp } = bandSeverity(pathogen, place, c);
  const beds = ((place.beds_per_thousand * place.population) / 1000) * place.bed_availability * (1 + response.surge);
  const npiCoef = c.npi_coef * place.adherence;
  const vaccineDay = response.vaccine ? (response.vaccine_day === null ? pathogen.vaccine_day : response.vaccine_day) : Infinity;
  const acceptance = new Array<number>(N_BANDS).fill(place.vaccine_acceptance);
  acceptance[0] *= c.child_acceptance_ratio;
  const [seasonality, seasonPeakDay] = seasonalTerms(pathogen, place, response, c);
  return {
    population: place.population,
    age_shares: [...place.age_shares],
    r0: pathogen.r0 * place.transmission,
    latent_days: pathogen.latent_days,
    infectious_days: pathogen.infectious_days,
    ifr,
    hosp,
    hosp_days: pathogen.hosp_days,
    icu_share: pathogen.icu_share,
    immunity_days: pathogen.immunity_days,
    seed_per_million: response.seed_per_million,
    seed_day: response.border_delay_days,
    seasonality,
    season_peak_day: seasonPeakDay,
    npi_coef: npiCoef,
    npi_coef_late: npiCoef * (response.fatigue ? c.fatigue_ratio : 1.0),
    fatigue_start: c.fatigue_start,
    fatigue_end: c.fatigue_end,
    isolation: response.isolation,
    awareness_deaths_pm: response.awareness ? c.awareness_deaths_pm * place.awareness : Infinity,
    awareness_power: c.awareness_power,
    stringency: stringencySeries(response, days),
    adaptive: response.adaptive ? 1 : 0,
    adaptive_on: response.adaptive_on,
    adaptive_off: response.adaptive_off,
    adaptive_level: response.adaptive_level,
    adaptive_min_days: response.adaptive_min_days,
    variant_day: variant.day,
    variant_transmission: variant.transmission,
    variant_severity: variant.severity,
    variant_escape: variant.escape,
    vaccine_day: vaccineDay,
    vaccine_capacity: place.vaccine_capacity,
    vaccine_acceptance: acceptance,
    ve_infection: pathogen.ve_infection,
    ve_death: Math.max(pathogen.ve_death, pathogen.ve_infection),
    vaccine_immunity_days: pathogen.vaccine_immunity_days,
    vaccine_oldest_first: response.vaccine_oldest_first ? 1 : 0,
    treatment_day: response.treatment_day,
    treatment_effect: response.treatment_effect * place.access,
    beds,
    icu_beds: beds * place.icu_share_of_beds,
    icu_death_share: c.icu_death_share,
    unmet_multiplier: c.unmet_multiplier,
    death_reporting: place.death_reporting,
    case_detection: response.case_detection,
  };
}
