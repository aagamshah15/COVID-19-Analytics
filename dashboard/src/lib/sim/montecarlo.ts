/**
 * Monte Carlo uncertainty, the no-response counterfactual and one-at-a-time sensitivity.
 *
 * Each draw perturbs the uncertain inputs with the spreads exported by training (smaller for
 * values calibrated or observed for this country, larger for model predictions; none for values
 * the visitor set by hand) and reruns the engine. Bands are per-day (and per-week) quantiles
 * across draws; summaries are quantiles of per-draw totals, never sums of quantiles.
 */
import { type EngineOutputs, run } from "./engine";
import type { SimModel, Source } from "./model";
import { buildInputs, DEFAULT_RESPONSE, type ModelConstants, type Pathogen, type Place, type Response, type Variant } from "./scenario";

export type ValueSource = Source | "user";
export interface ScenarioRun {
  place: Place;
  /** Where each learned place value came from; "user" values carry no uncertainty. */
  sources: Record<"transmission" | "severity" | "awareness" | "reporting" | "vaccine_acceptance" | "vaccine_capacity", ValueSource>;
  pathogen: Pathogen;
  response: Response;
  variant: Variant;
  constants: ModelConstants;
  uncertainty: SimModel["uncertainty"];
  days: number;
}

export const BAND_SERIES = ["infections", "reported_cases", "admissions", "hospital", "icu", "deaths", "reported_deaths", "dead", "rt", "vaccinated", "susceptible", "immune"] as const;
export type BandSeries = (typeof BAND_SERIES)[number];
const FLOWS = new Set<BandSeries>(["infections", "reported_cases", "admissions", "deaths", "reported_deaths"]);
export const QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95] as const;

export interface Summary {
  deaths: number;
  reported_deaths: number;
  infections: number;
  attack_rate: number;
  peak_hospital: number;
  peak_hospital_day: number;
  days_over_capacity: number;
  peak_deaths_day: number;
  vaccinated: number;
}

export interface EnsembleResult {
  central: EngineOutputs;
  capacity: number;
  bands: { daily: Record<BandSeries, number[][]>; weekly: Record<BandSeries, number[][]> };
  summary: { central: Summary; quantiles: Record<keyof Summary, number[]> };
  noResponse: Summary;
  draws: number;
  ms: number;
}

/** Small, fast, seedable PRNG (mulberry32) with Box-Muller normals. */
export function rng(seed: number) {
  let a = seed >>> 0;
  const uniform = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return {
    uniform,
    normal: () => {
      const u = Math.max(uniform(), 1e-12);
      return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * uniform());
    },
  };
}

const logit = (p: number) => Math.log(Math.min(Math.max(p, 1e-6), 1 - 1e-6) / (1 - Math.min(Math.max(p, 1e-6), 1 - 1e-6)));
const expit = (x: number) => 1 / (1 + Math.exp(-x));

function spread(source: ValueSource, sd: { calibrated?: number; observed?: number; predicted: number }): number {
  if (source === "user") return 0;
  if (source === "predicted") return sd.predicted;
  return sd.calibrated ?? sd.observed ?? sd.predicted;
}

/** Log-normal and logit-normal jitter; a zero spread returns the value untouched. */
const onLog = (v: number, z: number, sd: number) => (sd > 0 ? v * Math.exp(z * sd) : v);
const onLogit = (p: number, z: number, sd: number) => (sd > 0 ? expit(logit(p) + z * sd) : p);

/** One random draw of every uncertain input. */
export function perturb(s: ScenarioRun, normal: () => number): ScenarioRun {
  const u = s.uncertainty;
  const place = { ...s.place };
  place.transmission = onLog(place.transmission, normal(), spread(s.sources.transmission, u.log_transmission_sd));
  place.severity = onLog(place.severity, normal(), spread(s.sources.severity, u.log_severity_sd));
  place.awareness = onLog(place.awareness, normal(), spread(s.sources.awareness, u.log_awareness_country_sd));
  place.death_reporting = onLogit(place.death_reporting, normal(), spread(s.sources.reporting, u.logit_reporting_sd));
  place.vaccine_acceptance = onLogit(place.vaccine_acceptance, normal(), spread(s.sources.vaccine_acceptance, u.logit_vaccine_acceptance_sd));
  place.vaccine_capacity = onLog(place.vaccine_capacity, normal(), spread(s.sources.vaccine_capacity, u.log_vaccine_capacity_sd));
  const constants = { ...s.constants };
  constants.npi_coef += normal() * u.npi_coef_sd;
  if (Number.isFinite(constants.awareness_deaths_pm) && u.log_awareness_sd) constants.awareness_deaths_pm *= Math.exp(normal() * u.log_awareness_sd);
  constants.covid_seasonality = Math.min(1, Math.max(0, constants.covid_seasonality + normal() * u.seasonality_sd));
  const pathogen = { ...s.pathogen, r0: s.pathogen.r0 * Math.exp(normal() * u.log_r0_sd), ifr: s.pathogen.ifr * Math.exp(normal() * u.log_ifr_sd) };
  return { ...s, place, constants, pathogen };
}

