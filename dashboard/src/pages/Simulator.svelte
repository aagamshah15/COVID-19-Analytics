<script lang="ts">
  import { onDestroy, tick, untrack } from "svelte";
  import FullChart from "../components/sim/FullChart.svelte";
  import Outcomes from "../components/sim/Outcomes.svelte";
  import Running from "../components/sim/Running.svelte";
  import StartScreen from "../components/sim/StartScreen.svelte";
  import Story from "../components/sim/Story.svelte";
  import Wizard from "../components/sim/Wizard.svelte";
  import type { Dataset } from "../lib/data/types";
  import { SimClient } from "../lib/sim/client";
  import type { EngineOutputs } from "../lib/sim/engine";
  import { capacityOf, type EnsembleResult, simulate, summarise, type TornadoBar, withoutResponse } from "../lib/sim/montecarlo";
  import { encodeSpec } from "../lib/sim/spec";
  import { sim } from "../lib/sim/store.svelte";
  import { app } from "../lib/state/app.svelte";

  let { data }: { data: Dataset } = $props();
  const DRAWS = 200;
  const MIN_RUNNING_MS = 1400;

  // --- open: a shared link goes straight to its results; otherwise a blank start ------------
  // Read the link before loading: the URL effect below would otherwise clear it the moment the
  // model arrives, before open() has seen it.
  const link = { encoded: app.sim, iso: app.iso };
  let opened = $state(false);
  sim.load().then(() => {
    sim.open(link.encoded, link.iso);
    opened = true;
  });

  // The URL only ever holds a scenario that was run, so a shared link reproduces what was seen.
  $effect(() => {
    const applied = sim.applied;
    if (!sim.model || !opened) return;
    untrack(() => (applied && applied.iso ? app.setSim(encodeSpec($state.snapshot(applied)), applied.iso) : app.setSim("", null)));
  });

  // --- running ----------------------------------------------------------------------------------
  const client = new SimClient();
  onDestroy(() => client.dispose());
  let phase = $state(0);
  let computing = $state(false);
  let central = $state<EngineOutputs | null>(null);
  let noAction = $state<EngineOutputs | null>(null);
  let ensemble = $state<EnsembleResult | null>(null);
  let tornado = $state<{ base: number; bars: TornadoBar[] } | null>(null);
  let explored = $state(false);
  const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

  async function compute(id: number) {
    const result = sim.result;
    if (!result) return;
    computing = true;
    phase = 0;
    ensemble = null;
    tornado = null;
    const started = performance.now();
    const run = $state.snapshot(result.run);
    window.scrollTo({ top: 0, behavior: "smooth" });
    await tick();
    await wait(250);
    central = simulate(run);
    noAction = simulate(withoutResponse(run));
    phase = 1;
    await wait(250);
    phase = 2;
    const ens = await client.request("ensemble", run, DRAWS, 1);
    if (id !== sim.runId || !ens) return;
    ensemble = ens;
    phase = 3;
    const tor = await client.request("sensitivity", run);
    if (id !== sim.runId) return;
    tornado = tor;
    phase = 4;
    const left = MIN_RUNNING_MS - (performance.now() - started);
    if (left > 0) await wait(left);
    if (id === sim.runId) computing = false;
  }
  $effect(() => {
    const id = sim.runId;
    if (id > 0 && sim.model) untrack(() => compute(id));
  });

  let r = $derived(sim.result);
  let capacity = $derived(r ? capacityOf(r.run) : 0);
  let summary = $derived(r && central ? summarise(central, r.run.place.population, capacity) : null);
  let noActionSummary = $derived(r && noAction ? summarise(noAction, r.run.place.population, capacity) : null);

  // The PDF code (and jsPDF) loads only when someone asks for the report.
  async function downloadReport() {
    if (!r || !sim.applied || !central || !noAction || !summary || !noActionSummary || !ensemble) return;
    const { downloadPdf } = await import("../lib/sim/pdf");
    downloadPdf({
      model: sim.model!,
      spec: $state.snapshot(sim.applied),
      r,
      central,
      noAction,
      summary,
      noActionSummary,
      ensemble,
      tornado,
      capacity,
      link: location.href,
      date: new Date(),
    });
  }
</script>

<header>
  <h1>Pandemic simulator</h1>
  {#if sim.view === "start"}
    <p class="lede">
      What would happen if a new disease reached a country like yours? Pick a ready-made scenario or build your own, then press Run. The simulator
      is trained on real data from 2020–2023 and runs entirely in your browser.
    </p>
  {/if}
</header>

{#if sim.error}
  <div class="empty" role="alert"><h2>The simulator didn't load</h2><p>{sim.error}</p></div>
{:else if !sim.model}
  <p class="loading" role="status">Loading the simulator…</p>
{:else if sim.view === "start"}
  <StartScreen />
{:else if sim.view === "build"}
  <Wizard countries={data.countries} />
{:else if r}
  {#if computing || !central || !noAction || !ensemble || !summary || !noActionSummary}
    <Running phase={phase} place={{ name: r.country.name, population: r.run.place.population }} days={r.days} draws={DRAWS} />
  {:else}
    <Story {central} {noAction} {summary} {noActionSummary} {ensemble} {tornado} {capacity} onpdf={downloadReport} />

    <details class="explore" ontoggle={(e) => (explored ||= e.currentTarget.open)}>
      <summary>
        <span>Explore the details</span>
        <small>Detailed charts, who is most at risk, what drives the result, similar real countries, the full report and how the model works</small>
      </summary>
      <div class="explore-body">
        <FullChart {central} {ensemble} {capacity} />
        <Outcomes {data} {central} {summary} {ensemble} {tornado} {explored} onpdf={downloadReport} />
      </div>
    </details>
  {/if}
{/if}

<style>
  header {
    margin-bottom: 26px;
  }
  .loading {
    margin-top: 60px;
    color: var(--ink-2);
  }
  .explore {
    margin-top: 44px;
    border-top: 1px solid var(--hair);
    padding-top: 18px;
  }
  .explore > summary {
    cursor: pointer;
    display: grid;
    gap: 4px;
    list-style: none;
  }
  .explore > summary::-webkit-details-marker {
    display: none;
  }
  .explore > summary span {
    font-size: 19px;
    font-weight: 700;
  }
  .explore > summary span::after {
    content: " ▸";
    color: var(--muted);
  }
  .explore[open] > summary span::after {
    content: " ▾";
  }
  .explore > summary small {
    font-size: 14px;
    color: var(--ink-2);
  }
  .explore-body {
    margin-top: 22px;
  }
</style>
