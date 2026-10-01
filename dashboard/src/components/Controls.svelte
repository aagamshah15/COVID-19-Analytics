<script lang="ts">
  import { WHO_REGIONS } from "../lib/data/aggregate";
  import type { Dataset } from "../lib/data/types";
  import { day } from "../lib/format";
  import { app, PRESETS } from "../lib/state/app.svelte";
  import CountrySearch from "./CountrySearch.svelte";

  let { data, showRegion = true, showMeasure = true }: { data: Dataset; showRegion?: boolean; showMeasure?: boolean } = $props();

  const CONTINENTS = ["Africa", "Asia", "Europe", "North America", "Oceania", "South America"];
  let preset = $derived(PRESETS.find((p) => p.from === app.from && p.to === app.to));
</script>

<div class="controls" role="group" aria-label="Filters">
  <div class="seg period" role="group" aria-label="Period">
    {#each PRESETS as p}
      <button aria-pressed={preset === p} onclick={() => app.set({ from: p.from, to: p.to })}>{p.label}</button>
    {/each}
  </div>
  {#if !preset}
    <span class="custom">{day(app.from)} to {day(app.to)}</span>
  {/if}
  {#if showRegion}
    <label>
      <span class="sr-only">Region</span>
      <select value={app.region} onchange={(e) => app.set({ region: e.currentTarget.value })} aria-label="Region">
        <option value="all">All countries</option>
        <optgroup label="Continent">
          {#each CONTINENTS as c}<option value={`continent:${c}`}>{c}</option>{/each}
        </optgroup>
        <optgroup label="WHO region">
          {#each Object.entries(WHO_REGIONS) as [code, name]}<option value={`who:${code}`}>WHO {name}</option>{/each}
        </optgroup>
      </select>
    </label>
  {/if}
  {#if showMeasure}
    <div class="seg" role="group" aria-label="Measure">
      <button aria-pressed={app.measure === "pm"} onclick={() => app.set({ measure: "pm" })}>Per million</button>
      <button aria-pressed={app.measure === "abs"} onclick={() => app.set({ measure: "abs" })}>Absolute</button>
    </div>
  {/if}
  <CountrySearch countries={data.countries} onpick={(c) => app.go("country", c.iso)} />
</div>

<style>
  .controls {
    display: flex;
    flex-wrap: wrap;
    gap: 10px 18px;
    align-items: center;
    font-size: 14px;
    color: var(--ink-2);
  }
  .custom {
    font-size: 13.5px;
    color: var(--ink);
    font-weight: 500;
  }
  @media (max-width: 900px) {
    .period {
      max-width: 100%;
      overflow-x: auto;
    }
  }
</style>
