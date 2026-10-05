<script lang="ts">
  import { sim } from "../../lib/sim/store.svelte";
  import { CONTAGIOUS, DEADLY, DISEASE_CARDS, MORE_DISEASES, nearestLevel } from "../../lib/sim/words";
  import DiseasePanel from "./DiseasePanel.svelte";

  let preset = $derived(sim.spec.pathogen.preset);
  let p = $derived(sim.resolved!.pathogen);
  let base = $derived(sim.resolved!.basePathogen);
  let inMore = $derived(MORE_DISEASES.some((d) => d.id === preset));
  let contagious = $derived(nearestLevel(CONTAGIOUS, p.r0, "r0"));
  let deadly = $derived(nearestLevel(DEADLY, p.ifr, "ifr"));
  let edited = $derived("r0" in sim.spec.pathogen.edits || "ifr" in sim.spec.pathogen.edits);
</script>

<div class="step">
  <h2>What kind of disease?</h2>
  <p class="sub">Start from a disease people know, then make it more or less contagious or deadly.</p>

  <ul class="cards" role="group" aria-label="Diseases">
    {#each DISEASE_CARDS as d (d.id)}
      <li>
        <button class="card" aria-pressed={preset === d.id} onclick={() => sim.setPreset(d.id)}>
          <strong>{d.label}</strong>
          <span>{d.blurb}</span>
        </button>
      </li>
    {/each}
  </ul>
  <label class="more">
    <span>More diseases</span>
    <select value={inMore ? preset : ""} onchange={(e) => e.currentTarget.value && sim.setPreset(e.currentTarget.value)}>
      <option value="">Choose…</option>
      {#each MORE_DISEASES as d}<option value={d.id}>{d.label}</option>{/each}
    </select>
  </label>

  {#if preset}
    {#if base.kind === "hypothetical"}
      <p class="flag">This one is hypothetical: bird flu has never spread easily between people. How contagious it would be is a guess.</p>
    {/if}
    <div class="dial">
      <span class="label">How contagious</span>
      <div class="seg" role="group" aria-label="How contagious">
        {#each CONTAGIOUS as level, i}
          <button aria-pressed={contagious === i} onclick={() => sim.setPathogen("r0", level.r0)} title={`Each case infects about ${level.r0} others, ${level.note}`}>{level.label}</button>
        {/each}
      </div>
      <span class="note">Each case infects about {p.r0.toFixed(p.r0 < 10 ? 1 : 0)} others{p.r0 < 1 ? ", so outbreaks fizzle out" : ""}</span>
    </div>
    <div class="dial">
      <span class="label">How deadly</span>
      <div class="seg" role="group" aria-label="How deadly">
        {#each DEADLY as level, i}
          <button aria-pressed={deadly === i} onclick={() => sim.setPathogen("ifr", level.ifr)}>{level.label}</button>
        {/each}
      </div>
      <span class="note">About 1 in {Math.round(1 / p.ifr).toLocaleString("en-US")} infections fatal, for a world-average mix of ages</span>
    </div>
    {#if edited}
      <button class="link-button" onclick={() => (sim.resetPathogen("r0"), sim.resetPathogen("ifr"))}>Back to {base.name}'s values</button>
    {/if}

    <details class="fine">
      <summary>Fine-tune the disease</summary>
      <div class="fine-body"><DiseasePanel /></div>
    </details>
  {/if}
</div>

<style>
  .cards {
    list-style: none;
    margin: 18px 0 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
    gap: 10px;
  }
  .card {
    width: 100%;
    height: 100%;
    text-align: left;
    display: grid;
    align-content: start;
    gap: 4px;
    padding: 12px 14px;
    background: var(--raise);
    border: 1px solid var(--hair-2);
    border-radius: 10px;
    cursor: pointer;
  }
  .card strong {
    font-size: 15px;
  }
  .card span {
    font-size: 13px;
    color: var(--ink-2);
  }
  .card[aria-pressed="true"] {
    border-color: var(--ink);
    box-shadow: inset 0 0 0 1px var(--ink);
  }
  .more {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    margin-top: 12px;
    font-size: 14px;
    color: var(--ink-2);
  }
  .flag {
    margin-top: 16px;
    font-size: 14px;
    border-left: 3px solid var(--hosp);
    padding-left: 10px;
  }
  .dial {
    display: grid;
    grid-template-columns: 130px auto;
    align-items: center;
    gap: 6px 16px;
    margin-top: 18px;
  }
  .label {
    font-size: 15px;
  }
  .dial .seg {
    justify-self: start;
  }
  .note {
    grid-column: 2;
    font-size: 13px;
    color: var(--muted);
  }
  .link-button {
    margin-top: 12px;
  }
  @media (max-width: 640px) {
    .dial {
      grid-template-columns: minmax(0, 1fr);
    }
    .note {
      grid-column: 1;
    }
  }
</style>
