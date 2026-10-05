<script lang="ts">
  /**
   * M6, the data-only second opinion: a classifier trained on 381 real COVID-19 waves gives the odds
   * of each severity class for a wave starting in these conditions, independently of the engine.
   */
  import { count, pct } from "../../lib/format";
  import type { EngineOutputs } from "../../lib/sim/engine";
  import { featureVector, PRESET_ERA, waveSeverity } from "../../lib/sim/model";
  import { sim } from "../../lib/sim/store.svelte";

  let { central }: { central: EngineOutputs } = $props();
  let r = $derived(sim.result!);
  let model = $derived(sim.model!);
  let era = $derived(PRESET_ERA[sim.applied!.pathogen.preset ?? ""] ?? null);
  let early = $derived(Array.from(central.stringency.slice(0, 28)).reduce((a, b) => a + b, 0) / 28);
  let odds = $derived(
    era ? waveSeverity(model, featureVector(model, r.settings.signals), { stringency_first_4w: early, vaccinated_at_start: 0, log_prior_deaths_pm: 0 }, era) : null,
  );
  // The engine's own first-wave peak, in the same units, to compare classes.
  let enginePeak = $derived.by(() => {
    let best = 0;
    for (let w = 0; w * 7 < Math.min(central.deaths.length, 364); w++) {
      let s = 0;
      for (let d = w * 7; d < w * 7 + 7 && d < central.deaths.length; d++) s += central.deaths[d];
      best = Math.max(best, (s / r.run.place.population) * 1e6);
    }
    return best;
  });
  let engineClass = $derived(odds ? odds.thresholds.filter((t) => enginePeak > t).length : 0);
  let likely = $derived(odds ? odds.probabilities.indexOf(Math.max(...odds.probabilities)) : 0);
  const RANGES = (t: number[]) => [`under ${t[0].toFixed(0)}`, `${t[0].toFixed(0)}–${t[1].toFixed(0)}`, `${t[1].toFixed(0)}–${t[2].toFixed(0)}`, `over ${t[2].toFixed(0)}`];
</script>

{#if !odds}
  <p class="muted note">Shown for SARS-CoV-2 scenarios only: the classifier learned from real COVID-19 waves and has nothing to say about other diseases.</p>
{:else}
  <ol class="odds">
    {#each odds.classes as c, i}
      <li class:likely={i === likely}>
        <span class="cls">{c}<small>{RANGES(odds.thresholds)[i]} deaths/M/week at peak</small></span>
        <div class="track"><div class="bar" style:width={`${odds.probabilities[i] * 100}%`}></div></div>
        <span class="p num">{pct(odds.probabilities[i])}</span>
      </li>
    {/each}
  </ol>
  <p class="verdict">
    The engine's first-year peak is <strong>{count(enginePeak)}</strong> deaths per million per week: <strong>{odds.classes[engineClass]}</strong>.
    {#if engineClass === likely}The classifier agrees.{:else}The classifier's most likely class is <strong>{odds.classes[likely]}</strong>, so treat the peak with caution.{/if}
  </p>
{/if}

<style>
  .note {
    font-size: 13.5px;
  }
  .odds {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 8px;
  }
  li {
    display: grid;
    grid-template-columns: minmax(150px, 40%) minmax(0, 1fr) 44px;
    gap: 10px;
    align-items: center;
  }
  .cls {
    display: grid;
    font-size: 14px;
    text-transform: capitalize;
  }
  small {
    font-size: 12px;
    color: var(--muted);
    text-transform: none;
  }
  .track {
    height: 10px;
  }
  .bar {
    height: 10px;
    border-radius: 0 3px 3px 0;
    background: var(--faint);
    min-width: 1px;
  }
  .likely .bar {
    background: var(--ink);
  }
  .p {
    text-align: right;
    font-size: 13.5px;
  }
  .verdict {
    margin-top: 12px;
    font-size: 14px;
    color: var(--ink-2);
  }
</style>
