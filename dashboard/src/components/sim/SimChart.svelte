<script lang="ts" module>
  export interface Fan {
    lo90: number[];
    lo50: number[];
    hi50: number[];
    hi90: number[];
  }
  export interface CompareLine {
    id: string;
    label: string;
    /** A shorter name for the label at the line's end, when `label` is long. */
    short?: string;
    values: number[];
  }
</script>

<script lang="ts">
  /**
   * A simulated time series in simulation time (no calendar: these are scenarios, not dates).
   * Median line with 50% and 90% fans, an optional capacity rule, shading where the median is
   * above an intensity threshold, pinned comparison scenarios in grey, and a restrictions strip.
   */
  import { scaleLinear } from "d3-scale";
  import { area, line } from "d3-shape";
  import Tooltip from "../Tooltip.svelte";

  interface Props {
    central: number[];
    fan?: Fan | null;
    fanLevel?: "none" | "50" | "90";
    stepDays: 1 | 7;
    window: [number, number];
    color: string;
    format: (v: number) => string;
    label: string;
    capacity?: number | null;
    capacityLabel?: string;
    threshold?: number | null;
    policy?: number[] | null;
    compare?: CompareLine[];
    height?: number;
    ariaLabel: string;
    pending?: boolean;
  }
  let {
    central,
    fan = null,
    fanLevel = "90",
    stepDays,
    window,
    color,
    format,
    label,
    capacity = null,
    capacityLabel = "Capacity",
    threshold = null,
    policy = null,
    compare = [],
    height = 300,
    ariaLabel,
    pending = false,
  }: Props = $props();

  let width = $state(0);
  let W = $derived(Math.max(width, 160));
  const top = 14;
  let strip = $derived(policy ? 16 : 0);
  const bottom = 26;
  // Room on the right for the end labels: as wide as the longest one (12.5px text, ~6.6px a character).
  let endTexts = $derived([
    ...compare.map((c) => c.short ?? c.label),
    ...(compare.length ? ["This scenario"] : []),
    ...(capacity ? [W < 520 ? capacityLabel.split(" ")[0] : capacityLabel] : []),
  ]);
  let right = $derived(endTexts.length ? Math.min(W * 0.28, 12 + 6.8 * Math.max(...endTexts.map((t) => t.length))) : 6);
  let plotBottom = $derived(height - bottom - strip);

  // Indices of the visible window, in steps.
  let i0 = $derived(Math.max(0, Math.floor(window[0] / stepDays)));
  let i1 = $derived(Math.min(central.length - 1, Math.ceil(window[1] / stepDays)));
  let idx = $derived(Array.from({ length: Math.max(i1 - i0 + 1, 1) }, (_, k) => i0 + k));
  let x = $derived(scaleLinear().domain([i0 * stepDays, i1 * stepDays]).range([0, W - right]));
  let visibleMax = $derived(
    Math.max(
      1e-9,
      ...idx.map((i) => central[i]),
      ...(fan && fanLevel !== "none" ? idx.map((i) => (fanLevel === "90" ? fan!.hi90[i] : fan!.hi50[i])) : []),
      ...compare.flatMap((c) => idx.map((i) => c.values[i] ?? 0)),
      capacity && capacity < 4 * Math.max(...idx.map((i) => central[i])) ? capacity : 0,
    ),
  );
  let y = $derived(scaleLinear().domain([0, visibleMax]).nice(4).range([plotBottom, top]));
  let yTicks = $derived(y.ticks(4).filter((t) => t > 0));
  let px = $derived((i: number) => x(i * stepDays));

  let path = $derived((values: number[]) =>
    line<number>()
      .x((i) => px(i))
      .y((i) => y(values[i] ?? 0))(idx) ?? "",
  );
  let band = $derived((lo: number[], hi: number[]) =>
    area<number>()
      .x((i) => px(i))
      .y0((i) => y(lo[i]))
      .y1((i) => y(hi[i]))(idx) ?? "",
  );

  // Time axis: months up to 6 months shown, otherwise every 3 or 6 months.
  let ticks = $derived.by(() => {
    const span = (i1 - i0) * stepDays;
    const every = span <= 200 ? 30.4 : span <= 450 ? 91.25 : 182.5;
    const out: { day: number; label: string }[] = [];
    for (let d = Math.ceil((i0 * stepDays) / every) * every; d <= i1 * stepDays; d += every) {
      const months = Math.round(d / 30.4167);
      out.push({ day: d, label: months === 0 ? "start" : months % 12 === 0 ? `${months / 12} yr` : `${months} mo` });
    }
    return out;
  });

  // Runs of steps where the median is above the intensity threshold.
  let above = $derived.by(() => {
    if (threshold === null || threshold === undefined) return [];
    const runs: [number, number][] = [];
    let start: number | null = null;
    for (const i of idx) {
      if (central[i] > threshold && start === null) start = i;
      if ((central[i] <= threshold || i === idx[idx.length - 1]) && start !== null) {
        runs.push([start, i]);
        start = null;
      }
    }
    return runs;
  });

  let hover = $state<number | null>(null);
  let svgEl = $state<SVGSVGElement>();
  function move(e: PointerEvent) {
    const b = svgEl!.getBoundingClientRect();
    const day = x.invert(((e.clientX - b.left) / b.width) * W);
    hover = Math.max(i0, Math.min(i1, Math.round(day / stepDays)));
  }
  function key(e: KeyboardEvent) {
    const i = hover ?? i1;
    if (e.key === "ArrowLeft") hover = Math.max(i0, i - 1);
    else if (e.key === "ArrowRight") hover = Math.min(i1, i + 1);
    else return;
    e.preventDefault();
  }
  const when = (i: number) => (stepDays === 7 ? `Week ${i + 1}` : `Day ${i + 1}`) + ` (${(((i + 0.5) * stepDays) / 30.4167).toFixed(1)} months in)`;
  let tipRows = $derived(
    hover === null
      ? []
      : [
          { color, label, value: format(central[hover]) },
          ...(fan && fanLevel !== "none"
            ? [{ label: fanLevel === "90" ? "90% range" : "50% range", value: `${format(fanLevel === "90" ? fan.lo90[hover] : fan.lo50[hover])}–${format(fanLevel === "90" ? fan.hi90[hover] : fan.hi50[hover])}` }]
            : []),
          ...compare.map((c) => ({ color: "var(--muted)", dashed: true, label: c.label, value: format(c.values[hover!] ?? 0) })),
          ...(policy ? [{ label: "Restrictions (stringency)", value: `${Math.round(policy[hover])}` }] : []),
        ],
  );
  let labels = $derived.by(() => {
    const out: { y: number; text: string; muted: boolean }[] = [];
    for (const c of compare) out.push({ y: y(c.values[i1] ?? 0), text: c.short ?? c.label, muted: true });
    if (compare.length) out.push({ y: y(central[i1]), text: "This scenario", muted: false });
    if (capacity && capacity <= y.domain()[1]) out.push({ y: y(capacity), text: W < 520 ? capacityLabel.split(" ")[0] : capacityLabel, muted: true });
    out.sort((a, b) => a.y - b.y);
    for (let k = 1; k < out.length; k++) if (out[k].y - out[k - 1].y < 16) out[k].y = out[k - 1].y + 16;
    return out;
  });
