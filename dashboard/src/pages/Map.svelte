<script lang="ts">
  import ChartFrame from "../components/ChartFrame.svelte";
  import Controls from "../components/Controls.svelte";
  import Choropleth from "../lib/charts/Choropleth.svelte";
  import LineChart from "../lib/charts/LineChart.svelte";
  import RankBars from "../lib/charts/RankBars.svelte";
  import {
    aggregateWeekly,
    countryPeriod,
    inRegion,
    MIN_RANKING_POPULATION,
    regionCountries,
    regionLabel,
    weekRange,
    type CountryPeriod,
  } from "../lib/data/aggregate";
  import type { Dataset } from "../lib/data/types";
  import { count, day, perMillion, pct } from "../lib/format";
  import { app } from "../lib/state/app.svelte";

  let { data }: { data: Dataset } = $props();

  type MetricId = "period" | "cumulative" | "peak" | "vax" | "cfr";
  let metricId = $state<MetricId>("period");
  let range = $derived(weekRange(data.weeks, app.from, app.to));
  let periodText = $derived(app.isWholePeriod ? "2020–2023" : `${day(data.weeks[range[0]])} to ${day(data.weeks[range[1]])}`);

  let metrics = $derived({
    period: {
      label: app.measure === "abs" ? "Deaths in the period" : "Deaths per million in the period",
      short: app.measure === "abs" ? "deaths" : "deaths per million",
      color: "var(--deaths)",
      get: (p: CountryPeriod) => (app.measure === "abs" ? p.deaths : p.deathsPerMillion),
      format: (v: number) => (app.measure === "abs" ? count(v) : perMillion(v)),
    },
    cumulative: {
      label: "Cumulative deaths per million at the end of the period",
      short: "cumulative deaths per million",
      color: "var(--deaths)",
      get: (p: CountryPeriod) => p.cumulativeDeathsPerMillion,
      format: perMillion,
    },
    peak: {
      label: "Deadliest single week, deaths per million",
      short: "peak weekly deaths per million",
      color: "var(--deaths)",
      get: (p: CountryPeriod) => p.peakWeeklyDpm,
      format: perMillion,
    },
    vax: {
      label: "Fully vaccinated at the end of the period",
      short: "fully vaccinated",
      color: "var(--vax)",
      get: (p: CountryPeriod) => p.vaccination,
      format: (v: number) => pct(v),
    },
    cfr: {
      label: "Deaths per recorded case in the period",
      short: "case fatality rate",
      color: "var(--deaths)",
      get: (p: CountryPeriod) => (p.cfr !== null && p.cfr <= 1 ? p.cfr : null),
      format: (v: number) => pct(v, 1),
    },
  } as const);
  let metric = $derived(metrics[metricId]);

  let periods = $derived(data.countries.map((c) => countryPeriod(data, c, range)));
  let values = $derived(new Map(periods.filter((p) => p.country.numeric).map((p) => [p.country.numeric!, metric.get(p)])));
  let names = $derived(new Map(data.countries.filter((c) => c.numeric).map((c) => [c.numeric!, { iso: c.iso, name: c.name }])));
  let byNumeric = $derived(new Map(data.countries.filter((c) => c.numeric).map((c) => [c.numeric!, c])));

  let ranked = $derived(
    periods
      .filter((p) => inRegion(p.country, app.region) && (p.country.population ?? 0) >= MIN_RANKING_POPULATION)
      .map((p) => ({ p, v: metric.get(p) }))
      .filter((r): r is { p: CountryPeriod; v: number } => r.v !== null && r.v !== undefined)
      .sort((a, b) => b.v - a.v),
  );
  let top = $derived(ranked.slice(0, 15).map(({ p, v }) => ({ key: p.country.iso, label: p.country.name, value: v, note: p.country.continent ?? "" })));

  const CONTINENTS = ["South America", "Europe", "North America", "Asia", "Oceania", "Africa"];
  let regional = $derived(CONTINENTS.map((c) => ({ name: c, agg: aggregateWeekly(data, regionCountries(data, `continent:${c}`)) })));
  let regionalMax = $derived(Math.max(...regional.flatMap((r) => r.agg.map((w) => w.dpm ?? 0))));
  let activeContinent = $derived(app.region.startsWith("continent:") ? app.region.split(":")[1] : null);
