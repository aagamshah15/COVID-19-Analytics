<script lang="ts" module>
  export interface Bar {
    key: string;
    value: number | null;
    tick?: string;
    title: string;
    dim?: boolean;
    label?: boolean;
  }
</script>

<script lang="ts">
  /** Vertical bars on one axis. Negative values hang below a zero line. */
  import Tooltip from "../../components/Tooltip.svelte";

  interface Props {
    bars: Bar[];
    color: string;
    height?: number;
    max?: number;
    min?: number;
    format: (v: number) => string;
    ticks?: number[];
    ariaLabel: string;
    negativeColor?: string;
  }
  let { bars, color, height = 220, max, min, format, ticks, ariaLabel, negativeColor }: Props = $props();

  let width = $state(0);
  let W = $derived(Math.max(width, 120));
  const top = 20;
  const bottom = 24;
  let left = $derived(ticks ? 38 : 0);
  let vmax = $derived(max ?? Math.max(...bars.map((b) => b.value ?? 0), 0) * 1.08);
  let vmin = $derived(min ?? Math.min(...bars.map((b) => b.value ?? 0), 0) * 1.08);
  let y = $derived((v: number) => top + (height - top - bottom) * (1 - (v - vmin) / (vmax - vmin || 1)));
  let step = $derived((W - left) / Math.max(bars.length, 1));
  let gap = $derived(step > 14 ? 3 : 1.5);
  let hover = $state<number | null>(null);
</script>

<div class="bars" bind:clientWidth={width}>
  {#if width}
    <svg viewBox={`0 0 ${W} ${height}`} width={W} {height} role="img" aria-label={ariaLabel}>
      {#each ticks ?? [] as t}
        {#if t !== 0}<line x1={left} x2={W} y1={y(t)} y2={y(t)} stroke="var(--hair)" />{/if}
        <text class="axis-label" x={left - 6} y={y(t) + 4} text-anchor="end">{format(t)}</text>
      {/each}
      {#each bars as b, i}
        {#if b.value !== null}
          {@const neg = b.value < 0}
          <rect
            x={left + i * step + gap / 2}
            y={neg ? y(0) : y(b.value)}
            width={Math.max(step - gap, 1)}
            height={Math.max(Math.abs(y(b.value) - y(0)), 0.8)}
            rx={step > 10 ? 2 : 0.5}
            fill={neg && negativeColor ? negativeColor : color}
            opacity={b.dim ? 0.3 : hover === i ? 0.85 : 1}
          />
          {#if b.label}
            <text class="mark-label" x={left + i * step + step / 2} y={neg ? y(b.value) + 14 : y(b.value) - 5} text-anchor="middle">{format(b.value)}</text>
          {/if}
        {/if}
        {#if b.tick}<text class="axis-label" x={left + i * step + (step < 30 ? 1 : step / 2)} y={height - 6} text-anchor={step < 30 ? "start" : "middle"}>{b.tick}</text>{/if}
        <rect
          x={left + i * step}
          y={top}
          width={step}
          height={height - top - bottom}
          fill="transparent"
          role="presentation"
          onpointerenter={() => (hover = i)}
          onpointerleave={() => (hover = null)}
        />
      {/each}
      <line x1={left} x2={W} y1={y(0) + 0.5} y2={y(0) + 0.5} stroke="var(--muted)" />
    </svg>
    {#if hover !== null && bars[hover].value !== null}
      <Tooltip
        x={left + (hover + 0.5) * step}
        y={Math.max(0, y(Math.max(bars[hover].value ?? 0, 0)) - 64)}
        width={W}
        visible={true}
        title={bars[hover].title}
        rows={[{ color, label: "value", value: format(bars[hover].value ?? 0) }]}
      />
    {/if}
  {/if}
</div>

<style>
  .bars {
    position: relative;
    width: 100%;
  }
  svg {
    display: block;
    overflow: visible;
  }
</style>
