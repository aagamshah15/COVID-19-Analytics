import type { Country, CountryForecast, Dataset, ModelReport, Quality, Series, SqlRow } from "./types";

async function getJson<T>(name: string): Promise<T> {
  const res = await fetch(`${import.meta.env.BASE_URL}data/${name}`);
  if (!res.ok) throw new Error(`Couldn't load ${name} (HTTP ${res.status}). Run \`covid-pipeline web-export\` to generate it.`);
  return res.json() as Promise<T>;
}

export async function loadDataset(): Promise<Dataset> {
  const [weekly, countries, forecast, model, quality, sql] = await Promise.all([
    getJson<{ weeks: string[]; series: Record<string, Series> }>("weekly.json"),
    getJson<Country[]>("countries.json"),
    getJson<Record<string, CountryForecast>>("forecast.json"),
    getJson<ModelReport>("model.json"),
    getJson<Quality>("quality.json"),
    getJson<Record<string, SqlRow[]>>("sql.json"),
  ]);
  // Only countries with a weekly series take part in the dashboard.
  const withSeries = countries.filter((c) => weekly.series[c.iso]);
  return {
    weeks: weekly.weeks,
    countries: withSeries,
    byIso: new Map(withSeries.map((c) => [c.iso, c])),
    series: weekly.series,
    forecast,
    model,
    quality,
    sql,
  };
}
