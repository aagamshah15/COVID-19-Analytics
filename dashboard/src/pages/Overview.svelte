<script lang="ts">
  import ChartFrame from "../components/ChartFrame.svelte";
  import Controls from "../components/Controls.svelte";
  import Spine from "../components/Spine.svelte";
  import Stat from "../components/Stat.svelte";
  import BarChart from "../lib/charts/BarChart.svelte";
  import {
    aggregateWeekly,
    deathsPerMillionByYear,
    population,
    regionCountries,
    regionLabel,
    summarisePeriod,
    weekRange,
  } from "../lib/data/aggregate";
  import type { Dataset } from "../lib/data/types";
  import { big, count, day, perMillion, pct } from "../lib/format";
  import { app } from "../lib/state/app.svelte";

  let { data }: { data: Dataset } = $props();

  let countries = $derived(regionCountries(data, app.region));
  let agg = $derived(aggregateWeekly(data, countries));
  let range = $derived(weekRange(data.weeks, app.from, app.to));
  let summary = $derived(summarisePeriod(agg, range, population(countries)));
  let place = $derived(app.region === "all" ? "worldwide" : `in ${regionLabel(app.region)}`);
  let periodText = $derived(app.isWholePeriod ? "between January 2020 and December 2023" : `between ${day(data.weeks[range[0]])} and ${day(data.weeks[range[1]])}`);
  let deaths = $derived(big(summary.deaths));

  // Findings come straight from the SQL pack results.
  let peakRow = $derived(data.sql.q05_deadliest_global_weeks[0]);
  let cfr = $derived(data.sql.q12_cfr_by_quarter);
  let cfrLow = $derived(Math.min(...cfr.filter((r) => r.year === 2022).map((r) => r.cfr as number)));
  let peakVax = $derived(aggregateWeekly(data, data.countries)[data.weeks.indexOf(String(peakRow.week_end))]?.vax ?? 0);
  // Quote the quality gate's own count so the two pages can never disagree.
  let stopped = $derived(Number(data.quality.checks.find((c) => c.name === "death_reporting_active_at_end")?.observed.match(/\d+/)?.[0] ?? 0));

  let quarterBars = $derived(
    cfr.map((r) => {
      const qEnd = `${r.year}-${String((r.quarter as number) * 3).padStart(2, "0")}-31`;
      const qStart = `${r.year}-${String((r.quarter as number) * 3 - 2).padStart(2, "0")}-01`;
      return {
        key: `${r.year}Q${r.quarter}`,
        value: r.cfr as number,
        tick: r.quarter === 1 ? String(r.year) : undefined,
        title: `${r.year} Q${r.quarter}`,
        dim: !app.isWholePeriod && (qEnd < app.from || qStart > app.to),
        label: (r.year === 2020 && r.quarter === 1) || (r.year === 2022 && r.quarter === 4),
      };
    }),
  );

  const CONTINENTS = ["South America", "Europe", "North America", "Asia", "Oceania", "Africa"];
  let multiples = $derived(
    CONTINENTS.map((name) => ({ name, years: deathsPerMillionByYear(data, regionCountries(data, `continent:${name}`)) })),
  );
  let multiplesMax = $derived(Math.max(...multiples.flatMap((m) => m.years.map((y) => y.value))) * 1.12);
  let activeContinent = $derived(app.region.startsWith("continent:") ? app.region.split(":")[1] : null);
</script>

<Controls {data} />