</script>

<Controls {data} />

<header class="hero">
  <h1>Where the burden fell hardest</h1>
  <p class="lede">
    Reported COVID-19 mortality by country, {periodText}{app.region === "all" ? "" : `, ${regionLabel(app.region)}`}. Select a country for its full
    profile.
  </p>
</header>

<div class="metric seg" role="group" aria-label="Map metric">
  {#each Object.entries(metrics) as [id, m]}
    <button aria-pressed={metricId === id} onclick={() => (metricId = id as MetricId)}>{m.short.replace(/^./, (c) => c.toUpperCase())}</button>
  {/each}
</div>

<div class="grid-7-5 maprow">
  <ChartFrame
    title={metric.label}
    subtitle="Darker means higher. Classes are sixths of the countries shown; grey means no data for the period."
    columns={[
      { key: "name", label: "Country" },
      { key: "continent", label: "Continent" },
      { key: "value", label: metric.short, numeric: true, format: (v) => (v === null ? "–" : metric.format(v as number)) },
    ]}
    rows={periods
      .filter((p) => inRegion(p.country, app.region))
      .map((p) => ({ name: p.country.name, continent: p.country.continent, value: metric.get(p) }))
      .sort((a, b) => (b.value ?? -1) - (a.value ?? -1))}
  >
    <Choropleth
      {values}
      {names}
      inRegion={(numeric) => {
        const c = byNumeric.get(numeric);
        return c ? inRegion(c, app.region) : app.region === "all";
      }}
      color={metric.color}
      metric={metricId === "vax" ? "vax" : "deaths"}
      format={metric.format}
      metricLabel={metric.short}
      onpick={(iso) => app.go("country", iso)}
      ariaLabel={`World map of ${metric.short}, ${periodText}. The ranking and table views list the same values.`}
    />
  </ChartFrame>

  <ChartFrame
    title={`Highest ${metric.short}`}
    subtitle={`Countries with at least 1 million people${app.region === "all" ? "" : ` in ${regionLabel(app.region)}`}. Select one to open its profile.`}
    query={metricId === "cumulative" && app.isWholePeriod ? "q06_top_countries_cumulative_deaths_per_million" : metricId === "peak" && app.isWholePeriod ? "q07_peak_weekly_deaths_per_million" : undefined}
  >
    {#if top.length}
      <RankBars items={top} color={metric.color} format={metric.format} onpick={(iso) => app.go("country", iso)} />
    {:else}
      <p class="empty">No country in this region reported data for the period. Choose a longer period or another region.</p>
    {/if}
  </ChartFrame>
</div>

<div class="section">
  <ChartFrame
    title="Each continent's waves came at different times"
    subtitle="Weekly reported deaths per million, population-weighted. Same scale in every panel; the selected period is unshaded."
    query="q03_global_deaths_per_million_weekly"
  >
    <div class="multiples">
      {#each regional as r}
        <div class:faded={activeContinent && activeContinent !== r.name}>
          <h3>{r.name}</h3>
          <LineChart
            x={data.weeks}
            series={[{ id: r.name, label: r.name, values: r.agg.map((w) => w.dpm), color: "var(--deaths)" }]}
            height={130}
            yMax={regionalMax}
            format={perMillion}
            highlight={app.isWholePeriod ? null : range}
            hatchGaps={false}
            compact
            ariaLabel={`${r.name}: weekly deaths per million`}
          />
        </div>
      {/each}
    </div>
  </ChartFrame>
</div>

<style>
  .hero {
    margin-top: 34px;
  }
  .metric {
    margin-top: 26px;
    max-width: 100%;
    overflow-x: auto;
  }
  .maprow {
    margin-top: 22px;
  }
  .multiples {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 18px 28px;
  }
  .multiples h3 {
    font-size: 14px;
    font-weight: 500;
  }
  .faded {
    opacity: 0.45;
  }
  @media (max-width: 760px) {
    .multiples {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
