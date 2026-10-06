<script lang="ts">
  /**
   * The optional cloud analysis: thousands of runs on the Python reference engine and a breakdown of where
   * the uncertainty comes from. Shown only when the service is configured and answering; everything
   * else on the page is computed in the browser and never waits for it.
   */
  import { onDestroy } from "svelte";
  import { compact, count, pct } from "../../lib/format";
  import { CloudError, type CloudService, cloudService, combinedShare, type DeepResult, deepAnalysis, waitWords } from "../../lib/sim/cloud";
  import type { EnsembleResult, ScenarioRun, Summary } from "../../lib/sim/montecarlo";
  import ChartFrame from "../ChartFrame.svelte";
  import SobolBars from "./SobolBars.svelte";

  let { run, ensemble }: { run: ScenarioRun; ensemble: EnsembleResult } = $props();

  let service = $state<CloudService | null>(null);
  cloudService().then((s) => (service = s));

  let running = $state(false);
  let seconds = $state(0);
  let result = $state<DeepResult | null>(null);
  let problem = $state<string | null>(null);
  let timer: ReturnType<typeof setInterval> | undefined;
  onDestroy(() => clearInterval(timer));
  const UNAFFECTED = "Everything else on this page was worked out in your browser and isn't affected.";

  async function start() {
    running = true;
    problem = null;
    seconds = 0;
    timer = setInterval(() => seconds++, 1000);
    try {
      result = await deepAnalysis($state.snapshot(run) as ScenarioRun);
    } catch (e) {
      const error = e instanceof CloudError ? e : new CloudError("unavailable");
      if (error.kind === "busy") {
        const when = error.retryAfter ? `in ${waitWords(error.retryAfter)}` : "in a minute";
        const why = (error.retryAfter ?? 0) > 3600 ? "has reached its free limit for today" : "is busy";
        problem = `The cloud service ${why}. Try again ${when}. ${UNAFFECTED}`;
      } else if (error.kind === "rejected") {
        problem = `The cloud service couldn't run this scenario. ${UNAFFECTED}`;
      } else {
        problem = `The cloud service didn't answer. ${UNAFFECTED}`;
      }
    } finally {
      clearInterval(timer);
      running = false;
    }
  }

  const OUTCOMES: { key: keyof Summary; label: string }[] = [
    { key: "deaths", label: "Deaths" },
    { key: "infections", label: "Infections" },
    { key: "peak_hospital", label: "Most in hospital at once" },
  ];
  let top = $derived(result?.sobol.factors[0] ?? null);
</script>

