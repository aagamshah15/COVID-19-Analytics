<script lang="ts">
  /** The real countries most like this place, and what COVID-19 actually did there in 2020-2021. */
  import type { Dataset } from "../../lib/data/types";
  import { count } from "../../lib/format";
  import { analogs, featureVector } from "../../lib/sim/model";
  import { sim } from "../../lib/sim/store.svelte";
  import { app } from "../../lib/state/app.svelte";

  let { data }: { data: Dataset } = $props();
  let r = $derived(sim.result!);
  let result = $derived(analogs(sim.model!, featureVector(sim.model!, r.settings.signals), 5));
  let end2021 = $derived(data.weeks.findIndex((w) => w > "2021-12-31"));
  const W = 120;
  const H = 26;
  function spark(iso: string): string {
    const s = data.series[iso]?.dpm.slice(0, end2021);
    if (!s) return "";
    const max = Math.max(1e-9, ...s.map((v) => v ?? 0));
    let d = "";
    s.forEach((v, i) => {
      if (v === null) return;
      d += `${d && s[i - 1] !== null ? "L" : "M"}${((i / (s.length - 1)) * W).toFixed(1)},${(H - (v / max) * (H - 2)).toFixed(1)}`;
    });
    return d;
  }
</script>

{#if result.outOfRange}
  <p class="flag">These characteristics are unlike any real country, so the learned country effects are an extrapolation.</p>
{/if}
<table>
  <caption class="sr-only">Most similar real countries and their COVID-19 deaths, 2020-2021</caption>
  <thead>
    <tr>
      <th scope="col">Country</th>
      <th scope="col">Weekly deaths per million, 2020–21</th>
      <th scope="col" class="numeric">Reported per million</th>
      <th scope="col" class="numeric">Excess per million</th>
    </tr>
  </thead>
  <tbody>
    {#each result.nearest as n (n.country.iso)}
      <tr>
        <th scope="row">
          <a href={app.link("country", n.country.iso)}>{n.country.name}</a>
        </th>
        <td>
          <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
            <line x1="0" x2={W} y1={H - 0.5} y2={H - 0.5} stroke="var(--hair)" />
            <path d={spark(n.country.iso)} fill="none" stroke="var(--deaths)" stroke-width="1.5" />
          </svg>
        </td>
        <td class="numeric num">{count(n.country.outcomes.reported_deaths_pm_2021)}</td>
        <td class="numeric num">{n.country.outcomes.excess_deaths_pm_2021 === null ? "–" : count(n.country.outcomes.excess_deaths_pm_2021)}</td>
      </tr>
    {/each}
  </tbody>
</table>

<style>
  .flag {
    font-size: 13.5px;
    border-left: 3px solid var(--hosp);
    padding-left: 10px;
    margin-bottom: 10px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13.5px;
  }
  th,
  td {
    text-align: left;
    padding: 6px 8px 6px 0;
    border-bottom: 1px solid var(--hair);
    vertical-align: middle;
  }
  thead th {
    font-weight: 500;
    color: var(--ink-2);
    font-size: 12.5px;
  }
  tbody th {
    font-weight: 500;
  }
  .numeric {
    text-align: right;
  }
  svg {
    display: block;
  }
</style>
