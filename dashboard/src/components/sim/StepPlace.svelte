<script lang="ts">
  import type { Country } from "../../lib/data/types";
  import { compact } from "../../lib/format";
  import type { Shift } from "../../lib/sim/spec";
  import { sim } from "../../lib/sim/store.svelte";
  import CountrySearch from "../CountrySearch.svelte";
  import PlacePanel from "./PlacePanel.svelte";

  let { countries }: { countries: Country[] } = $props();
  let model = $derived(sim.model!);
  let pickable = $derived(countries.filter((c) => model.byIso.has(c.iso)));
  const QUICK = ["USA", "IND", "BRA", "NGA", "DEU", "JPN"];
  let chosen = $derived(sim.spec.iso ? model.byIso.get(sim.spec.iso) : null);
  let r = $derived(sim.resolved!);
  const people = (n: number) => (n >= 1e9 ? `${(n / 1e9).toFixed(1)} billion` : n >= 1e6 ? `${Math.round(n / 1e6)} million` : compact(n));
  const SHIFTS: { value: Shift; age: string; care: string }[] = [
    { value: -1, age: "Younger", care: "Weaker" },
    { value: 0, age: "As it is", care: "As it is" },
    { value: 1, age: "Older", care: "Stronger" },
  ];
</script>

<div class="step">
  <h2>Where does the outbreak start?</h2>
  <p class="sub">Pick a real country. Its population, health system and how its people behaved in 2020–2022 set the starting point.</p>

  <div class="search">
    <CountrySearch countries={pickable} onpick={(c) => sim.setCountry(c.iso)} placeholder="Search for a country" label="Search for a country" />
  </div>
  <div class="quick" role="group" aria-label="Popular choices">
    {#each QUICK as iso}
      {@const c = model.byIso.get(iso)}
      {#if c}<button aria-pressed={sim.spec.iso === iso} onclick={() => sim.setCountry(iso)}>{c.name}</button>{/if}
    {/each}
  </div>

  {#if chosen}
    <div class="profile">
      <h3>{chosen.name}</h3>
      <p>
        {people(r.settings.population)} people. Half are younger than {Math.round(r.settings.signals.median_age ?? 30)}.
        {#if r.settings.signals.hospital_beds_per_thousand !== null}{r.settings.signals.hospital_beds_per_thousand.toFixed(1)} hospital beds for every 1,000 people.{/if}
        {#if r.settings.signals.health_exp_per_capita !== null}About ${compact(r.settings.signals.health_exp_per_capita)} a year spent on health per person.{/if}
      </p>
    </div>

    <div class="choice">
      <span class="label">Population</span>
      <div class="seg" role="group" aria-label="Population age">
        {#each SHIFTS as s}<button aria-pressed={sim.spec.simple.age === s.value} onclick={() => sim.setSimple("age", s.value)}>{s.age}</button>{/each}
      </div>
    </div>
    <div class="choice">
      <span class="label">Healthcare</span>
      <div class="seg" role="group" aria-label="Healthcare">
        {#each SHIFTS as s}<button aria-pressed={sim.spec.simple.care === s.value} onclick={() => sim.setSimple("care", s.value)}>{s.care}</button>{/each}
      </div>
    </div>

    <details class="fine">
      <summary>Fine-tune {chosen.name}'s characteristics</summary>
      <div class="fine-body"><PlacePanel /></div>
    </details>
  {/if}
</div>

<style>
  .search {
    margin-top: 18px;
  }
  .search :global(input) {
    width: min(100%, 360px);
    font-size: 16px;
    padding: 10px 12px;
  }
  .quick {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 10px;
  }
  .quick button {
    border: 1px solid var(--hair-2);
    background: var(--plane);
    border-radius: 999px;
    padding: 4px 12px;
    font-size: 13.5px;
    color: var(--ink-2);
    cursor: pointer;
  }
  .quick button[aria-pressed="true"] {
    background: var(--ink);
    border-color: var(--ink);
    color: var(--plane);
  }
  .profile {
    margin-top: 22px;
    padding: 14px 16px;
    border-left: 3px solid var(--ink);
    background: var(--raise);
    border-radius: 0 10px 10px 0;
  }
  .profile p {
    margin-top: 4px;
    color: var(--ink-2);
    font-size: 15px;
  }
  .choice {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px 16px;
    margin-top: 16px;
  }
  .label {
    width: 100px;
    font-size: 15px;
  }
</style>