<header class="hero">
  <h1>Four years of COVID-19,<br />week by week</h1>
  <p class="lede">
    {count(summary.deaths)} deaths were reported {place} {periodText}{#if summary.cfr !== null}, about {pct(summary.cfr, 1)} of recorded cases{/if}.
    {#if app.isWholePeriod && app.region === "all"}The true toll was higher: many deaths were never tested or registered.{/if}
  </p>
</header>

<div class="spine-wrap">
  <Spine
    weeks={data.weeks}
    {agg}
    measure={app.measure}
    {range}
    onselect={(from, to) => app.set({ from, to })}
    label={`Weekly reported COVID-19 deaths ${place}, ${app.measure === "abs" ? "absolute" : "per million people"}, with vaccination coverage and variant eras`}
  />
  <p class="hint">Drag across the chart to choose a period. Every page uses it.</p>
</div>

<div class="stats">
  <Stat value={deaths.value} unit={deaths.unit} label={`deaths reported ${place} in the period`} color="var(--deaths)" />
  <Stat value={perMillion(summary.deathsPerMillion)} label="deaths per million people" color="var(--deaths)" />
  <Stat value={count(summary.peakDeaths)} label={`in the deadliest week, ending ${day(data.weeks[summary.peakIndex])}`} color="var(--deaths)" />
  <Stat value={pct(summary.vaxAtEnd)} label="fully vaccinated by the end of the period" color="var(--vax)" />
</div>

<section class="findings" aria-label="Key findings">
  <article>
    <h2>The deadliest week came before most people could be vaccinated</h2>
    <p>
      {count(peakRow.global_deaths as number)} deaths were reported worldwide in the week ending {day(String(peakRow.week_end))}, when
      {pct(peakVax, 1)} of the world was fully vaccinated.
    </p>
    <a href={app.link("map")} onclick={() => app.set({ from: "2021-01-01", to: "2021-12-31" })}>See 2021 on the map</a>
  </article>
  <article>
    <h2>Severity fell about {Math.round((cfr[0].cfr as number) / cfrLow)}-fold</h2>
    <p>
      Deaths per recorded case dropped from {pct(cfr[0].cfr as number, 1)} in early 2020 to {pct(cfrLow, 2)} in 2022, as immunity, treatment and
      milder variants arrived.
    </p>
    <a href={app.link("vaccines")}>Explore vaccines and severity</a>
  </article>
  <article>
    <h2>The data thinned out long before the virus did</h2>
    <p>{stopped} countries had stopped reporting deaths by the end of 2023. Those weeks are shown as gaps, never as zero.</p>
    <a href={app.link("data")}>See reporting coverage</a>
  </article>
</section>

<div class="section grid-5-7">
  <ChartFrame
    title="Deaths per recorded case fell through 2022"
    subtitle="Case fatality rate by quarter, all countries. The 2023 rise reflects testing collapse more than deadlier disease."
    query="q12_cfr_by_quarter"
    columns={[
      { key: "year", label: "Year" },
      { key: "quarter", label: "Quarter" },
      { key: "cfr", label: "Case fatality rate", numeric: true, format: (v) => pct(v as number, 2) },
    ]}
    rows={cfr}
  >
    <BarChart bars={quarterBars} color="var(--deaths)" height={240} max={0.06} min={0} ticks={[0, 0.02, 0.04, 0.06]} format={(v) => pct(v, v < 0.01 ? 1 : 1)} ariaLabel="Case fatality rate by quarter, 2020 to 2023" />
  </ChartFrame>

  <ChartFrame
    title="The Americas and Europe bore the heaviest reported toll"
    subtitle="Reported deaths per million people, by continent and year. Same scale in every panel."
    query="q08_continent_burden"
    columns={[
      { key: "continent", label: "Continent" },
      { key: "year", label: "Year" },
      { key: "value", label: "Deaths per million", numeric: true, format: (v) => perMillion(v as number) },
    ]}
    rows={multiples.flatMap((m) => m.years.map((y) => ({ continent: m.name, ...y })))}
  >
    <div class="multiples">
      {#each multiples as m}
        <div class:active={activeContinent === m.name} class:faded={activeContinent && activeContinent !== m.name}>
          <h3>{m.name}</h3>
          <BarChart
            bars={m.years.map((y) => ({
              key: String(y.year),
              value: y.value,
              tick: `’${String(y.year).slice(2)}`,
              title: `${m.name}, ${y.year}: deaths per million`,
              label: y.value === Math.max(...m.years.map((z) => z.value)),
            }))}
            color="var(--deaths)"
            height={110}
            max={multiplesMax}
            format={(v) => perMillion(v)}
            ariaLabel={`${m.name}: reported deaths per million by year`}
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
  .spine-wrap {
    margin-top: 26px;
  }
  .hint {
    margin-top: 6px;
    font-size: 12.5px;
    color: var(--muted);
  }
  .stats {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 28px;
    margin-top: 32px;
    padding-top: 26px;
    border-top: 1px solid var(--hair);
  }
  .findings {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 32px;
    margin-top: 44px;
  }
  .findings h2 {
    font-size: 19px;
    line-height: 1.3;
    margin-bottom: 6px;
  }
  .findings p {
    color: var(--ink-2);
    font-size: 15px;
    max-width: 46ch;
  }
  .findings a {
    display: inline-block;
    margin-top: 8px;
    font-size: 14px;
    font-weight: 500;
  }
  .multiples {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px 22px;
  }
  .multiples h3 {
    font-size: 14px;
    font-weight: 500;
  }
  .multiples .faded {
    opacity: 0.45;
  }
  .multiples .active h3 {
    font-weight: 700;
  }
  @media (max-width: 900px) {
    .stats,
    .findings {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
  @media (max-width: 560px) {
    .stats {
      gap: 22px 18px;
    }
    .findings,
    .multiples {
      grid-template-columns: minmax(0, 1fr);
    }
    .multiples {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
