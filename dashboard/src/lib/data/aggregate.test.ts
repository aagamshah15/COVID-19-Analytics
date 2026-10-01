/**
 * Parity tests: the browser's aggregation must reproduce the SQL pack's numbers.
 * Runs against the real exported data (generate it with `covid-pipeline web-export`).
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  aggregateWeekly,
  countryPeriod,
  population,
  regionCountries,
  summarisePeriod,
  totalDeaths,
  weekRange,
} from "./aggregate";
import type { Country, Dataset } from "./types";

const dir = resolve(__dirname, "../../../public/data");
const read = (name: string) => JSON.parse(readFileSync(resolve(dir, name), "utf8"));

function dataset(): Dataset {
  const weekly = read("weekly.json");
  const countries: Country[] = read("countries.json").filter((c: Country) => weekly.series[c.iso]);
  return {
    weeks: weekly.weeks,
    countries,
    byIso: new Map(countries.map((c) => [c.iso, c])),
    series: weekly.series,
    forecast: read("forecast.json"),
    model: read("model.json"),
    quality: read("quality.json"),
    sql: read("sql.json"),
  };
}

const data = dataset();
const all = regionCountries(data, "all");
const close = (a: number, b: number, rel = 1e-6) => expect(Math.abs(a - b)).toBeLessThanOrEqual(Math.abs(b) * rel + 1e-6);

describe("aggregation matches the SQL pack", () => {
  it("q01: total deaths and countries", () => {
    const kpi = data.sql.q01_executive_kpis[0];
    close(totalDeaths(data, all), kpi.total_deaths as number);
    const agg = aggregateWeekly(data, all);
    const s = summarisePeriod(agg, [0, data.weeks.length - 1], population(all));
    close(s.deaths, kpi.total_deaths as number);
    close(s.cases, kpi.total_cases as number);
    close(s.vaxAtEnd!, kpi.fully_vaccinated_share_at_end as number, 1e-3);
  });

  it("q02/q05: weekly global deaths and the deadliest week", () => {
    const agg = aggregateWeekly(data, all);
    for (const row of data.sql.q02_global_weekly_trend) {
      const i = data.weeks.indexOf(String(row.week_end));
      close(agg[i].deaths ?? 0, row.global_deaths as number);
    }
    const s = summarisePeriod(agg, [0, data.weeks.length - 1], population(all));
    expect(data.weeks[s.peakIndex]).toBe(String(data.sql.q05_deadliest_global_weeks[0].week_end));
  });

  it("q03: population-weighted weekly deaths per million among reporting countries", () => {
    const agg = aggregateWeekly(data, all);
    for (const row of data.sql.q03_global_deaths_per_million_weekly) {
      const i = data.weeks.indexOf(String(row.week_end));
      close(agg[i].dpm!, row.deaths_per_million as number, 1e-3);
      expect(agg[i].reporting).toBe(row.reporting_countries);
    }
  });

  it("q08: continent deaths", () => {
    for (const row of data.sql.q08_continent_burden) {
      const countries = regionCountries(data, `continent:${row.continent}`);
      close(totalDeaths(data, countries), row.deaths as number);
      close((totalDeaths(data, countries) * 1e6) / population(countries), row.deaths_per_million as number, 1e-3);
    }
  });

  it("q09: WHO region deaths", () => {
    for (const row of data.sql.q09_who_region_burden.filter((r) => r.who_region !== "Not assigned")) {
      close(totalDeaths(data, regionCountries(data, `who:${row.who_region}`)), row.deaths as number);
    }
  });

  it("q06: end-of-window cumulative deaths per million per country", () => {
    const end = data.weeks.length - 1;
    for (const row of data.sql.q06_top_countries_cumulative_deaths_per_million) {
      const c = data.countries.find((x) => x.name === row.country_name)!;
      close(countryPeriod(data, c, [0, end]).cumulativeDeathsPerMillion!, row.cumulative_deaths_per_million as number, 1e-3);
    }
  });

  it("q07: peak weekly deaths per million per country", () => {
    const end = data.weeks.length - 1;
    for (const row of data.sql.q07_peak_weekly_deaths_per_million) {
      const c = data.countries.find((x) => x.name === row.country_name)!;
      const p = countryPeriod(data, c, [0, end]);
      close(p.peakWeeklyDpm!, row.weekly_deaths_per_million as number, 1e-3);
      expect(data.weeks[p.peakWeek!]).toBe(String(row.peak_week));
    }
  });

  it("weekRange is inclusive and clamps", () => {
    const [a, b] = weekRange(data.weeks, "2021-01-01", "2021-12-31");
    expect(data.weeks[a] >= "2021-01-01").toBe(true);
    expect(data.weeks[b] <= "2021-12-31").toBe(true);
    expect(data.weeks[b + 1] > "2021-12-31").toBe(true);
    expect(weekRange(data.weeks, "1999-01-01", "2099-01-01")).toEqual([0, data.weeks.length - 1]);
  });
});
