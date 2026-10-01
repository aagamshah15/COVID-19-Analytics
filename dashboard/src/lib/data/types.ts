export type Value = number | null;

/** Per-country weekly series, keyed as exported by `covid-pipeline web-export`. */
export interface Series {
  d: Value[]; // new deaths (null = not reported)
  c: Value[]; // new cases
  dpm: Value[]; // weekly deaths per million
  cdpm: Value[]; // cumulative deaths per million
  cfr: Value[]; // cumulative case fatality rate
  v1: Value[]; // at least one dose, share of population
  v: Value[]; // fully vaccinated share
  vb: Value[]; // boosters per person
  h: Value[]; // hospital patients per million
  icu: Value[]; // ICU patients per million
  occ: Value[]; // share of hospital beds occupied by COVID-19 patients
}

export interface Country {
  iso: string;
  numeric: string | null;
  name: string;
  continent: string | null;
  whoRegion: string | null;
  population: number | null;
  beds: number | null;
  medianAge: number | null;
  gdp: number | null;
}

export interface ForecastPoint {
  week: string;
  h: number;
  p: number;
  lo: number;
  hi: number;
}

export interface CountryForecast {
  origin: string;
  focus: boolean;
  points: ForecastPoint[];
}

export interface Score {
  mae_deaths: number;
  mae_naive_deaths: number;
  wape: number | null;
  skill_vs_naive: number | null;
  n: number;
}

export interface ModelReport {
  model: string;
  method: string;
  target: string;
  horizon_weeks: number;
  origin_date: string;
  focus_countries: Record<string, string>;
  training_universe: string;
  not_forecast_reporting_stopped: string[];
  baseline: string;
  interval: string;
  backtest: {
    folds: number;
    fold_weeks: number;
    first_cutoff: string;
    all_countries: Score;
    focus_countries: Score;
    by_horizon_focus: Record<string, Score>;
    by_country: Record<string, Score>;
  };
  permutation_importance_h1: Record<string, number>;
}

export interface QualityCheck {
  name: string;
  severity: "error" | "warn";
  passed: boolean;
  observed: string;
  expectation: string;
}

export interface Quality {
  generatedAt: string;
  checks: QualityCheck[];
  sources: Record<string, { url: string; path: string; fetched_at_utc: string; bytes: number; sha256: string }>;
}

export type SqlRow = Record<string, string | number | boolean | null>;

export interface Dataset {
  weeks: string[];
  countries: Country[];
  byIso: Map<string, Country>;
  series: Record<string, Series>;
  forecast: Record<string, CountryForecast>;
  model: ModelReport;
  quality: Quality;
  sql: Record<string, SqlRow[]>;
}