export function simulate(s: ScenarioRun): EngineOutputs {
  return run(buildInputs(s.place, s.pathogen, s.response, s.days, s.constants, s.variant), s.days);
}

/** Hospital beds available to the epidemic (the capacity line on charts). */
export function capacityOf(s: ScenarioRun): number {
  return ((s.place.beds_per_thousand * s.place.population) / 1000) * s.place.bed_availability * (1 + s.response.surge);
}

export function summarise(out: EngineOutputs, population: number, capacity: number): Summary {
  let deaths = 0, reported = 0, infections = 0, over = 0, peakH = 0, peakHDay = 0, peakD = 0, peakDDay = 0;
  for (let d = 0; d < out.deaths.length; d++) {
    deaths += out.deaths[d];
    reported += out.reported_deaths[d];
    infections += out.infections[d];
    if (out.hospital[d] > capacity) over++;
    if (out.hospital[d] > peakH) [peakH, peakHDay] = [out.hospital[d], d];
    if (out.deaths[d] > peakD) [peakD, peakDDay] = [out.deaths[d], d];
  }
  return {
    deaths,
    reported_deaths: reported,
    infections,
    attack_rate: infections / population,
    peak_hospital: peakH,
    peak_hospital_day: peakHDay,
    days_over_capacity: over,
    peak_deaths_day: peakDDay,
    vaccinated: out.vaccinated[out.vaccinated.length - 1] ?? 0,
  };
}

/** The same place and disease with no policy response (people still react to deaths). */
export function withoutResponse(s: ScenarioRun): ScenarioRun {
  return { ...s, response: { ...DEFAULT_RESPONSE, vaccine: false, start_month: s.response.start_month, seed_per_million: s.response.seed_per_million } };
}

function weekly(values: Float64Array, flow: boolean): number[] {
  const out: number[] = [];
  for (let w = 0; w * 7 < values.length; w++) {
    const chunk = values.subarray(w * 7, Math.min(values.length, w * 7 + 7));
    if (flow) out.push(chunk.reduce((a, b) => a + b, 0));
    else out.push(chunk[chunk.length - 1]);
  }
  return out;
}

