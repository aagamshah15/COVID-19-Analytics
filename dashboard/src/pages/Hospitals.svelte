<script lang="ts">
  import ChartFrame from "../components/ChartFrame.svelte";
  import Controls from "../components/Controls.svelte";
  import Heatmap from "../lib/charts/Heatmap.svelte";
  import RankBars from "../lib/charts/RankBars.svelte";
  import { inRegion, regionLabel, weekRange } from "../lib/data/aggregate";
  import type { Dataset } from "../lib/data/types";
  import { day, perMillion, pct } from "../lib/format";
  import { app } from "../lib/state/app.svelte";

  let { data }: { data: Dataset } = $props();

  let range = $derived(weekRange(data.weeks, app.from, app.to));
  const peakIn = (values: (number | null)[], [a, b]: [number, number]) => {
    let best: number | null = null;
    let at = -1;
    for (let i = a; i <= b; i++) {
      const v = values[i];
      if (v !== null && (best === null || v > best)) {
        best = v;
        at = i;
      }
    }
    return { best, at };
  };

  let reporting = $derived(data.countries.filter((c) => data.series[c.iso].occ.some((v) => v !== null)));
  let publishing = $derived(data.countries.filter((c) => data.series[c.iso].h.some((v) => v !== null) || data.series[c.iso].icu.some((v) => v !== null)));
  let inScope = $derived(reporting.filter((c) => inRegion(c, app.region)));
  let occPeaks = $derived(
    inScope
      .map((c) => ({ c, ...peakIn(data.series[c.iso].occ, range) }))
      .filter((r) => r.best !== null)
      .sort((a, b) => (b.best ?? 0) - (a.best ?? 0)),
  );
  let icuPeaks = $derived(
    data.countries
      .filter((c) => inRegion(c, app.region))
      .map((c) => ({ c, ...peakIn(data.series[c.iso].icu, range) }))
      .filter((r) => r.best !== null)
      .sort((a, b) => (b.best ?? 0) - (a.best ?? 0))
      .slice(0, 15),
  );
  let heatRows = $derived(
    [...inScope]
      .map((c) => ({ c, peak: peakIn(data.series[c.iso].occ, [0, data.weeks.length - 1]).best ?? 0 }))
      .sort((a, b) => b.peak - a.peak)
      .map(({ c }) => ({ key: c.iso, label: c.name, values: data.series[c.iso].occ.slice(40) })),
  );
  let top = $derived(occPeaks[0]);
  let periodText = $derived(app.isWholePeriod ? "2020–2023" : `${day(data.weeks[range[0]])} to ${day(data.weeks[range[1]])}`);
</script>

<Controls {data} showMeasure={false} />

<header class="hero">
  <h1>How close hospitals came to the edge</h1>
  <p class="lede">
    {#if top}
      At its worst, COVID-19 filled {pct(top.best)} of {top.c.name}'s hospital beds, in the week ending {day(data.weeks[top.at])}.
    {/if}
    Only {publishing.length} countries published COVID-19 hospital figures, mostly in Europe and the Americas, and {reporting.length} of them can be set
    against their total bed capacity. This page covers them alone.
  </p>
</header>

<div class="section grid-5-7">
  <ChartFrame
    title="Peak share of all hospital beds taken by COVID-19 patients"
    subtitle={`Highest weekly average, ${periodText}${app.region === "all" ? "" : `, ${regionLabel(app.region)}`}. Select a country to open its profile.`}
    query={app.isWholePeriod ? "q15_peak_covid_bed_occupancy" : undefined}
    columns={[
      { key: "name", label: "Country" },
      { key: "peak", label: "Peak share of beds", numeric: true, format: (v) => pct(v as number, 1) },
      { key: "week", label: "Week ending" },
    ]}
    rows={occPeaks.map((r) => ({ name: r.c.name, peak: r.best, week: day(data.weeks[r.at]) }))}
  >
    {#if occPeaks.length}
      <RankBars
        items={occPeaks.slice(0, 18).map((r) => ({ key: r.c.iso, label: r.c.name, value: r.best ?? 0, note: day(data.weeks[r.at]).slice(-8) }))}
        color="var(--hosp)"
        format={(v) => pct(v, 1)}
        onpick={(iso) => app.go("country", iso)}
      />
    {:else}
      <p class="empty">No country {app.region === "all" ? "" : `in ${regionLabel(app.region)} `}published hospital occupancy for this period.</p>
    {/if}
  </ChartFrame>

  <ChartFrame
    title="Strain came in waves, and the waves moved"
    subtitle="Share of hospital beds occupied by COVID-19 patients, week by week, from October 2020. Rows sorted by each country's worst week."
  >
    {#if heatRows.length}
      <Heatmap
        weeks={data.weeks.slice(40)}
        rows={heatRows}
        metric="hosp"
        max={0.2}
        format={(v) => pct(v)}
        valueLabel="beds occupied"
        highlight={app.isWholePeriod ? null : [Math.max(range[0] - 40, 0), range[1] - 40]}
        onpick={(iso) => app.go("country", iso)}
        ariaLabel="Heatmap of weekly COVID-19 hospital bed occupancy by country. The ranking and table views list each country's peak."
      />
    {:else}
      <p class="empty">No hospital occupancy data for this region.</p>
    {/if}
  </ChartFrame>
</div>

<div class="section grid-2">
  <ChartFrame
    title="Intensive care load at its peak"
    subtitle={`COVID-19 patients in intensive care per million people, highest week, ${periodText}.`}
    query={app.isWholePeriod ? "q16_peak_icu_load" : undefined}
  >
    {#if icuPeaks.length}
      <RankBars
        items={icuPeaks.map((r) => ({ key: r.c.iso, label: r.c.name, value: r.best ?? 0 }))}
        color="var(--hosp)"
        format={perMillion}
        onpick={(iso) => app.go("country", iso)}
      />
    {:else}
      <p class="empty">No intensive care data for this region and period.</p>
    {/if}
  </ChartFrame>
  <div class="notes">
    <h2>Reading these numbers</h2>
    <ul>
      <li>Bed occupancy divides COVID-19 inpatients by the country's total hospital beds, from its most recent count. It shows pressure on the whole system, not just COVID wards.</li>
      <li>Countries define "COVID-19 patient" differently. Some count anyone testing positive, others only those admitted for COVID-19, so compare shapes and timing more than exact levels.</li>
      <li>A missing country means it didn't publish occupancy, not that its hospitals were unaffected.</li>
    </ul>
  </div>
</div>

<style>
  .hero {
    margin-top: 34px;
  }
  .notes ul {
    margin: 12px 0 0;
    padding-left: 18px;
    color: var(--ink-2);
    font-size: 15px;
    max-width: 60ch;
  }
  .notes li + li {
    margin-top: 10px;
  }
</style>
