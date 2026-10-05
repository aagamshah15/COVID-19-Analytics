<script lang="ts">
  /** The written scenario report beside its key numbers and where the settings came from, plus ways to take it away. */
  import type { EngineOutputs } from "../../lib/sim/engine";
  import type { EnsembleResult, Summary, TornadoBar } from "../../lib/sim/montecarlo";
  import { buildReport, settingsRows, toCsv } from "../../lib/sim/report";
  import { sim } from "../../lib/sim/store.svelte";
  import PdfButton from "./PdfButton.svelte";

  interface Props {
    central: EngineOutputs;
    summary: Summary;
    ensemble: EnsembleResult | null;
    tornado: { base: number; bars: TornadoBar[] } | null;
    onpdf: () => Promise<void>;
  }
  let { central, summary, ensemble, tornado, onpdf }: Props = $props();
  let r = $derived(sim.result!);
  let report = $derived(buildReport(sim.model!, r, summary, ensemble, tornado));
  let settings = $derived(settingsRows(sim.model!, r, sim.applied!));
  let copied = $state(false);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(location.href);
      copied = true;
      setTimeout(() => (copied = false), 2000);
    } catch {
      copied = false;
    }
  }
  function download() {
    const blob = new Blob([toCsv(central, ensemble)], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `pandemic-scenario-${r.country.iso.toLowerCase()}-${sim.applied!.pathogen.preset}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }
</script>

<div class="report">
  <div class="text">
    {#each report.paragraphs as p}<p>{p}</p>{/each}
    <ul class="warnings">
      {#each report.warnings as w}<li>{w}</li>{/each}
    </ul>
    <table>
      <caption>Key numbers</caption>
      <thead><tr><th scope="col">Outcome</th><th scope="col" class="numeric">Median run</th><th scope="col" class="numeric">90% range</th></tr></thead>
      <tbody>
        {#each report.metrics as m}
          <tr><th scope="row">{m.label}</th><td class="numeric num">{m.median}</td><td class="numeric num">{m.range}</td></tr>
        {/each}
      </tbody>
    </table>
  </div>

  <table>
    <caption>Where the settings came from</caption>
    <thead><tr><th scope="col">Setting</th><th scope="col">Value</th><th scope="col">Source</th></tr></thead>
    <tbody>
      {#each settings as a}
        <tr><th scope="row">{a.label}</th><td class="num">{a.value}</td><td class="src">{a.source}</td></tr>
      {/each}
    </tbody>
  </table>
</div>

<div class="actions">
  <PdfButton make={onpdf} label="Download the full report (PDF)" variant="plain" />
  <button onclick={download}>Download daily results (CSV)</button>
  <button onclick={copyLink}>{copied ? "Link copied" : "Copy link to this scenario"}</button>
</div>

<style>
  .report {
    display: grid;
    grid-template-columns: minmax(0, 7fr) minmax(0, 5fr);
    gap: 48px;
    align-items: start;
  }
  .report p {
    max-width: 72ch;
    font-size: 15.5px;
  }
  .report p + p {
    margin-top: 10px;
  }
  .warnings {
    margin: 16px 0 0;
    padding-left: 18px;
    color: var(--ink-2);
    font-size: 14px;
    max-width: 72ch;
  }
  .warnings li + li {
    margin-top: 4px;
  }
  .text table {
    margin-top: 26px;
    max-width: 72ch;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13.5px;
  }
  caption {
    text-align: left;
    font-weight: 700;
    font-size: 15px;
    margin-bottom: 6px;
  }
  th,
  td {
    text-align: left;
    padding: 6px 8px 6px 0;
    border-bottom: 1px solid var(--hair);
  }
  thead th {
    font-weight: 500;
    color: var(--ink-2);
    font-size: 12.5px;
  }
  tbody th {
    font-weight: 400;
  }
  .numeric {
    text-align: right;
  }
  .src {
    color: var(--ink-2);
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 22px;
  }
  .actions button {
    border: 1px solid var(--hair-2);
    background: var(--plane);
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 14px;
    cursor: pointer;
  }
  .actions button:hover {
    background: color-mix(in oklab, var(--ink) 6%, transparent);
  }
  @media (max-width: 960px) {
    .report {
      grid-template-columns: minmax(0, 1fr);
      gap: 28px;
    }
  }
</style>