function quantile(sorted: Float64Array, q: number): number {
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

/** Per-time-step quantiles across draws: result[q][t]. */
function bandsOf(samples: number[][]): number[][] {
  const steps = samples[0].length;
  const out = QUANTILES.map(() => new Array<number>(steps));
  const column = new Float64Array(samples.length);
  for (let t = 0; t < steps; t++) {
    for (let i = 0; i < samples.length; i++) column[i] = samples[i][t];
    column.sort();
    QUANTILES.forEach((q, k) => (out[k][t] = quantile(column, q)));
  }
  return out;
}

export function ensemble(s: ScenarioRun, draws = 200, seed = 1): EnsembleResult {
  const started = performance.now();
  const capacity = capacityOf(s);
  const central = simulate(s);
  const daily = Object.fromEntries(BAND_SERIES.map((k) => [k, [] as number[][]])) as Record<BandSeries, number[][]>;
  const week = Object.fromEntries(BAND_SERIES.map((k) => [k, [] as number[][]])) as Record<BandSeries, number[][]>;
  const summaries: Summary[] = [];
  const r = rng(seed);
  for (let i = 0; i < draws; i++) {
    const draw = perturb(s, r.normal);
    const out = simulate(draw);
    for (const k of BAND_SERIES) {
      daily[k].push(Array.from(out[k]));
      week[k].push(weekly(out[k], FLOWS.has(k)));
    }
    summaries.push(summarise(out, s.place.population, capacityOf(draw)));
  }
  const keys = Object.keys(summaries[0]) as (keyof Summary)[];
  const quantiles = Object.fromEntries(
    keys.map((k) => {
      const sorted = Float64Array.from(summaries.map((x) => x[k])).sort();
      return [k, QUANTILES.map((q) => quantile(sorted, q))];
    }),
  ) as Record<keyof Summary, number[]>;
  return {
    central,
    capacity,
    bands: {
      daily: Object.fromEntries(BAND_SERIES.map((k) => [k, bandsOf(daily[k])])) as Record<BandSeries, number[][]>,
      weekly: Object.fromEntries(BAND_SERIES.map((k) => [k, bandsOf(week[k])])) as Record<BandSeries, number[][]>,
    },
    summary: { central: summarise(central, s.place.population, capacity), quantiles },
    noResponse: summarise(simulate(withoutResponse(s)), s.place.population, capacity),
    draws,
    ms: performance.now() - started,
  };
}

// --------------------------------------------------------------------------- sensitivity

export interface TornadoBar {
  key: string;
  label: string;
  low: number;
  high: number;
  lowLabel: string;
  highLabel: string;
}

/** One-at-a-time sensitivity of total deaths: each input pushed to a plausible low and high value. */
export function sensitivity(s: ScenarioRun): { base: number; bars: TornadoBar[] } {
  const deaths = (x: ScenarioRun) => summarise(simulate(x), x.place.population, capacityOf(x)).deaths;
  const base = deaths(s);
  const u = s.uncertainty;
  const cases: { key: string; label: string; lowLabel: string; highLabel: string; low: ScenarioRun; high: ScenarioRun; when?: boolean }[] = [
    { key: "r0", label: "How contagious (R0)", lowLabel: "−20%", highLabel: "+20%", low: { ...s, pathogen: { ...s.pathogen, r0: s.pathogen.r0 * 0.8 } }, high: { ...s, pathogen: { ...s.pathogen, r0: s.pathogen.r0 * 1.2 } } },
    { key: "ifr", label: "How deadly (IFR)", lowLabel: "÷1.5", highLabel: "×1.5", low: { ...s, pathogen: { ...s.pathogen, ifr: s.pathogen.ifr / 1.5 } }, high: { ...s, pathogen: { ...s.pathogen, ifr: s.pathogen.ifr * 1.5 } } },
    sdCase(s, "transmission", "Country transmission (learned)", spread(s.sources.transmission, u.log_transmission_sd)),
    sdCase(s, "severity", "Country severity (learned)", spread(s.sources.severity, u.log_severity_sd)),
    { key: "npi", label: "Lockdown effectiveness", lowLabel: "half", highLabel: "×1.5", low: { ...s, constants: { ...s.constants, npi_coef: s.constants.npi_coef * 0.5 } }, high: { ...s, constants: { ...s.constants, npi_coef: s.constants.npi_coef * 1.5 } }, when: s.response.segments.length > 0 || s.response.adaptive },
    { key: "awareness", label: "Public caution as deaths rise", lowLabel: "less", highLabel: "more", low: { ...s, constants: { ...s.constants, awareness_deaths_pm: s.constants.awareness_deaths_pm * 2 } }, high: { ...s, constants: { ...s.constants, awareness_deaths_pm: s.constants.awareness_deaths_pm / 2 } }, when: s.response.awareness && Number.isFinite(s.constants.awareness_deaths_pm) },
    { key: "beds", label: "Hospital beds", lowLabel: "half", highLabel: "double", low: { ...s, place: { ...s.place, beds_per_thousand: s.place.beds_per_thousand / 2 } }, high: { ...s, place: { ...s.place, beds_per_thousand: s.place.beds_per_thousand * 2 } } },
    { key: "vaccine_day", label: "Vaccine arrival", lowLabel: "90 days later", highLabel: "90 days sooner", low: shiftVaccine(s, 90), high: shiftVaccine(s, -90), when: s.response.vaccine },
    { key: "acceptance", label: "Vaccine acceptance", lowLabel: "−15 pts", highLabel: "+15 pts", low: { ...s, place: { ...s.place, vaccine_acceptance: Math.max(0, s.place.vaccine_acceptance - 0.15) } }, high: { ...s, place: { ...s.place, vaccine_acceptance: Math.min(1, s.place.vaccine_acceptance + 0.15) } }, when: s.response.vaccine },
    { key: "stringency", label: "Lockdown strictness", lowLabel: "−20 pts", highLabel: "+20 pts", low: shiftStringency(s, -20), high: shiftStringency(s, 20), when: s.response.segments.length > 0 },
  ];
  const bars = cases
    .filter((c) => c.when !== false)
    .map((c) => ({ key: c.key, label: c.label, lowLabel: c.lowLabel, highLabel: c.highLabel, low: deaths(c.low), high: deaths(c.high) }))
    .sort((a, b) => Math.abs(b.high - b.low) - Math.abs(a.high - a.low));
  return { base, bars };
}

function sdCase(s: ScenarioRun, key: "transmission" | "severity", label: string, sd: number) {
  const f = Math.exp(Math.max(sd, 0.1));
  return { key, label, lowLabel: "−1 sd", highLabel: "+1 sd", low: { ...s, place: { ...s.place, [key]: s.place[key] / f } }, high: { ...s, place: { ...s.place, [key]: s.place[key] * f } } };
}

function shiftVaccine(s: ScenarioRun, days: number): ScenarioRun {
  const current = s.response.vaccine_day ?? s.pathogen.vaccine_day;
  return { ...s, response: { ...s.response, vaccine_day: Number.isFinite(current) ? Math.max(0, current + days) : current } };
}

function shiftStringency(s: ScenarioRun, points: number): ScenarioRun {
  return { ...s, response: { ...s.response, segments: s.response.segments.map((g) => ({ ...g, level: Math.min(100, Math.max(0, g.level + points)) })) } };
}
