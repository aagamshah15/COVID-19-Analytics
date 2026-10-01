<script lang="ts">
  import ChartFrame from "../components/ChartFrame.svelte";
  import Controls from "../components/Controls.svelte";
  import BarChart from "../lib/charts/BarChart.svelte";
  import LineChart from "../lib/charts/LineChart.svelte";
  import Scatter from "../lib/charts/Scatter.svelte";
  import { aggregateWeekly, inRegion, lastValue, MIN_RANKING_POPULATION, regionCountries, regionLabel, weekRange } from "../lib/data/aggregate";
  import type { Dataset } from "../lib/data/types";
  import { perMillion, pct } from "../lib/format";
  import { app } from "../lib/state/app.svelte";

  let { data }: { data: Dataset } = $props();

  let world = $derived(aggregateWeekly(data, data.countries));
  let cfr = $derived(data.sql.q12_cfr_by_quarter);
  let quarterEnds = $derived(
    cfr.map((r) => {
      const end = `${r.year}-${String((r.quarter as number) * 3).padStart(2, "0")}-31`;
      let i = data.weeks.length - 1;
      while (i > 0 && data.weeks[i] > end) i--;
      return i;
    }),
  );
  const quarterTick = (r: Record<string, unknown>) => (r.quarter === 1 ? String(r.year) : undefined);
  let cfrBars = $derived(
    cfr.map((r) => ({
      key: `${r.year}Q${r.quarter}`,
      value: r.cfr as number,
      tick: quarterTick(r),
      title: `${r.year} Q${r.quarter}: deaths per recorded case`,
      label: (r.year === 2020 && r.quarter === 1) || (r.year === 2022 && r.quarter === 4),
    })),
  );
  let vaxBars = $derived(
    cfr.map((r, k) => ({
      key: `${r.year}Q${r.quarter}`,
      value: world[quarterEnds[k]].vax ?? 0,
      tick: quarterTick(r),
      title: `${r.year} Q${r.quarter}: share of the world fully vaccinated`,
      label: (r.year === 2021 && r.quarter === 4) || (r.year === 2023 && r.quarter === 4),
    })),
  );

  const CONTINENTS = ["Europe", "South America", "North America", "Asia", "Oceania", "Africa"];
  let rollout = $derived(CONTINENTS.map((c) => ({ name: c, agg: aggregateWeekly(data, regionCountries(data, `continent:${c}`)) })));
  let activeContinent = $derived(app.region.startsWith("continent:") ? app.region.split(":")[1] : null);

  // Country scatter: vaccination at the end of 2021 vs deaths per recorded case during 2022.
  let end2021 = $derived(weekRange(data.weeks, "2020-01-01", "2021-12-31")[1]);
  let year2022 = $derived(weekRange(data.weeks, "2022-01-01", "2022-12-31"));
  let dots = $derived(
    data.countries
      .filter((c) => (c.population ?? 0) >= MIN_RANKING_POPULATION)
      .map((c) => {
        const s = data.series[c.iso];
        let deaths = 0;
        let cases = 0;
        for (let i = year2022[0]; i <= year2022[1]; i++) {
          if (s.d[i] !== null && s.c[i] !== null) {
            deaths += s.d[i] ?? 0;
            cases += s.c[i] ?? 0;
          }
        }
        const vax = lastValue(s.v, end2021);
        return vax === null || cases < 1000 ? null : { key: c.iso, label: c.name, x: vax, y: deaths / cases, emphasis: inRegion(c, app.region), note: c.continent ?? "" };
      })
      .filter((d): d is NonNullable<typeof d> => d !== null),
  );

  let terciles = $derived(data.sql.q13_vaccination_tercile_vs_2022_mortality);
  const TERCILE = ["Least vaccinated third", "Middle third", "Most vaccinated third"];
  let income = $derived(data.sql.q18_income_quartile_outcomes);
</script>

<Controls {data} showMeasure={false} />

<header class="hero">
  <h1>Vaccines and severity</h1>
  <p class="lede">
    COVID-19 became far less deadly per infection between 2020 and 2023. Vaccination was a large part of that, alongside prior infection, better
    treatment and milder variants. Comparing countries needs care: the most-vaccinated countries were also the oldest, richest and best at testing.
  </p>
</header>

