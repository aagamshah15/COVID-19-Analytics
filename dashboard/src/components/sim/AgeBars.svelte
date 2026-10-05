<script lang="ts">
  /** Share of the population vs share of deaths, by age band: who carries the burden. */
  import { pct } from "../../lib/format";
  import { BANDS } from "../../lib/sim/scenario";

  let { population, deaths }: { population: number[]; deaths: number[] } = $props();
  let totalDeaths = $derived(deaths.reduce((a, b) => a + b, 0));
  let rows = $derived(
    BANDS.map((band, i) => ({ band, pop: population[i], dead: totalDeaths > 0 ? deaths[i] / totalDeaths : 0 })),
  );
  let max = $derived(Math.max(...rows.map((r) => Math.max(r.pop, r.dead)), 1e-9));
</script>

<div class="legend" aria-hidden="true">
  <span><span class="key pop"></span>Share of people</span>
  <span><span class="key dead"></span>Share of deaths</span>
</div>
<table class="bars">
  <caption class="sr-only">Share of the population and share of deaths by age band</caption>
  <thead class="sr-only"><tr><th>Age</th><th>Share of people</th><th>Share of deaths</th></tr></thead>
  <tbody>
    {#each rows as r (r.band)}
      <tr>
        <th scope="row">{r.band}</th>
        <td>
          <div class="pair">
            <div class="track"><div class="bar pop" style:width={`${(r.pop / max) * 100}%`}></div><span class="v num">{pct(r.pop)}</span></div>
            <div class="track"><div class="bar dead" style:width={`${(r.dead / max) * 100}%`}></div><span class="v num">{pct(r.dead)}</span></div>
          </div>
        </td>
      </tr>
    {/each}
  </tbody>
</table>

<style>
  .legend {
    display: flex;
    gap: 18px;
    font-size: 13px;
    color: var(--ink-2);
    margin-bottom: 10px;
  }
  .key {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 2px;
    margin-right: 6px;
    vertical-align: -1px;
  }
  .bars {
    width: 100%;
    border-collapse: collapse;
  }
  th {
    text-align: left;
    font-weight: 500;
    font-size: 13.5px;
    color: var(--ink-2);
    width: 56px;
    padding: 6px 8px 6px 0;
    vertical-align: middle;
    font-variant-numeric: tabular-nums;
  }
  td {
    padding: 6px 0;
  }
  .pair {
    display: grid;
    gap: 2px;
  }
  .track {
    display: flex;
    align-items: center;
    gap: 8px;
    height: 12px;
  }
  .bar {
    height: 10px;
    border-radius: 0 3px 3px 0;
    min-width: 1px;
  }
  .pop,
  .key.pop {
    background: var(--faint);
  }
  .dead,
  .key.dead {
    background: var(--deaths);
  }
  .v {
    font-size: 12.5px;
    color: var(--ink-2);
  }
</style>
