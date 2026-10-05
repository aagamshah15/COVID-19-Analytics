<script lang="ts">
  /** One-at-a-time sensitivity: how far each input, pushed low and high, moves total deaths. */
  import { compact } from "../../lib/format";
  import type { TornadoBar } from "../../lib/sim/montecarlo";

  let { base, bars }: { base: number; bars: TornadoBar[] } = $props();
  let lo = $derived(Math.min(base, ...bars.map((b) => Math.min(b.low, b.high))));
  let hi = $derived(Math.max(base, ...bars.map((b) => Math.max(b.low, b.high))));
  let x = $derived((v: number) => ((v - lo) / Math.max(hi - lo, 1e-9)) * 100);
</script>

<ol class="tornado" aria-label="Inputs ranked by how much they change total deaths">
  {#each bars as b (b.key)}
    {@const left = Math.min(b.low, b.high)}
    {@const right = Math.max(b.low, b.high)}
    <li>
      <span class="label">{b.label}</span>
      <div class="track">
        <div class="baseline" style:left={`${x(base)}%`}></div>
        <div class="span" style:left={`${x(left)}%`} style:width={`${Math.max(x(right) - x(left), 0.4)}%`}></div>
        <span class="end num" style:right={`${100 - x(left) + 1}%`}>{b.low <= b.high ? b.lowLabel : b.highLabel}</span>
        <span class="end num after" style:left={`${x(right) + 1}%`}>{b.low <= b.high ? b.highLabel : b.lowLabel}</span>
      </div>
      <span class="sr-only">{b.lowLabel}: {compact(b.low)} deaths; {b.highLabel}: {compact(b.high)} deaths.</span>
    </li>
  {/each}
  <li class="axis" aria-hidden="true">
    <span class="label"></span>
    <div class="track">
      <span class="tick num" style:left={`${x(base)}%`}>{compact(base)} deaths in this scenario</span>
    </div>
  </li>
</ol>

<style>
  .tornado {
    list-style: none;
    margin: 0;
    padding: 0;
    position: relative;
  }
  li {
    display: grid;
    grid-template-columns: minmax(120px, 34%) minmax(0, 1fr);
    gap: 12px;
    align-items: center;
    min-height: 26px;
  }
  .label {
    font-size: 13.5px;
    color: var(--ink);
  }
  .track {
    position: relative;
    height: 18px;
  }
  .span {
    position: absolute;
    top: 4px;
    height: 10px;
    background: var(--deaths);
    opacity: 0.85;
    border-radius: 3px;
  }
  .end {
    position: absolute;
    top: 1px;
    font-size: 11.5px;
    color: var(--muted);
    white-space: nowrap;
  }
  .baseline {
    position: absolute;
    top: -4px;
    bottom: -4px;
    border-left: 1px solid var(--ink-2);
  }
  .axis .track {
    border-top: 1px solid var(--muted);
    height: 22px;
  }
  .tick {
    position: absolute;
    top: 4px;
    transform: translateX(-50%);
    font-size: 12px;
    color: var(--ink-2);
    white-space: nowrap;
  }
</style>
