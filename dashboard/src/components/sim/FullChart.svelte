<script lang="ts">
  /** The detailed chart: every metric, daily or weekly, per million, bands, time window, pinned scenarios. */
  import { compact, count } from "../../lib/format";
  import type { EngineOutputs } from "../../lib/sim/engine";
  import type { EnsembleResult } from "../../lib/sim/montecarlo";
  import { sim } from "../../lib/sim/store.svelte";
  import { diseaseLabel } from "../../lib/sim/words";
  import ChartFrame from "../ChartFrame.svelte";
  import SimChart, { type CompareLine, type Fan } from "./SimChart.svelte";

  let { central, ensemble, capacity }: { central: EngineOutputs; ensemble: EnsembleResult; capacity: number } = $props();
  let r = $derived(sim.result!);

  type MetricId = "infections" | "hospital" | "deaths" | "reported" | "rt" | "vaccinated";
  const METRICS: { id: MetricId; label: string; series: "infections" | "hospital" | "deaths" | "reported_deaths" | "rt" | "vaccinated"; color: string; flow: boolean }[] = [
    { id: "infections", label: "Infections", series: "infections", color: "var(--cases)", flow: true },
    { id: "hospital", label: "In hospital", series: "hospital", color: "var(--hosp)", flow: false },
    { id: "deaths", label: "Deaths", series: "deaths", color: "var(--deaths)", flow: true },
    { id: "reported", label: "Reported deaths", series: "reported_deaths", color: "var(--deaths)", flow: true },
    { id: "rt", label: "Effective R", series: "rt", color: "var(--cases)", flow: false },
    { id: "vaccinated", label: "Vaccinated", series: "vaccinated", color: "var(--vax)", flow: false },
  ];
  let metricId = $state<MetricId>("hospital");
  let metric = $derived(METRICS.find((m) => m.id === metricId)!);
  let weekly = $state(true);
  let perMillion = $state(false);
  let fanLevel = $state<"none" | "50" | "90">("90");
  let windowId = $state<"all" | "6m" | "y1" | "y2" | "y3">("all");
  let shade = $state(true);
  let days = $derived(r.days);
  let windowRange = $derived<[number, number]>(
    windowId === "6m" ? [0, 182] : windowId === "y1" ? [0, 365] : windowId === "y2" ? [365, 730] : windowId === "y3" ? [730, 1095] : [0, days - 1],
  );
  let scale = $derived(perMillion && metricId !== "rt" ? 1e6 / r.run.place.population : 1);

  function aggregate(values: ArrayLike<number>, flow: boolean): number[] {
    if (!weekly) return Array.from(values);
    const out: number[] = [];
    for (let w = 0; w * 7 < values.length; w++) {
      const end = Math.min(values.length, w * 7 + 7);
      let s = 0;
      for (let d = w * 7; d < end; d++) s += values[d];
      out.push(flow ? s : values[end - 1]);
    }
    return out;
  }
  let line = $derived(aggregate(central[metric.series], metric.flow).map((v) => v * scale));
  let fan = $derived.by<Fan | null>(() => {
    const q = (weekly ? ensemble.bands.weekly : ensemble.bands.daily)[metric.series];
    if (!q || q[0].length !== line.length) return null;
    return { lo90: q[0].map((v) => v * scale), lo50: q[1].map((v) => v * scale), hi50: q[3].map((v) => v * scale), hi90: q[4].map((v) => v * scale) };
  });
  let policy = $derived(aggregate(central.stringency, false));
  let fmt = $derived((v: number) => (metricId === "rt" ? v.toFixed(2) : perMillion ? (v >= 100 ? count(v) : v.toFixed(1)) : compact(v)));
  let threshold = $derived(shade ? (metricId === "hospital" ? capacity * scale : metricId === "rt" ? 1 : null) : null);

  // Pinned scenarios live in the store, so they survive a new run and can be compared.
  function pin() {
    if (sim.pins.length >= 3) return;
    const letter = ["A", "B", "C"].find((l) => !sim.pins.some((x) => x.id === l)) ?? "A";
    let deaths = 0;
    for (const d of central.deaths) deaths += d;
    const label = `${letter}: ${r.country.name}, ${diseaseLabel(sim.applied!.pathogen.preset).replace(/^Like /, "")}`;
    sim.pins = [...sim.pins, { id: letter, label, outputs: central, population: r.run.place.population, deaths }];
  }
  let compare = $derived<CompareLine[]>(
    sim.pins.map((x) => ({
      id: x.id,
      label: x.id,
      values: aggregate(x.outputs[metric.series], metric.flow).map((v) => v * (perMillion && metricId !== "rt" ? 1e6 / x.population : 1)),
    })),
  );