{#if service}
  <section class="section deep" aria-live="polite">
    <h2>A deeper look, run in the cloud</h2>
    {#if !result}
      <p class="sub">
        Your browser tried {count(ensemble.draws)} versions of this scenario. A small cloud service can try {count(service.draws)}, and work out how much of the uncertainty
        each input is responsible for, on its own and in combination with the others.
      </p>
      <div class="go">
        <button onclick={start} disabled={running}>{running ? `Running… ${seconds} s` : problem ? "Try again" : "Run the deeper analysis"}</button>
        <span class="note">
          {#if running}
            Trying {count(service.draws)} versions of this scenario, then a few thousand more to see which inputs matter.
          {:else}
            Sends this scenario's settings, and nothing about you, to the service. Takes 15 to 50 seconds.
          {/if}
        </span>
      </div>
      {#if problem}<p class="problem" role="status">{problem}</p>{/if}
    {:else if top}
      <p class="sub finding">
        {#if top.total > 0}
          <strong>{top.label}</strong> accounts for about {pct(top.total)} of the uncertainty in deaths.
          {#if combinedShare(top) >= 0.05}
            About {pct(Math.min(top.first, top.total))} is its effect on its own; the rest appears only in combination with other inputs, which the
            one-at-a-time chart above can't show.
          {:else}
            Nearly all of that is its effect on its own, not a combination with other inputs.
          {/if}
        {:else}
          Deaths come out the same in every run, so there is no uncertainty to share out between the inputs.
        {/if}
      </p>
      <div class="grid">
        <ChartFrame
          title="Where the uncertainty in deaths comes from"
          subtitle="Each input's share of the spread in total deaths across the runs. Shares can add up to more than 100% when inputs act together."
          source={null}
          columns={[
            { key: "label", label: "Uncertain input" },
            { key: "first", label: "On its own", numeric: true, format: (v) => pct(v as number, 1) },
            { key: "total", label: "With other inputs", numeric: true, format: (v) => pct(v as number, 1) },
            { key: "interval", label: `${pct(result.sobol.confidence)} interval`, numeric: true },
          ]}
          rows={result.sobol.factors.map((f) => ({
            label: f.label,
            first: Math.min(f.first, f.total), // an input can't explain more alone than it does in all
            total: f.total,
            interval: `${(f.total_interval[0] * 100).toFixed(1)}–${pct(f.total_interval[1], 1)}`,
          }))}
        >
          {#snippet legend()}
            <span><i class="key alone"></i>On its own</span>
            <span><i class="key together"></i>In combination with other inputs</span>
            <span><i class="key interval"></i>{pct(result!.sobol.confidence)} interval of the estimate</span>
          {/snippet}
          <SobolBars factors={result.sobol.factors} confidence={result.sobol.confidence} />
        </ChartFrame>

        <div>
          <table>
            <caption>{count(result.monte_carlo.draws)} runs against {count(ensemble.draws)}</caption>
            <thead>
              <tr>
                <th scope="col">Outcome</th>
                <th scope="col" class="numeric">In your browser</th>
                <th scope="col" class="numeric">In the cloud</th>
              </tr>
            </thead>
            <tbody>
              {#each OUTCOMES as o}
                <tr>
                  <th scope="row">{o.label}</th>
                  {#each [ensemble.summary.quantiles[o.key], result.monte_carlo.quantiles[o.key]] as q}
                    <td class="numeric num">{compact(q[2])}<span class="range">{compact(q[0])} to {compact(q[4])}</span></td>
                  {/each}
                </tr>
              {/each}
            </tbody>
          </table>
          <p class="foot">
            The middle run, then the range 9 in 10 runs fall in. The two columns come from separate engines, one in TypeScript and one in Python, drawing
            their own random inputs, so close agreement is a check on both.
          </p>
          <p class="foot">
            Worked out in {(result.ms / 1000).toFixed(result.ms < 10_000 ? 1 : 0)} seconds: {count(result.monte_carlo.draws)} runs for the ranges and
            {count(result.sobol.evaluations)} for the breakdown (Sobol indices, Saltelli design).
          </p>
        </div>
      </div>
    {/if}
  </section>
{/if}

<style>
  .sub {
    color: var(--ink-2);
    font-size: 14.5px;
    margin-top: 4px;
    max-width: 72ch;
  }
  .finding {
    font-size: 15.5px;
    color: var(--ink);
  }
  .go {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px 16px;
    margin-top: 16px;
  }
  button {
    border: 1px solid var(--ink);
    background: var(--ink);
    color: var(--plane);
    border-radius: 10px;
    padding: 9px 16px;
    font-size: 14.5px;
    font-weight: 500;
    cursor: pointer;
    white-space: nowrap;
  }
  button:hover:not(:disabled) {
    background: color-mix(in oklab, var(--ink) 86%, var(--plane));
  }
  button:disabled {
    cursor: progress;
    opacity: 0.75;
    font-variant-numeric: tabular-nums;
  }
  .note {
    font-size: 13.5px;
    color: var(--muted);
    max-width: 60ch;
  }
  .problem {
    margin-top: 14px;
    max-width: 72ch;
    font-size: 14.5px;
    color: var(--ink);
    border-left: 3px solid var(--warning);
    padding-left: 12px;
  }
  .grid {
    display: grid;
    grid-template-columns: minmax(0, 7fr) minmax(0, 5fr);
    gap: 48px;
    align-items: start;
    margin-top: 22px;
  }
  .key {
    display: inline-block;
    width: 14px;
    height: 10px;
    margin-right: 6px;
    border-radius: 2px;
    vertical-align: -1px;
  }
  .key.alone {
    background: var(--deaths);
  }
  .key.together {
    background: color-mix(in oklab, var(--deaths) 42%, var(--plane));
    box-shadow: inset 0 0 0 1px var(--deaths);
  }
  .key.interval {
    height: 2px;
    background: var(--ink-2);
    vertical-align: 3px;
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
    padding-right: 0;
    padding-left: 8px;
    white-space: nowrap;
  }
  .range {
    display: block;
    font-size: 12.5px;
    color: var(--muted);
  }
  /* The section already has its heading: the chart's title sits a level below it, like the table's. */
  .grid :global(.frame h2) {
    font-size: 15px;
  }
  .foot {
    margin-top: 10px;
    font-size: 13px;
    color: var(--muted);
    max-width: 60ch;
  }
  @media (max-width: 960px) {
    .grid {
      grid-template-columns: minmax(0, 1fr);
      gap: 28px;
    }
  }
</style>
