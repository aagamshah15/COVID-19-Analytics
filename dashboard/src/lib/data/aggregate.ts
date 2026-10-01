/**
 * Browser-side aggregation. Every formula mirrors sql/analytical_queries.sql:
 *  - flows are summed over weeks and countries, skipping weeks a country didn't report;
 *  - cross-country rates are population-weighted (sum of deaths / sum of population);
 *  - cumulative metrics and vaccination are read at a single week, never averaged over time.
 * src/lib/data/aggregate.test.ts checks these against the exported SQL results.
 */
import type { Country, Dataset, Series, Value } from "./types";

export const MIN_RANKING_POPULATION = 1_000_000;

export type RegionKey = string; // "all" | "continent:<name>" | "who:<code>"

export const WHO_REGIONS: Record<string, string> = {
  AFR: "Africa",
  AMR: "Americas",
  EMR: "Eastern Mediterranean",
  EUR: "Europe",
  SEAR: "South-East Asia",
  WPR: "Western Pacific",
};

export function regionLabel(region: RegionKey): string {
  if (region === "all") return "All countries";
  const [kind, value] = region.split(":");
  return kind === "who" ? `WHO ${WHO_REGIONS[value] ?? value} region` : value;
}

export function inRegion(country: Country, region: RegionKey): boolean {
  if (region === "all") return true;
  const [kind, value] = region.split(":");
  return kind === "who" ? country.whoRegion === value : country.continent === value;
}

export function regionCountries(data: Dataset, region: RegionKey): Country[] {
  return data.countries.filter((c) => inRegion(c, region));
}

/** Inclusive [start, end] week indexes covering the date range. */
export function weekRange(weeks: string[], from: string, to: string): [number, number] {
  let start = weeks.findIndex((w) => w >= from);
  if (start < 0) start = weeks.length - 1;
  let end = weeks.length - 1;
  while (end > 0 && weeks[end] > to) end--;
  return [start, Math.max(start, end)];
}

const sum = (xs: Value[]) => xs.reduce<number>((a, x) => a + (x ?? 0), 0);

export interface AggregateWeek {
  deaths: number | null;
  cases: number | null;
  /** deaths per million among countries that reported that week */
  dpm: number | null;
  /** population-weighted fully-vaccinated share among countries with data */
  vax: number | null;
  reporting: number;
}

/** Weekly totals for a set of countries (the SQL q02/q03/q11 formulas). */
export function aggregateWeekly(data: Dataset, countries: Country[]): AggregateWeek[] {
  // A country counts as 0% vaccinated until its first report (if it ever reports), so the
  // regional share doesn't jump around while early reporters are the only ones in the average.
  const firstVax = countries.map((c) => data.series[c.iso].v.findIndex((v) => v !== null));
  return data.weeks.map((_, i) => {
    let deaths = 0;
    let cases = 0;
    let reportingPop = 0;
    let reporting = 0;
    let anyCases = false;
    let vaxNum = 0;
    let vaxPop = 0;
    for (let k = 0; k < countries.length; k++) {
      const c = countries[k];
      const s = data.series[c.iso];
      const pop = c.population ?? 0;
      const d = s.d[i];
      if (d !== null) {
        deaths += d;
        reportingPop += pop;
        reporting++;
      }
      const cs = s.c[i];
      if (cs !== null) {
        cases += cs;
        anyCases = true;
      }
      const v = s.v[i] ?? (firstVax[k] > i ? 0 : null);
      if (v !== null && pop) {
        vaxNum += v * pop;
        vaxPop += pop;
      }
    }
    return {
      deaths: reporting ? deaths : null,
      cases: anyCases ? cases : null,
      dpm: reportingPop ? (deaths * 1e6) / reportingPop : null,
      vax: vaxPop ? vaxNum / vaxPop : null,
      reporting,
    };
  });
}

export interface PeriodSummary {
  deaths: number;
  cases: number;
  cfr: number | null;
  peakIndex: number;
  peakDeaths: number;
  vaxAtEnd: number | null;
  population: number;
  deathsPerMillion: number | null;
}

export function summarisePeriod(agg: AggregateWeek[], [start, end]: [number, number], population: number): PeriodSummary {
  let deaths = 0;
  let cases = 0;
  let peakIndex = start;
  let peakDeaths = -1;
  let vaxAtEnd: number | null = null;
  for (let i = start; i <= end; i++) {
    const w = agg[i];
    deaths += w.deaths ?? 0;
    cases += w.cases ?? 0;
    if ((w.deaths ?? -1) > peakDeaths) {
      peakDeaths = w.deaths ?? 0;
      peakIndex = i;
    }
    if (w.vax !== null) vaxAtEnd = w.vax;
  }
  return {
    deaths,
    cases,
    cfr: cases ? deaths / cases : null,
    peakIndex,
    peakDeaths: Math.max(peakDeaths, 0),
    vaxAtEnd,
    population,
    deathsPerMillion: population ? (deaths * 1e6) / population : null,
  };
}

/** Last non-null value at or before index `end`. */
export function lastValue(values: Value[], end: number, start = 0): Value {
  for (let i = end; i >= start; i--) if (values[i] !== null) return values[i];
  return null;
}

export interface CountryPeriod {
  country: Country;
  deaths: number;
  deathsPerMillion: number | null;
  cumulativeDeathsPerMillion: Value;
  peakWeeklyDpm: number | null;
  peakWeek: number | null;
  vaccination: Value;
  cfr: number | null;
  reportedShare: number;
}

export function countryPeriod(data: Dataset, country: Country, [start, end]: [number, number]): CountryPeriod {
  const s: Series = data.series[country.iso];
  let deaths = 0;
  let cases = 0;
  let reported = 0;
  let peak: number | null = null;
  let peakWeek: number | null = null;
  for (let i = start; i <= end; i++) {
    const d = s.d[i];
    if (d !== null) {
      deaths += d;
      reported++;
    }
    cases += s.c[i] ?? 0;
    const dpm = s.dpm[i];
    if (dpm !== null && (peak === null || dpm > peak)) {
      peak = dpm;
      peakWeek = i;
    }
  }
  const pop = country.population ?? 0;
  return {
    country,
    deaths,
    deathsPerMillion: pop ? (deaths * 1e6) / pop : null,
    cumulativeDeathsPerMillion: lastValue(s.cdpm, end),
    peakWeeklyDpm: peak,
    peakWeek,
    vaccination: lastValue(s.v, end),
    cfr: cases ? deaths / cases : null,
    reportedShare: (reported / (end - start + 1)) || 0,
  };
}

export function population(countries: Country[]): number {
  return countries.reduce((a, c) => a + (c.population ?? 0), 0);
}

export function totalDeaths(data: Dataset, countries: Country[]): number {
  return countries.reduce((a, c) => a + sum(data.series[c.iso].d), 0);
}

/** Calendar-year totals (used by the continent small multiples). */
export function deathsPerMillionByYear(data: Dataset, countries: Country[]): { year: number; value: number }[] {
  const pop = population(countries);
  const byYear = new Map<number, number>();
  data.weeks.forEach((w, i) => {
    const year = Number(w.slice(0, 4));
    let d = 0;
    for (const c of countries) d += data.series[c.iso].d[i] ?? 0;
    byYear.set(year, (byYear.get(year) ?? 0) + d);
  });
  return [...byYear].map(([year, deaths]) => ({ year, value: pop ? (deaths * 1e6) / pop : 0 }));
}