</script>

<div class="filters" role="group" aria-label="Chart filters">
  <div class="seg small wide-only" role="group" aria-label="Metric">
    {#each METRICS as m}<button aria-pressed={metricId === m.id} onclick={() => (metricId = m.id)}>{m.label}</button>{/each}
  </div>
  <select class="narrow-only" aria-label="Metric" bind:value={metricId}>
    {#each METRICS as m}<option value={m.id}>{m.label}</option>{/each}
  </select>
  <div class="seg small" role="group" aria-label="Time step">
    <button aria-pressed={weekly} onclick={() => (weekly = true)}>Weekly</button>
    <button aria-pressed={!weekly} onclick={() => (weekly = false)}>Daily</button>
  </div>
  <div class="seg small" role="group" aria-label="Measure">
    <button aria-pressed={!perMillion} onclick={() => (perMillion = false)}>People</button>
    <button aria-pressed={perMillion} onclick={() => (perMillion = true)} disabled={metricId === "rt"}>Per million</button>
  </div>
  <div class="seg small" role="group" aria-label="Uncertainty range">
    <button aria-pressed={fanLevel === "90"} onclick={() => (fanLevel = "90")}>90% range</button>
    <button aria-pressed={fanLevel === "50"} onclick={() => (fanLevel = "50")}>50%</button>
    <button aria-pressed={fanLevel === "none"} onclick={() => (fanLevel = "none")}>Median only</button>
  </div>
  <div class="seg small" role="group" aria-label="Time window">
    <button aria-pressed={windowId === "all"} onclick={() => (windowId = "all")}>All</button>
    <button aria-pressed={windowId === "6m"} onclick={() => (windowId = "6m")}>First 6 months</button>
    {#each Array.from({ length: days / 365 }, (_, i) => i + 1) as y}
      <button aria-pressed={windowId === `y${y}`} onclick={() => (windowId = `y${y}` as typeof windowId)}>Year {y}</button>
    {/each}
  </div>
  {#if metricId === "hospital" || metricId === "rt"}
    <label class="check"><input type="checkbox" bind:checked={shade} /> Shade {metricId === "hospital" ? "over capacity" : "R above 1"}</label>
  {/if}
</div>

<ChartFrame
  title={`${metric.label}, in detail`}
  subtitle={`Median of the simulation, with the ${fanLevel === "none" ? "range hidden" : `${fanLevel}% range across uncertain inputs`}. Pin a scenario, change it, run again, and compare.`}
  source={null}
>
  <SimChart
    central={line}
    {fan}
    {fanLevel}
    stepDays={weekly ? 7 : 1}
    window={windowRange}
    color={metric.color}
    format={fmt}
    label={metric.label}
    capacity={metricId === "hospital" ? capacity * scale : null}
    capacityLabel="Beds available"
    {threshold}
    {policy}
    {compare}
    ariaLabel={`${metric.label}, ${weekly ? "weekly" : "daily"}`}
  />
</ChartFrame>

<div class="pins">
  <button onclick={pin} disabled={sim.pins.length >= 3}>Pin this scenario to compare</button>
  {#each sim.pins as x (x.id)}
    <span class="pin">
      <span class="num">{x.label} · {compact(x.deaths)} deaths</span>
      <button aria-label={`Remove ${x.label}`} onclick={() => (sim.pins = sim.pins.filter((y) => y.id !== x.id))}>×</button>
    </span>
  {/each}
</div>

<style>
  .filters {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 10px;
    align-items: center;
    margin: 4px 0 18px;
  }
  .check {
    display: flex;
    gap: 6px;
    align-items: center;
    font-size: 13px;
    color: var(--ink-2);
  }
  .check input {
    accent-color: var(--ink);
  }
  .narrow-only {
    display: none;
  }
  .pins {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 12px;
    align-items: center;
    margin-top: 14px;
    font-size: 13.5px;
  }
  .pins > button {
    border: 1px solid var(--hair-2);
    background: var(--plane);
    border-radius: 8px;
    padding: 5px 12px;
    cursor: pointer;
  }
  .pins > button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .pin {
    display: inline-flex;
    gap: 6px;
    align-items: center;
    border: 1px dashed var(--muted);
    border-radius: 999px;
    padding: 2px 4px 2px 10px;
    color: var(--ink-2);
  }
  .pin button {
    border: 0;
    background: none;
    cursor: pointer;
    color: var(--ink-2);
    font-size: 15px;
    line-height: 1;
  }
  @media (max-width: 640px) {
    .wide-only {
      display: none;
    }
    .narrow-only {
      display: inline-block;
    }
  }
</style>
