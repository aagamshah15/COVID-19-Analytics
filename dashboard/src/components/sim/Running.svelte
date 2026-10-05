<script lang="ts">
  /** Shown while a scenario runs: what the simulator is doing, step by step. */
  import { compact } from "../../lib/format";

  let { phase, place, days, draws }: { phase: number; place: { name: string; population: number }; days: number; draws: number } = $props();
  let steps = $derived([
    `Building the population of ${place.name} (${compact(place.population)} people in five age groups)`,
    `Simulating the outbreak day by day for ${days} days`,
    `Re-running it ${draws} times with uncertain inputs, to find the likely range`,
    "Testing which choices make the biggest difference",
  ]);
</script>

<section class="running" role="status" aria-live="polite" aria-label="Running the simulation">
  <h2>Running your scenario…</h2>
  <ol>
    {#each steps as s, i}
      <li class:done={phase > i} class:active={phase === i}>
        <span class="mark" aria-hidden="true">{#if phase > i}✓{:else if phase === i}<span class="spin"></span>{/if}</span>
        <span>{s}</span>
      </li>
    {/each}
  </ol>
  <p class="note">Everything runs here in your browser. Nothing is sent anywhere.</p>
</section>

<style>
  .running {
    max-width: 640px;
    margin: 40px 0 60px;
  }
  ol {
    list-style: none;
    margin: 20px 0 0;
    padding: 0;
    display: grid;
    gap: 12px;
  }
  li {
    display: flex;
    gap: 12px;
    align-items: center;
    font-size: 16px;
    color: var(--muted);
    transition: color 0.2s;
  }
  li.active,
  li.done {
    color: var(--ink);
  }
  .mark {
    display: inline-grid;
    place-items: center;
    width: 22px;
    height: 22px;
    flex: none;
    border-radius: 50%;
    border: 1.5px solid var(--hair-2);
    font-size: 12px;
    font-weight: 700;
  }
  .done .mark {
    background: var(--ink);
    border-color: var(--ink);
    color: var(--plane);
  }
  .spin {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    border: 2px solid var(--hair-2);
    border-top-color: var(--ink);
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  .note {
    margin-top: 22px;
    font-size: 13.5px;
    color: var(--muted);
  }
</style>
