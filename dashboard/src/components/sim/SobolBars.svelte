<script lang="ts">
  /**
   * Where the uncertainty comes from: each input's share of the spread in the outcome. The solid part
   * of a bar is the input acting on its own (first-order Sobol index); the outlined part is what it
   * adds in combination with other inputs (up to the total-order index). The thin line underneath
   * is the interval around the full bar.
   */
  import { pct } from "../../lib/format";
  import type { SobolFactor } from "../../lib/sim/cloud";
  import Tooltip from "../Tooltip.svelte";

  let { factors, confidence }: { factors: SobolFactor[]; confidence: number } = $props();
  // Shares under a point would be bars too thin to see: they are counted in a note and listed in the
  // table view. A bar is split into its two parts only when the second part is wide enough to read.
  const MIN_SHARE = 0.01;
  const MIN_SPLIT = 0.02;
  let shown = $derived(factors.filter((f, i) => i === 0 || f.total >= MIN_SHARE));
  let hidden = $derived(factors.length - shown.length);
  const share = (v: number) => (v > 0 && v < 0.005 ? "<1%" : pct(v));
  const range = (r: [number, number]) => `${pct(r[0])} to ${pct(r[1])}`;

  let box = $state<HTMLElement>();
  let width = $state(0);
  let tip = $state<{ x: number; y: number; factor: SobolFactor } | null>(null);
  function hover(event: PointerEvent, factor: SobolFactor) {
    const bounds = box!.getBoundingClientRect();
    tip = { x: event.clientX - bounds.left, y: event.clientY - bounds.top + 14, factor };
  }
</script>

<div class="wrap" bind:this={box} bind:clientWidth={width}>
  <ol class="bars" aria-label="Uncertain inputs ranked by their share of the spread in total deaths">
    {#each shown as f (f.key)}
      {@const together = f.total - f.first >= MIN_SPLIT ? f.total - f.first : 0}
      {@const alone = f.total - together}
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions (the tooltip repeats the hidden text below) -->
      <li onpointermove={(e) => hover(e, f)} onpointerleave={() => (tip = null)}>
        <span class="label">{f.label}</span>
        <div class="track">
          <div class="bar">
            {#if alone > 0}<span class="alone" style:width={`${alone * 100}%`}></span>{/if}
            {#if together > 0}<span class="together" style:width={`${together * 100}%`}></span>{/if}
          </div>
          <span class="interval" style:left={`${f.total_interval[0] * 100}%`} style:width={`${Math.max((f.total_interval[1] - f.total_interval[0]) * 100, 0.3)}%`}></span>
        </div>
        <span class="value num" aria-hidden="true">{share(f.total)}</span>
        <span class="sr-only">
          {share(f.total)} of the spread ({range(f.total_interval)}); {share(Math.min(f.first, f.total))} on its own.
        </span>
      </li>
    {/each}
    <li class="axis" aria-hidden="true">
      <span class="label"></span>
      <div class="track">
        {#each [0, 0.25, 0.5, 0.75, 1] as t}
          <span class="tick num" class:first={t === 0} class:last={t === 1} class:minor={t % 0.5 !== 0} style:left={`${t * 100}%`}>{pct(t)}</span>
        {/each}
      </div>
      <span class="value"></span>
    </li>
  </ol>
  {#if hidden > 0}
    <p class="rest">{hidden} other input{hidden === 1 ? "" : "s"} each account for under 1%.</p>
  {/if}
  <Tooltip
    x={tip?.x ?? 0}
    y={tip?.y ?? 0}
    {width}
    visible={tip !== null}
    title={tip?.factor.label}
    rows={tip
      ? [
          { label: "On its own", value: share(Math.min(tip.factor.first, tip.factor.total)) },
          { label: "With other inputs", value: share(tip.factor.total) },
          { label: `${pct(confidence)} interval`, value: range(tip.factor.total_interval) },
        ]
      : []}
  />
</div>

<style>
  .wrap {
    position: relative;
  }
  .bars {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li {
    display: grid;
    grid-template-columns: minmax(120px, 34%) minmax(0, 1fr) 44px;
    gap: 12px;
    align-items: center;
    min-height: 32px;
    padding: 3px 0;
  }
  .label {
    font-size: 13.5px;
    line-height: 1.3;
    color: var(--ink);
  }
  .track {
    position: relative;
    height: 20px;
  }
  .bar {
    position: absolute;
    inset: 2px 0 auto 0;
    height: 10px;
    display: flex;
    gap: 2px;
  }
  .alone,
  .together {
    height: 100%;
    min-width: 2px;
  }
  .alone {
    background: var(--deaths);
    border-radius: 0 2px 2px 0;
  }
  /* A lighter step of the same hue, outlined so it still reads against the page. */
  .together {
    background: color-mix(in oklab, var(--deaths) 42%, var(--plane));
    box-shadow: inset 0 0 0 1px var(--deaths);
    border-radius: 0 2px 2px 0;
  }
  .interval {
    position: absolute;
    top: 15px;
    height: 2px;
    background: var(--ink-2);
    border-radius: 1px;
  }
  .value {
    font-size: 13px;
    color: var(--ink);
    text-align: right;
  }
  .axis {
    min-height: 0;
  }
  .axis .track {
    border-top: 1px solid var(--hair-2);
    height: 22px;
    margin-top: 4px;
  }
  .tick {
    position: absolute;
    top: 4px;
    transform: translateX(-50%);
    font-size: 12px;
    color: var(--muted);
  }
  .tick.first {
    transform: none;
  }
  .tick.last {
    transform: translateX(-100%);
  }
  @media (max-width: 560px) {
    .tick.minor {
      display: none;
    }
  }
  .rest {
    margin-top: 6px;
    font-size: 13px;
    color: var(--muted);
  }
</style>