</script>

<div class="chart" class:pending bind:clientWidth={width}>
  {#if width}
    <svg bind:this={svgEl} viewBox={`0 0 ${W} ${height}`} width={W} {height} role="img" aria-label={ariaLabel}>
      {#each above as [a, b]}
        <rect x={px(a)} y={top} width={Math.max(px(b) - px(a), 1)} height={plotBottom - top} fill={color} opacity="0.07" />
      {/each}
      {#each yTicks as t}
        <line x1="0" x2={W - right} y1={y(t)} y2={y(t)} stroke="var(--hair)" />
        <text class="axis-label" x="0" y={y(t) - 4}>{format(t)}</text>
      {/each}
      {#if fan && fanLevel === "90"}<path d={band(fan.lo90, fan.hi90)} fill={color} opacity="0.12" />{/if}
      {#if fan && fanLevel !== "none"}<path d={band(fan.lo50, fan.hi50)} fill={color} opacity="0.22" />{/if}
      {#each compare as c (c.id)}
        <path d={path(c.values)} fill="none" stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="5 3" />
      {/each}
      <path d={path(central)} fill="none" stroke={color} stroke-width="2.25" stroke-linejoin="round" stroke-linecap="round" />
      {#if capacity && capacity <= y.domain()[1]}
        <line x1="0" x2={W - right} y1={y(capacity)} y2={y(capacity)} stroke="var(--ink-2)" stroke-width="1.25" stroke-dasharray="6 4" />
      {/if}
      {#if threshold !== null && threshold !== undefined && threshold <= y.domain()[1]}
        <line x1="0" x2={W - right} y1={y(threshold)} y2={y(threshold)} stroke={color} stroke-width="1" opacity="0.6" />
      {/if}
      <line x1="0" x2={W - right} y1={plotBottom + 0.5} y2={plotBottom + 0.5} stroke="var(--muted)" />
      {#if policy}
        {#each idx as i}
          {#if policy[i] > 0}
            <rect x={px(i)} y={plotBottom + 4} width={Math.max((W - right) / idx.length, 1) + 0.4} height="8" fill="var(--ink)" opacity={0.08 + (policy[i] / 100) * 0.62} />
          {/if}
        {/each}
      {/if}
      {#each ticks as t}
        <line x1={x(t.day)} x2={x(t.day)} y1={height - bottom} y2={height - bottom + 4} stroke="var(--muted)" />
        <text class="axis-label" x={x(t.day) + 3} y={height - 8}>{t.label}</text>
      {/each}
      {#each labels as l}
        <text class="mark-label" x={W - right + 6} y={l.y + 4} style:fill={l.muted ? "var(--ink-2)" : "var(--ink)"}>{l.text}</text>
      {/each}
      {#if hover !== null}
        <line x1={px(hover)} x2={px(hover)} y1={top} y2={plotBottom} stroke="var(--ink)" opacity="0.4" />
        <circle cx={px(hover)} cy={y(central[hover])} r="3.5" fill={color} stroke="var(--plane)" stroke-width="1.5" />
      {/if}
      <rect
        class="hit"
        x="0"
        y={top}
        width={W - right}
        height={plotBottom - top + strip}
        fill="transparent"
        tabindex="0"
        role="slider"
        aria-label={`${ariaLabel}. Arrow keys read each ${stepDays === 7 ? "week" : "day"}.`}
        aria-valuemin={i0}
        aria-valuemax={i1}
        aria-valuenow={hover ?? i1}
        aria-valuetext={hover !== null ? `${when(hover)}: ${tipRows.map((r) => `${r.label} ${r.value}`).join(", ")}` : undefined}
        onpointermove={move}
        onpointerleave={() => (hover = null)}
        onkeydown={key}
        onfocus={() => (hover = hover ?? i1)}
        onblur={() => (hover = null)}
      />
    </svg>
    {#if hover !== null}
      <Tooltip x={px(hover)} y={top} width={W} visible={true} title={when(hover)} rows={tipRows} />
    {/if}
  {/if}
</div>

<style>
  .chart {
    position: relative;
    width: 100%;
    transition: opacity 0.15s;
  }
  .pending {
    opacity: 0.75;
  }
  svg {
    display: block;
    overflow: visible;
  }
  .hit {
    cursor: crosshair;
    outline: none;
  }
  .hit:focus-visible {
    stroke: var(--focus);
    stroke-width: 2;
  }
</style>
