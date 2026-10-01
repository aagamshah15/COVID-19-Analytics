<script lang="ts" module>
  export interface Dot {
    key: string;
    label: string;
    x: number;
    y: number;
    emphasis: boolean;
    note?: string;
  }
</script>

<script lang="ts">
  /**
   * Scatter with one emphasis hue (selected group) over grey context dots. Nearest-point hover
   * so readers don't have to land on an 8px dot; click opens the country.
   */
  import { scaleLinear } from "d3-scale";
  import Tooltip from "../../components/Tooltip.svelte";

  interface Props {
    dots: Dot[];
    color: string;
    xLabel: string;
    yLabel: string;
    xFormat: (v: number) => string;
    yFormat: (v: number) => string;
    xMax?: number;
    yMax?: number;
    height?: number;
    onpick?: (key: string) => void;
    ariaLabel: string;
    labelKeys?: string[];
  }
  let { dots, color, xLabel, yLabel, xFormat, yFormat, xMax, yMax, height = 340, onpick, ariaLabel, labelKeys = [] }: Props = $props();

  let width = $state(0);
  let W = $derived(Math.max(width, 260));
  const m = { top: 30, right: 12, bottom: 40, left: 48 };
  let x = $derived(scaleLinear().domain([0, xMax ?? Math.max(...dots.map((d) => d.x))]).nice().range([m.left, W - m.right]));
  let y = $derived(scaleLinear().domain([0, yMax ?? Math.max(...dots.map((d) => d.y))]).nice().range([height - m.bottom, m.top]));
  let sorted = $derived([...dots].sort((a, b) => Number(a.emphasis) - Number(b.emphasis)));
  let hover = $state<Dot | null>(null);
  let svgEl = $state<SVGSVGElement>();

  function move(e: PointerEvent) {
    const b = svgEl!.getBoundingClientRect();
    const px = ((e.clientX - b.left) / b.width) * W;
    const py = ((e.clientY - b.top) / b.height) * height;
    let best: Dot | null = null;
    let bd = 24 * 24;
    for (const d of dots) {
      const dd = (x(Math.min(d.x, x.domain()[1])) - px) ** 2 + (y(Math.min(d.y, y.domain()[1])) - py) ** 2;
      if (dd < bd) {
        bd = dd;
        best = d;
      }
    }
    hover = best;
  }
</script>

<div class="scatter" bind:clientWidth={width}>
  {#if width}
    <svg bind:this={svgEl} viewBox={`0 0 ${W} ${height}`} width={W} {height} role="img" aria-label={ariaLabel}>
      {#each y.ticks(5) as t}
        <line x1={m.left} x2={W - m.right} y1={y(t)} y2={y(t)} stroke="var(--hair)" />
        <text class="axis-label" x={m.left - 6} y={y(t) + 4} text-anchor="end">{yFormat(t)}</text>
      {/each}
      {#each x.ticks(5) as t}
        <text class="axis-label" x={x(t)} y={height - m.bottom + 16} text-anchor="middle">{xFormat(t)}</text>
      {/each}
      <line x1={m.left} x2={W - m.right} y1={height - m.bottom + 0.5} y2={height - m.bottom + 0.5} stroke="var(--muted)" />
      <text class="axis-label" x={(m.left + W - m.right) / 2} y={height - 4} text-anchor="middle">{xLabel}</text>
      <text class="axis-label" x={m.left - 44} y={12}>{yLabel}</text>
      {#each sorted as d (d.key)}
        <circle
          cx={x(Math.min(d.x, x.domain()[1]))}
          cy={y(Math.min(d.y, y.domain()[1]))}
          r={d.emphasis ? 5 : 4}
          fill={d.emphasis ? color : "var(--faint)"}
          stroke="var(--plane)"
          stroke-width="1.5"
          opacity={d.emphasis ? 0.9 : 0.7}
        />
      {/each}
      {#each dots.filter((d) => labelKeys.includes(d.key)) as d}
        <text class="mark-label" x={x(Math.min(d.x, x.domain()[1])) + 7} y={y(Math.min(d.y, y.domain()[1])) + 4}>{d.label}</text>
      {/each}
      {#if hover}
        <circle cx={x(Math.min(hover.x, x.domain()[1]))} cy={y(Math.min(hover.y, y.domain()[1]))} r="7" fill="none" stroke="var(--ink)" stroke-width="1.5" />
      {/if}
      <rect
        x={m.left}
        y={m.top}
        width={W - m.left - m.right}
        height={height - m.top - m.bottom}
        fill="transparent"
        role="presentation"
        onpointermove={move}
        onpointerleave={() => (hover = null)}
        onclick={() => hover && onpick?.(hover.key)}
        style:cursor={onpick ? "pointer" : "default"}
      />
    </svg>
    {#if hover}
      <Tooltip
        x={x(Math.min(hover.x, x.domain()[1]))}
        y={Math.max(0, y(Math.min(hover.y, y.domain()[1])) - 90)}
        width={W}
        visible={true}
        title={`${hover.label}${hover.note ? `, ${hover.note}` : ""}`}
        rows={[
          { label: xLabel, value: xFormat(hover.x) },
          { label: yLabel, value: yFormat(hover.y) },
        ]}
      />
    {/if}
  {/if}
</div>

<style>
  .scatter {
    position: relative;
    width: 100%;
  }
  svg {
    display: block;
    overflow: visible;
  }
</style>
