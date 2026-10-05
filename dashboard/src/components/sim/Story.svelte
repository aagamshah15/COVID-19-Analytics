<script lang="ts">
  /**
   * Results, story first: what was simulated, one plain sentence, four numbers, one chart with the
   * "if nothing were done" path for contrast, and the three biggest levers in words.
   */
  import { compact } from "../../lib/format";
  import type { EngineOutputs } from "../../lib/sim/engine";
  import type { EnsembleResult, Summary, TornadoBar } from "../../lib/sim/montecarlo";
  import { sim } from "../../lib/sim/store.svelte";
  import { CAVEAT, didSomething, figures, headline, leverSentence, levers, scenarioParts, weekly } from "../../lib/sim/story";
  import ChartFrame from "../ChartFrame.svelte";
  import PdfButton from "./PdfButton.svelte";
  import SimChart, { type Fan } from "./SimChart.svelte";

  interface Props {
    central: EngineOutputs;
    noAction: EngineOutputs;
    summary: Summary;
    noActionSummary: Summary;
    ensemble: EnsembleResult;
    tornado: { base: number; bars: TornadoBar[] } | null;
    capacity: number;
    onpdf: () => Promise<void>;
  }
  let { central, noAction, summary, noActionSummary, ensemble, tornado, capacity, onpdf }: Props = $props();
  let r = $derived(sim.result!);
  let applied = $derived(sim.applied!);
  let parts = $derived(scenarioParts(r, applied));
  let acted = $derived(didSomething(applied));

  type MetricId = "hospital" | "infections" | "deaths";
  const METRICS: { id: MetricId; label: string; series: "hospital" | "infections" | "deaths"; color: string; flow: boolean; title: string }[] = [
    { id: "hospital", label: "In hospital", series: "hospital", color: "var(--hosp)", flow: false, title: "How full hospitals get" },
    { id: "infections", label: "New infections", series: "infections", color: "var(--cases)", flow: true, title: "New infections each week" },
    { id: "deaths", label: "Deaths", series: "deaths", color: "var(--deaths)", flow: true, title: "Deaths each week" },
  ];
  let metricId = $state<MetricId>("hospital");
  let metric = $derived(METRICS.find((m) => m.id === metricId)!);
  let line = $derived(weekly(central[metric.series], metric.flow));
  let fan = $derived.by<Fan | null>(() => {
    const b = ensemble.bands.weekly[metric.series];
    return b && b[0].length === line.length ? { lo90: b[0], lo50: b[1], hi50: b[3], hi90: b[4] } : null;
  });
  let compare = $derived(acted ? [{ id: "none", label: "If nothing were done", short: "Nothing done", values: weekly(noAction[metric.series], metric.flow) }] : []);
  let policy = $derived(weekly(central.stringency, false));
  let figs = $derived(figures(applied, summary, noActionSummary, ensemble));
  let top = $derived(levers(tornado));
  let leverMax = $derived(Math.max(1, ...top.map((l) => l.cases[1].deaths)));
</script>