<div class="section grid-2">
  <ChartFrame
    title="As coverage rose, deaths per recorded case fell"
    subtitle="Two panels on the same quarters, not one chart with two scales. Top: case fatality rate. Bottom: share of the world fully vaccinated at quarter end."
    query="q12_cfr_by_quarter"
    columns={[
      { key: "period", label: "Quarter" },
      { key: "cfr", label: "Case fatality rate", numeric: true, format: (v) => pct(v as number, 2) },
      { key: "vax", label: "Fully vaccinated", numeric: true, format: (v) => pct(v as number) },
    ]}
    rows={cfr.map((r, k) => ({ period: `${r.year} Q${r.quarter}`, cfr: r.cfr, vax: world[quarterEnds[k]].vax }))}
  >
    <BarChart bars={cfrBars} color="var(--deaths)" height={170} min={0} max={0.06} ticks={[0, 0.03, 0.06]} format={(v) => pct(v, 1)} ariaLabel="Case fatality rate by quarter" />
    <div class="gap"></div>
    <BarChart bars={vaxBars} color="var(--vax)" height={150} min={0} max={1} ticks={[0, 0.5, 1]} format={(v) => pct(v)} ariaLabel="Share of the world fully vaccinated by quarter" />
  </ChartFrame>

  <ChartFrame
    title="Europe and the Americas vaccinated first; Africa never caught up"
    subtitle="Population-weighted share fully vaccinated. The dashed line is the world in every panel."
    query="q11_vaccination_rollout_by_continent"
  >
    <div class="multiples">
      {#each rollout as r}
        <div class:faded={activeContinent && activeContinent !== r.name}>
          <h3>{r.name}</h3>
          <LineChart
            x={data.weeks.slice(40)}
            series={[
              { id: r.name, label: r.name, values: r.agg.slice(40).map((w) => w.vax), color: "var(--vax)" },
              { id: "world", label: "World", values: world.slice(40).map((w) => w.vax), color: "var(--faint)", role: "faint", dashed: true },
            ]}
            height={110}
            yMax={1}
            format={(v) => pct(v)}
            hatchGaps={false}
            compact
            ariaLabel={`${r.name}: share fully vaccinated`}
          />
        </div>
      {/each}
    </div>
  </ChartFrame>
</div>

<div class="section grid-7-5">
  <ChartFrame
    title="More-vaccinated countries saw fewer deaths per recorded case in 2022"
    subtitle={`Each dot is a country with 1 million or more people and at least 1,000 recorded cases in 2022.${app.region === "all" ? "" : ` ${regionLabel(app.region)} is highlighted.`} Select a dot to open the country.`}
    columns={[
      { key: "label", label: "Country" },
      { key: "x", label: "Fully vaccinated, end 2021", numeric: true, format: (v) => pct(v as number) },
      { key: "y", label: "Deaths per case, 2022", numeric: true, format: (v) => pct(v as number, 2) },
    ]}
    rows={[...dots].sort((a, b) => b.x - a.x)}
  >
    <Scatter
      {dots}
      color="var(--vax)"
      xLabel="Fully vaccinated at the end of 2021"
      yLabel="Deaths per recorded case in 2022"
      xFormat={(v) => pct(v)}
      yFormat={(v) => pct(v, 1)}
      xMax={1}
      yMax={0.04}
      onpick={(iso) => app.go("country", iso)}
      labelKeys={["USA", "IND", "ZAF", "JPN", "NGA"]}
      ariaLabel="Scatter of countries: vaccination at the end of 2021 against deaths per recorded case in 2022. Values above 4% are drawn at the top edge."
    />
  </ChartFrame>

  <div>
    <ChartFrame
      title="Why the raw comparison misleads"
      subtitle="Countries split into thirds by vaccination at the end of 2021, compared on 2022 outcomes."
      query="q13_vaccination_tercile_vs_2022_mortality"
      columns={[
        { key: "group", label: "Group" },
        { key: "countries", label: "Countries", numeric: true },
        { key: "dpm", label: "Deaths per million", numeric: true, format: (v) => perMillion(v as number) },
        { key: "cfr", label: "Deaths per case", numeric: true, format: (v) => pct(v as number, 2) },
      ]}
      rows={terciles.map((t, i) => ({ group: TERCILE[i], countries: t.countries, dpm: t.deaths_per_million_2022, cfr: t.cfr_2022 }))}
    >
      <div class="pair">
        <div>
          <h3>Deaths per million, 2022</h3>
          <BarChart
            bars={terciles.map((t, i) => ({ key: String(i), value: t.deaths_per_million_2022 as number, tick: ["Least", "Middle", "Most"][i], title: TERCILE[i], label: true }))}
            color="var(--deaths)"
            height={150}
            format={perMillion}
            ariaLabel="Deaths per million in 2022 by vaccination third"
          />
        </div>
        <div>
          <h3>Deaths per case, 2022</h3>
          <BarChart
            bars={terciles.map((t, i) => ({ key: String(i), value: t.cfr_2022 as number, tick: ["Least", "Middle", "Most"][i], title: TERCILE[i], label: true }))}
            color="var(--deaths)"
            height={150}
            format={(v) => pct(v, 2)}
            ariaLabel="Deaths per recorded case in 2022 by vaccination third"
          />
        </div>
      </div>
      <p class="explain">
        The most-vaccinated third recorded <strong>more</strong> deaths per million but less than a quarter of the deaths per case. They were older and
        tested far more, so they found more cases and registered more deaths. Deaths per case is the fairer severity comparison, and even that is an
        association rather than a measured vaccine effect.
      </p>
    </ChartFrame>

    <div class="income">
      <h3>By income</h3>
      <table>
        <thead><tr><th>GDP per person</th><th class="r">Deaths per million</th><th class="r">Fully vaccinated</th></tr></thead>
        <tbody>
          {#each income as q}
            <tr>
              <td>{["Poorest quarter", "Second quarter", "Third quarter", "Richest quarter"][(q.gdp_quartile as number) - 1]}</td>
              <td class="r num">{perMillion(q.deaths_per_million as number)}</td>
              <td class="r num">{pct(q.fully_vaccinated_share as number)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      <p class="muted small">Source: OWID and WHO. Query <code>q18_income_quartile_outcomes</code></p>
    </div>
  </div>
</div>

<style>
  .hero {
    margin-top: 34px;
  }
  .gap {
    height: 18px;
  }
  .multiples {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px 24px;
  }
  .multiples h3,
  .pair h3,
  .income h3 {
    font-size: 14px;
    font-weight: 500;
  }
  .faded {
    opacity: 0.45;
  }
  .pair {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 20px;
  }
  .explain {
    margin-top: 14px;
    color: var(--ink-2);
    font-size: 14.5px;
  }
  .income {
    margin-top: 32px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 8px;
    font-size: 14px;
  }
  th {
    text-align: left;
    font-weight: 500;
    color: var(--ink-2);
    border-bottom: 1px solid var(--hair-2);
    padding: 6px 4px;
  }
  td {
    padding: 6px 4px;
    border-bottom: 1px solid var(--hair);
  }
  .r {
    text-align: right;
  }
  .small {
    font-size: 12.5px;
    margin-top: 8px;
  }
  code {
    font-size: 12px;
  }
</style>
