<script lang="ts">
  import type { Dataset } from "../../lib/data/types";
  import type { EngineOutputs } from "../../lib/sim/engine";
  import { PRESET_ERA } from "../../lib/sim/model";
  import type { EnsembleResult, Summary, TornadoBar } from "../../lib/sim/montecarlo";
  import { sim } from "../../lib/sim/store.svelte";
  import ChartFrame from "../ChartFrame.svelte";
  import AgeBars from "./AgeBars.svelte";
  import Analogs from "./Analogs.svelte";
  import AreaStack, { type Layer } from "./AreaStack.svelte";
  import ModelCard from "./ModelCard.svelte";
  import Report from "./Report.svelte";
  import Tornado from "./Tornado.svelte";
  import WaveOdds from "./WaveOdds.svelte";

  let {
    data,
    central,
    summary,
    ensemble,
    tornado,
    onpdf,
  }: {
    data: Dataset;
    central: EngineOutputs;
    summary: Summary;
    ensemble: EnsembleResult | null;
    tornado: { base: number; bars: TornadoBar[] } | null;
    onpdf: () => Promise<void>;
  } = $props();
  let r = $derived(sim.result!);
  // The wave classifier learned from COVID-19 only; for other diseases the sensitivity chart takes the row.
  let classifier = $derived(sim.applied!.pathogen.preset! in PRESET_ERA);

  function weeklyLast(values: Float64Array): number[] {
    const out: number[] = [];
    for (let w = 0; w * 7 < values.length; w++) out.push(values[Math.min(values.length - 1, w * 7 + 6)]);
    return out;
  }
  let layers = $derived.by<Layer[]>(() => {
    const hosp = weeklyLast(central.hospital);
    return [
      { id: "s", label: "Never infected yet", values: weeklyLast(central.susceptible), color: "var(--faint)" },
      { id: "i", label: "Infected now", values: weeklyLast(central.infected).map((v, i) => v + hosp[i]), color: "var(--cases)" },
      { id: "r", label: "Immune (recovered or vaccinated)", values: weeklyLast(central.immune), color: "var(--vax)" },
      { id: "d", label: "Died", values: weeklyLast(central.dead), color: "var(--deaths)" },
    ];
  });
</script>

<div class="section grid-2">
  <ChartFrame
    title="Who dies"
    subtitle={`Each age group's share of the population, against its share of deaths.`}
    source={null}
    columns={[
      { key: "band", label: "Age" },
      { key: "pop", label: "Share of people", numeric: true, format: (v) => `${((v as number) * 100).toFixed(1)}%` },
      { key: "deaths", label: "Deaths", numeric: true, format: (v) => Math.round(v as number).toLocaleString("en-US") },
    ]}
    rows={["0-19", "20-39", "40-59", "60-79", "80+"].map((band, i) => ({ band, pop: r.run.place.age_shares[i], deaths: central.deaths_by_age[i] }))}
  >
    <AgeBars population={r.run.place.age_shares} deaths={central.deaths_by_age} />
  </ChartFrame>
  <ChartFrame title="Where the population stands" subtitle="Share of people in each state, week by week (median run)." source={null}>
    <AreaStack {layers} ariaLabel="Share of the population susceptible, infected, immune and dead over time" />
  </ChartFrame>
</div>

<div class="section" class:grid-2={classifier}>
  <ChartFrame
    title="What moves the outcome most"
    subtitle="Total deaths when each input is pushed to a plausible low and high value, one at a time. The line marks this scenario."
    source={null}
  >
    {#if tornado}
      <Tornado base={tornado.base} bars={tornado.bars} />
    {:else}
      <p class="muted">Working out which inputs matter most…</p>
    {/if}
  </ChartFrame>
  {#if classifier}
    <ChartFrame
      title="A second opinion from real waves"
      subtitle="A classifier trained on 381 real COVID-19 waves in 149 countries gives the odds of each peak severity for a wave starting in these conditions. It never sees the engine."
      source={null}
    >
      <WaveOdds {central} />
    </ChartFrame>
  {:else}
    <p class="aside">
      For COVID-19-like diseases, a classifier trained on 381 real COVID-19 waves gives a second opinion here. It learned only from COVID-19, so
      it has nothing to say about this disease.
    </p>
  {/if}
</div>

<section class="section">
  <h2>Countries like this one</h2>
  <p class="sub">The real countries closest to this place on the model's 13 characteristics, and what COVID-19 did there in 2020–2021.</p>
  <div class="body"><Analogs {data} /></div>
</section>

<section class="section" id="report">
  <h2>Scenario report</h2>
  <div class="body"><Report {central} {summary} {ensemble} {tornado} {onpdf} /></div>
</section>

<section class="section">
  <h2>How the simulator works</h2>
  <div class="body"><ModelCard /></div>
</section>

<style>
  .sub {
    color: var(--ink-2);
    font-size: 14.5px;
    margin-top: 4px;
    max-width: 72ch;
  }
  .body {
    margin-top: 14px;
  }
  .aside {
    margin-top: 14px;
    max-width: 72ch;
    font-size: 13.5px;
    color: var(--muted);
  }
</style>