<section class="story">
  {#if sim.changed}
    <div class="stale" role="status">
      <span>You've changed the scenario since these results were run.</span>
      <button class="primary-small" onclick={() => sim.run()}>Run now</button>
      <button class="link-button" onclick={() => (sim.spec = $state.snapshot(sim.applied!))}>Discard changes</button>
    </div>
  {/if}
  <div class="chosen">
    <p><strong>{parts[0]}</strong> · {parts.slice(1).join(" · ")}</p>
    <div class="actions">
      <PdfButton make={onpdf} />
      <button class="ghost" onclick={() => sim.edit(1)}>Change scenario</button>
      <button class="link-button" onclick={() => sim.startOver()}>Start over</button>
    </div>
  </div>

  <p class="headline">
    {#each headline(applied, r.days, summary, noActionSummary) as run}{#if run.bold}<strong>{run.text}</strong>{:else}{run.text}{/if}{/each}
  </p>

  <div class="numbers">
    {#each figs as f}
      <div>
        <span class="v">{f.value}{#if f.unit}<small>{f.unit}</small>{/if}</span>
        <span class="l">{f.label}</span>
        {#each f.notes as note}<span class="r">{note}</span>{/each}
      </div>
    {/each}
  </div>

  <div class="chart">
    <div class="seg" role="group" aria-label="What to show">
      {#each METRICS as m}<button aria-pressed={metricId === m.id} onclick={() => (metricId = m.id)}>{m.label}</button>{/each}
    </div>
    <ChartFrame
      title={metric.title}
      subtitle={`The solid line is the most likely path. The shaded band covers 9 in 10 of ${ensemble.draws} runs with uncertain inputs.${compare.length ? " The dashed line is what would happen if nothing were done." : ""} The grey strip along the bottom shows when restrictions are in place.`}
      source={null}
    >
      <SimChart
        central={line}
        {fan}
        fanLevel="90"
        stepDays={7}
        window={[0, r.days - 1]}
        color={metric.color}
        format={(v) => compact(v)}
        label={metric.label}
        capacity={metricId === "hospital" ? capacity : null}
        capacityLabel="Hospital beds"
        threshold={metricId === "hospital" ? capacity : null}
        {policy}
        {compare}
        ariaLabel={`${metric.title}, by week`}
      />
    </ChartFrame>
  </div>

  {#if top.length}
    <div class="levers">
      <h3>What makes the biggest difference</h3>
      <p class="sub">Change one of these, and the number of deaths moves the most:</p>
      <ul>
        {#each top as l}
          <li>
            <strong>{l.name}</strong>
            <span class="lever-bar" aria-hidden="true">
              <span style:left={`${(l.cases[0].deaths / leverMax) * 100}%`} style:width={`${Math.max(((l.cases[1].deaths - l.cases[0].deaths) / leverMax) * 100, 1)}%`}></span>
            </span>
            <span class="lever-text">{leverSentence(l)}</span>
          </li>
        {/each}
      </ul>
    </div>
  {/if}

  <p class="caveat">{CAVEAT}</p>
</section>

<style>
  .stale {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 14px;
    margin-bottom: 16px;
    padding: 10px 14px;
    border: 1px solid var(--ink-2);
    border-radius: 10px;
    font-size: 14.5px;
  }
  .stale span {
    flex: 1;
    min-width: 200px;
  }
  .primary-small {
    background: var(--ink);
    color: var(--plane);
    border: 0;
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 14px;
    cursor: pointer;
  }
  .chosen {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 10px 20px;
    padding-bottom: 14px;
    border-bottom: 1px solid var(--hair);
    font-size: 15px;
    color: var(--ink-2);
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px 14px;
  }
  .actions :global(button) {
    white-space: nowrap;
  }
  .ghost {
    background: none;
    border: 1px solid var(--hair-2);
    border-radius: 10px;
    padding: 8px 14px;
    font-size: 14.5px;
    cursor: pointer;
  }
  .headline {
    margin-top: 22px;
    font-size: clamp(20px, 2.1vw, 25px);
    line-height: 1.4;
    max-width: 52ch;
  }
  .numbers {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 24px;
    margin-top: 28px;
  }
  .numbers > div {
    display: grid;
    align-content: start;
    gap: 6px;
  }
  .v {
    font-size: clamp(32px, 3.2vw, 44px);
    font-weight: 700;
    line-height: 1;
  }
  .v small {
    font-size: 0.45em;
    font-weight: 500;
    color: var(--ink-2);
    margin-left: 5px;
  }
  .l {
    font-size: 15px;
    color: var(--ink-2);
  }
  .r {
    font-size: 13px;
    color: var(--muted);
  }
  .chart {
    margin-top: 36px;
  }
  .chart > .seg {
    margin-bottom: 16px;
  }
  .levers {
    margin-top: 36px;
  }
  .levers .sub {
    margin-top: 4px;
    color: var(--ink-2);
    font-size: 14.5px;
  }
  .levers ul {
    list-style: none;
    margin: 14px 0 0;
    padding: 0;
    display: grid;
    gap: 14px;
    max-width: 900px;
  }
  .levers li {
    display: grid;
    grid-template-columns: minmax(160px, 34%) minmax(0, 1fr);
    gap: 4px 16px;
    align-items: center;
  }
  .lever-bar {
    position: relative;
    height: 10px;
    background: var(--hair);
    border-radius: 3px;
  }
  .lever-bar span {
    position: absolute;
    top: 0;
    bottom: 0;
    background: var(--deaths);
    border-radius: 3px;
  }
  .lever-text {
    grid-column: 2;
    font-size: 13px;
    color: var(--ink-2);
  }
  .caveat {
    margin-top: 32px;
    max-width: 72ch;
    font-size: 14.5px;
    color: var(--ink-2);
    border-left: 3px solid var(--hair-2);
    padding-left: 12px;
  }
  @media (max-width: 640px) {
    .levers li {
      grid-template-columns: minmax(0, 1fr);
    }
    .lever-text {
      grid-column: 1;
    }
  }
</style>
