<script lang="ts">
  import { PLANS, VACCINES } from "../../lib/sim/spec";
  import { sim } from "../../lib/sim/store.svelte";
  import ResponsePanel from "./ResponsePanel.svelte";
</script>

<div class="step">
  <h2>How does the country respond?</h2>
  <p class="sub">Choose the restrictions, and whether a vaccine is coming.</p>

  <fieldset>
    <legend>Restrictions</legend>
    <div class="plans">
      {#each PLANS as plan (plan.id)}
        <label class="plan" class:on={sim.spec.plan === plan.id}>
          <input type="radio" name="plan" value={plan.id} checked={sim.spec.plan === plan.id} onchange={() => sim.setPlan(plan.id)} />
          <span><strong>{plan.label}</strong><small>{plan.note}</small></span>
        </label>
      {/each}
    </div>
  </fieldset>

  <fieldset>
    <legend>Vaccine</legend>
    <div class="seg vaccines" role="group" aria-label="Vaccine">
      {#each VACCINES as v}
        <button aria-pressed={sim.spec.vaccine === v.id} onclick={() => sim.setVaccine(v.id)}>{v.label}</button>
      {/each}
    </div>
    {#if sim.spec.vaccine === "custom"}<p class="note">Arrival day set in fine-tuning: day {sim.spec.response.vaccine_day}.</p>{/if}
  </fieldset>

  {#if sim.spec.plan && sim.spec.vaccine}
    <details class="fine" open={sim.spec.plan === "custom"}>
      <summary>Fine-tune the response, timing and behaviour</summary>
      <div class="fine-body"><ResponsePanel /></div>
    </details>
  {/if}
</div>

<style>
  fieldset {
    border: 0;
    margin: 20px 0 0;
    padding: 0;
  }
  legend {
    font-size: 15px;
    font-weight: 700;
    padding: 0;
    margin-bottom: 8px;
  }
  .plans {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 8px;
  }
  .plan {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 10px 12px;
    border: 1px solid var(--hair-2);
    border-radius: 10px;
    background: var(--raise);
    cursor: pointer;
  }
  .plan.on {
    border-color: var(--ink);
    box-shadow: inset 0 0 0 1px var(--ink);
  }
  .plan input {
    margin-top: 4px;
    accent-color: var(--ink);
  }
  .plan span {
    display: grid;
    font-size: 14.5px;
  }
  .plan small {
    color: var(--ink-2);
    font-size: 13px;
  }
  .vaccines {
    flex-wrap: wrap;
  }
  .note {
    margin-top: 6px;
    font-size: 13px;
    color: var(--muted);
  }
</style>
