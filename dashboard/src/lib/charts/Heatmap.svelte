<script lang="ts" module>
  export interface HeatRow {
    key: string;
    label: string;
    values: (number | null)[];
  }
</script>

<script lang="ts">
  /** Rows x weeks heatmap on a one-hue ramp. Missing weeks stay blank. */
  import Tooltip from "../../components/Tooltip.svelte";
  import { day } from "../format";
  import { rampColor } from "./ramp";

  interface Props {
    weeks: string[];
    rows: HeatRow[];
    metric: "deaths" | "vax" | "hosp";
    max: number;
    format: (v: number) => string;
    valueLabel: string;
    highlight?: [number, number] | null;
    onpick?: (key: string) => void;
    ariaLabel: string;
  }
  let { weeks, rows, metric, max, format, valueLabel, highlight = null, onpick, ariaLabel }: Props = $props();

  let width = $state(0);
  let W = $derived(Math.max(width, 300));
  let narrow = $derived(W < 560);
  let labelW = $derived(narrow ? 96 : 140);
  const rowH = 16;
  const top = 4;
  let n = $derived(weeks.length);
  let cell = $derived((W - labelW) / n);
  let H = $derived(top + rows.length * rowH + 26);
  let years = $derived(
    weeks
      .map((w, i) => ({ w, i }))
      .filter(({ w, i }) => (i === 0 || w.slice(0, 4) !== weeks[i - 1].slice(0, 4)) && (i === 0 ? weeks.findIndex((x) => x.slice(0, 4) !== w.slice(0, 4)) * cell > 40 : true)),
  );
  let hover = $state<{ r: number; c: number } | null>(null);
  let svgEl = $state<SVGSVGElement>();

  function move(e: PointerEvent) {
    const b = svgEl!.getBoundingClientRect();
    const px = ((e.clientX - b.left) / b.width) * W;
    const py = ((e.clientY - b.top) / b.height) * H;
    const c = Math.floor((px - labelW) / cell);
    const r = Math.floor((py - top) / rowH);
    hover = c >= 0 && c < n && r >= 0 && r < rows.length ? { r, c } : null;
  }
</script>

<div class="heat" bind:clientWidth={width}>
  {#if width}
    <svg bind:this={svgEl} viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={ariaLabel}>
      {#each rows as row, r (row.key)}
        <text class="axis-label row-label" x={labelW - 8} y={top + r * rowH + rowH - 4} text-anchor="end">
          {row.label.length > (narrow ? 13 : 20) ? `${row.label.slice(0, narrow ? 12 : 19)}…` : row.label}
        </text>
        {#each row.values as v, c}
          {#if v !== null}
            <rect
              x={labelW + c * cell}
              y={top + r * rowH + 1}
              width={cell + 0.4}
              height={rowH - 2}
              style:fill={rampColor(metric, Math.min(v / max, 1))}
              opacity={highlight && (c < highlight[0] || c > highlight[1]) ? 0.3 : 1}
            />
          {/if}
        {/each}
      {/each}
      {#each years as y}
        <line x1={labelW + y.i * cell} x2={labelW + y.i * cell} y1={top} y2={H - 20} stroke="var(--hair-2)" />
        <text class="axis-label" x={labelW + y.i * cell + 3} y={H - 6}>{y.w.slice(0, 4)}</text>
      {/each}
      {#if hover}
        <rect x={labelW + hover.c * cell - 0.5} y={top + hover.r * rowH} width={cell + 1} height={rowH} fill="none" stroke="var(--ink)" />
      {/if}
      <rect
        x={labelW}
        y={top}
        width={W - labelW}
        height={rows.length * rowH}
        fill="transparent"
        role="presentation"
        onpointermove={move}
        onpointerleave={() => (hover = null)}
        onclick={() => hover && onpick?.(rows[hover.r].key)}
        style:cursor={onpick ? "pointer" : "default"}
      />
    </svg>
    {#if hover}
      {@const v = rows[hover.r].values[hover.c]}
      <Tooltip
        x={labelW + hover.c * cell}
        y={Math.max(0, top + hover.r * rowH - 70)}
        width={W}
        visible={true}
        title={`${rows[hover.r].label}, week ending ${day(weeks[hover.c])}`}
        rows={[{ color: `var(--${metric})`, label: valueLabel, value: v === null ? "not reported" : format(v) }]}
      />
    {/if}
    <div class="legend">
      <span>0</span>
      {#each [0.1, 0.3, 0.5, 0.7, 0.9] as t}<span class="sw" style:background={rampColor(metric, t)}></span>{/each}
      <span>{format(max)} or more</span>
    </div>
  {/if}
</div>

<style>
  .heat {
    position: relative;
    width: 100%;
  }
  svg {
    display: block;
  }
  .row-label {
    fill: var(--ink-2);
  }
  .legend {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: 12.5px;
    color: var(--ink-2);
    margin-top: 8px;
  }
  .legend span:first-child {
    margin-right: 4px;
  }
  .legend span:last-child {
    margin-left: 4px;
  }
  .sw {
    width: 22px;
    height: 10px;
    border-radius: 2px;
  }
</style>
