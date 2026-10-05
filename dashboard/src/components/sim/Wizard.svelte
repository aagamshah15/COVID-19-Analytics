<script lang="ts">
  /** The three guided steps, ending in Run. Nothing is simulated until Run is pressed. */
  import type { Country } from "../../lib/data/types";
  import { sim } from "../../lib/sim/store.svelte";
  import StepDisease from "./StepDisease.svelte";
  import StepPlace from "./StepPlace.svelte";
  import StepResponse from "./StepResponse.svelte";

  let { countries }: { countries: Country[] } = $props();
  const TITLES = ["Where?", "What disease?", "How does it respond?"];
  let ready = $derived([sim.spec.iso !== null, sim.spec.pathogen.preset !== null, sim.spec.plan !== null && sim.spec.vaccine !== null]);
  let canNext = $derived(ready[sim.step - 1]);
  let missing = $derived(
    sim.step === 1 ? "Pick a country to continue." : sim.step === 2 ? "Pick a disease to continue." : !sim.spec.plan ? "Choose the restrictions." : "Choose the vaccine option.",
  );
  let top = $state<HTMLElement>();
  function go(step: 1 | 2 | 3) {
    sim.step = step;
    top?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
</script>

<section class="wizard" bind:this={top} aria-label="Build a scenario">
  <ol class="progress">
    {#each TITLES as title, i}
      {@const n = (i + 1) as 1 | 2 | 3}
      <li class:current={sim.step === n} class:done={ready[i]}>
        <button onclick={() => go(n)} disabled={n > 1 && !ready.slice(0, i).every(Boolean)} aria-current={sim.step === n ? "step" : undefined}>
          <span class="dot">{ready[i] && sim.step !== n ? "✓" : n}</span>{title}
        </button>
      </li>
    {/each}
  </ol>

  <div class="body">
    {#if sim.step === 1}
      <StepPlace {countries} />
    {:else if sim.step === 2}
      <StepDisease />
    {:else}
      <StepResponse />
    {/if}
  </div>

  <div class="nav">
    {#if sim.step > 1}
      <button class="ghost" onclick={() => go((sim.step - 1) as 1 | 2)}>← <span class="long">Back</span></button>
    {:else if sim.applied}
      <button class="ghost" onclick={() => (sim.view = "results")} aria-label="Back to results">← <span class="long">Back to results</span></button>
    {:else}
      <button class="ghost" onclick={() => sim.startOver()} aria-label="Back to ready-made scenarios">← <span class="long">Ready-made scenarios</span></button>
    {/if}
    <span class="hint" aria-live="polite">{canNext ? "" : missing}</span>
    {#if sim.step < 3}
      <!-- Once every question is answered (e.g. when changing a scenario), Run is one click from any step. -->
      <button class={sim.complete ? "ghost" : "primary"} disabled={!canNext} onclick={() => go((sim.step + 1) as 2 | 3)}>Next →</button>
    {/if}
    {#if sim.step === 3 || sim.complete}
      <button class="primary" disabled={!sim.complete} onclick={() => sim.run()}>Run <span class="long">simulation</span></button>
    {/if}
  </div>
</section>

<style>
  .wizard {
    max-width: 880px;
    scroll-margin-top: 20px;
  }
  .progress {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 6px 24px;
    border-bottom: 1px solid var(--hair);
    padding-bottom: 14px;
  }
  .progress button {
    display: flex;
    align-items: center;
    gap: 8px;
    background: none;
    border: 0;
    padding: 0;
    font-size: 15px;
    color: var(--muted);
    cursor: pointer;
  }
  .progress button:disabled {
    cursor: default;
  }
  .current button,
  .done button {
    color: var(--ink);
  }
  .current button {
    font-weight: 700;
  }
  .dot {
    display: inline-grid;
    place-items: center;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 1.5px solid currentColor;
    font-size: 12.5px;
    font-weight: 700;
  }
  .current .dot {
    background: var(--ink);
    color: var(--plane);
    border-color: var(--ink);
  }
  .body {
    padding: 26px 0 8px;
  }
  .body :global(h2) {
    font-size: 26px;
  }
  .body :global(.sub) {
    margin-top: 6px;
    color: var(--ink-2);
    font-size: 15.5px;
    max-width: 64ch;
  }
  .body :global(.fine) {
    margin-top: 26px;
    border-top: 1px solid var(--hair);
    padding-top: 14px;
  }
  .body :global(.fine > summary) {
    cursor: pointer;
    font-size: 14.5px;
    color: var(--ink-2);
    font-weight: 500;
  }
  .body :global(.fine-body) {
    margin-top: 10px;
    max-width: 520px;
  }
  .nav {
    position: sticky;
    bottom: 0;
    z-index: 3;
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 14px 0;
    margin-top: 18px;
    background: var(--plane);
    border-top: 1px solid var(--hair);
  }
  .hint {
    flex: 1;
    font-size: 13.5px;
    color: var(--muted);
    text-align: right;
  }
  .ghost {
    background: none;
    border: 1px solid var(--hair-2);
    border-radius: 10px;
    padding: 10px 16px;
    font-size: 15px;
    cursor: pointer;
  }
  .primary {
    background: var(--ink);
    color: var(--plane);
    border: 0;
    border-radius: 10px;
    padding: 11px 22px;
    font-size: 16px;
    font-weight: 500;
    cursor: pointer;
  }
  @media (max-width: 480px) {
    .long {
      display: none;
    }
    .nav {
      gap: 8px;
    }
  }
  .primary:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }
</style>
