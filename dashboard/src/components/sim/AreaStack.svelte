<script lang="ts" module>
  export interface Layer {
    id: string;
    label: string;
    values: number[];
    color: string;
  }
</script>

<script lang="ts">
  /** Shares of the population over (simulated) weeks, stacked to 100%. */
  import { scaleLinear } from "d3-scale";
  import { area } from "d3-shape";
  import { pct } from "../../lib/format";
  import Tooltip from "../Tooltip.svelte";

  let { layers, height = 220, ariaLabel }: { layers: Layer[]; height?: number; ariaLabel: string } = $props();

  let width = $state(0);
  let W = $derived(Math.max(width, 160));
  const top = 8;
  const bottom = 24;
  let n = $derived(layers[0]?.values.length ?? 0);
  let total = $derived(Array.from({ length: n }, (_, i) => layers.reduce((s, l) => s + l.values[i], 0) || 1));
  let x = $derived(scaleLinear().domain([0, Math.max(n - 1, 1)]).range([0, W]));
  let y = $derived(scaleLinear().domain([0, 1]).range([height - bottom, top]));
  let stacks = $derived.by(() => {
    const base = new Array(n).fill(0);
    return layers.map((l) => {
      const lo = [...base];
      l.values.forEach((v, i) => (base[i] += v / total[i]));
      const hi = [...base];
      const d =
        area<number>()
          .x((i) => x(i))
          .y0((i) => y(lo[i]))
          .y1((i) => y(hi[i]))(Array.from({ length: n }, (_, i) => i)) ?? "";
      return { ...l, d };
    });
  });
  let ticks = $derived(
    Array.from({ length: Math.floor((n * 7) / 182.5) + 1 }, (_, k) => k * 182.5).map((d) => ({
      i: d / 7,
      label: d === 0 ? "start" : d % 365 === 0 ? `${d / 365} yr` : `${Math.round(d / 30.4167)} mo`,
    })),
  );
  let hover = $state<number | null>(null);
  let svgEl = $state<SVGSVGElement>();
  function move(e: PointerEvent) {
    const b = svgEl!.getBoundingClientRect();
    hover = Math.max(0, Math.min(n - 1, Math.round(x.invert(((e.clientX - b.left) / b.width) * W))));
  }
</script>

<div class="legend">
  {#each layers as l}<span><span class="key" style:background={l.color}></span>{l.label}</span>{/each}
</div>
<div class="stack" bind:clientWidth={width}>
  {#if width && n}
    <svg bind:this={svgEl} viewBox={`0 0 ${W} ${height}`} width={W} {height} role="img" aria-label={ariaLabel}>
      {#each stacks as s (s.id)}
        <path d={s.d} fill={s.color} opacity="0.85" stroke="var(--plane)" stroke-width="1.5" />
      {/each}
      {#each [0.25, 0.5, 0.75] as t}
        <text class="axis-label" x="4" y={y(t) + 4}>{pct(t)}</text>
      {/each}
      {#each ticks as t}
        <!-- The last tick sits at the right edge, so its label ends there instead of running past it. -->
        {@const last = x(t.i) > W - 30}
        <text class="axis-label" x={last ? x(t.i) : x(t.i) + 3} y={height - 7} text-anchor={last ? "end" : "start"}>{t.label}</text>
      {/each}
      {#if hover !== null}<line x1={x(hover)} x2={x(hover)} y1={top} y2={height - bottom} stroke="var(--ink)" opacity="0.5" />{/if}
      <rect
        x="0"
        y={top}
        width={W}
        height={height - bottom - top}
        fill="transparent"
        role="presentation"
        onpointermove={move}
        onpointerleave={() => (hover = null)}
      />
    </svg>
    {#if hover !== null}
      <Tooltip
        x={x(hover)}
        y={top}
        width={W}
        visible={true}
        title={`Week ${hover + 1}`}
        rows={[...layers].reverse().map((l) => ({ color: l.color, label: l.label, value: pct(l.values[hover!] / total[hover!], 1) }))}
      />
    {/if}
  {/if}
</div>

<style>
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 16px;
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
  .stack {
    position: relative;
  }
  svg {
    display: block;
    overflow: visible;
  }
</style>
