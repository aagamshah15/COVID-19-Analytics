<script lang="ts" module>
  export interface LineSeries {
    id: string;
    label: string;
    values: (number | null)[];
    color: string;
    /** primary = the subject; context = comparison (grey); faint = background */
    role?: "primary" | "context" | "faint";
    dashed?: boolean;
    /** Used for direct labels on narrow screens. */
    short?: string;
  }
  export interface Band {
    lo: (number | null)[];
    hi: (number | null)[];
    color: string;
    label: string;
  }
</script>

<script lang="ts">
  /**
   * Line chart over a shared weekly x axis with a crosshair readout of every series.
   * Gaps (null values) break the line; for the primary series they are hatched as "not reported".
   */
  import { scaleLinear } from "d3-scale";
  import { line } from "d3-shape";
  import Tooltip from "../../components/Tooltip.svelte";
  import { day } from "../format";

  interface Props {
    x: string[];
    series: LineSeries[];
    band?: Band;
    height?: number;
    format: (v: number) => string;
    yMax?: number;
    highlight?: [number, number] | null;
    marker?: { index: number; label: string } | null;
    hatchGaps?: boolean;
    ariaLabel: string;
    compact?: boolean;
    directLabels?: boolean;
  }
  let {
    x,
    series,
    band,
    height = 260,
    format,
    yMax,
    highlight = null,
    marker = null,
    hatchGaps = true,
    ariaLabel,
    compact = false,
    directLabels = false,
  }: Props = $props();

  let width = $state(0);
  let W = $derived(Math.max(width, 120));
  let top = $derived(compact ? 18 : 16);
  const bottom = 24;
  let narrowW = $derived(W < 520);
  let right = $derived(directLabels ? (narrowW ? 64 : 110) : 4);
  let n = $derived(x.length);
  let xs = $derived((i: number) => (n <= 1 ? 0 : (i / (n - 1)) * (W - right)));
  let dataMax = $derived(
    Math.max(1e-9, ...series.flatMap((s) => s.values.map((v) => v ?? 0)), ...(band ? band.hi.map((v) => v ?? 0) : [])),
  );
  let scale = $derived(scaleLinear().domain([0, yMax ?? dataMax]).nice(compact ? 2 : 4).range([height - bottom, top]));
  let ticks = $derived(scale.ticks(compact ? 2 : 4).filter((t) => t > 0));
  let pathFor = $derived((values: (number | null)[]) =>
    line<number | null>()
      .defined((v) => v !== null)
      .x((_, i) => xs(i))
      .y((v) => scale(v ?? 0))(values) ?? "",
  );
  let bandPath = $derived.by(() => {
    if (!band) return "";
    const pts: string[] = [];
    const lower: string[] = [];
    band.hi.forEach((v, i) => {
      if (v !== null && band.lo[i] !== null) {
        pts.push(`${xs(i)},${scale(v)}`);
        lower.unshift(`${xs(i)},${scale(band.lo[i] ?? 0)}`);
      }
    });
    return pts.length ? `M${pts.join("L")}L${lower.join("L")}Z` : "";
  });
  let years = $derived(
    x
      .map((d, i) => ({ d, i }))
      .filter(({ d, i }) => i > 0 && d.slice(0, 4) !== x[i - 1].slice(0, 4))
      .map(({ d, i }) => ({ i, label: d.slice(0, 4) })),
  );
  let monthTicks = $derived(
    n <= 60
      ? x
          .map((d, i) => ({ d, i }))
          .filter(({ d, i }) => i > 0 && d.slice(5, 7) !== x[i - 1].slice(5, 7) && Number(d.slice(5, 7)) % 2 === 1)
          .map(({ d, i }) => ({ i, label: new Date(`${d}T00:00:00Z`).toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" }) }))
      : [],
  );
  let primary = $derived(series.find((s) => (s.role ?? "primary") === "primary"));
  let gaps = $derived(
    hatchGaps && primary
      ? primary.values
          .map((v, i) => ({ v, i }))
          .filter(({ v, i }) => v === null && primary!.values.slice(0, i).some((p) => p !== null))
          .map(({ i }) => i)
      : [],
  );
  const pid = `h${Math.random().toString(36).slice(2, 8)}`;

  let hover = $state<number | null>(null);
  let svgEl = $state<SVGSVGElement>();
  function move(e: PointerEvent) {
    const b = svgEl!.getBoundingClientRect();
    const px = ((e.clientX - b.left) / b.width) * W;
    hover = Math.max(0, Math.min(n - 1, Math.round((px / (W - right)) * (n - 1))));
  }
  function key(e: KeyboardEvent) {
    const i = hover ?? n - 1;
    if (e.key === "ArrowLeft") hover = Math.max(0, i - 1);
    else if (e.key === "ArrowRight") hover = Math.min(n - 1, i + 1);
    else return;
    e.preventDefault();
  }
  let tipRows = $derived(
    hover === null
      ? []
      : [
          ...series.map((s) => ({
            color: s.color,
            dashed: s.dashed,
            label: s.label,
            value: s.values[hover!] === null ? "not reported" : format(s.values[hover!] as number),
          })),
          ...(band && band.lo[hover] !== null ? [{ color: band.color, label: band.label, value: `${format(band.lo[hover] ?? 0)}–${format(band.hi[hover] ?? 0)}` }] : []),
        ].filter((r) => !(r.value === "not reported" && series.find((s) => s.label === r.label)?.role === "faint")),
  );
  let labels = $derived.by(() => {
    if (!directLabels) return [];
    const placed: { y: number; text: string; color: string }[] = [];
    for (const s of series) {
      let last = n - 1;
      while (last > 0 && s.values[last] === null) last--;
      const v = s.values[last];
      if (v === null) continue;
      placed.push({ y: scale(v), text: narrowW && s.short ? s.short : s.label, color: s.role === "faint" ? "var(--muted)" : "var(--ink)" });
    }
    placed.sort((a, b) => a.y - b.y);
    for (let i = 1; i < placed.length; i++) if (placed[i].y - placed[i - 1].y < 14) placed[i].y = placed[i - 1].y + 14;
    return placed;
  });
</script>

<div class="line" bind:clientWidth={width}>
  {#if width}
    <svg bind:this={svgEl} viewBox={`0 0 ${W} ${height}`} width={W} {height} role="img" aria-label={ariaLabel}>
      <defs>
        <pattern id={pid} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="6" stroke="var(--faint)" stroke-width="1.6" />
        </pattern>
      </defs>
      {#each ticks as t}
        <line x1="0" x2={W - right} y1={scale(t)} y2={scale(t)} stroke="var(--hair)" />
        <text class="axis-label" x="0" y={scale(t) - 4}>{format(t)}</text>
      {/each}
      {#if highlight}
        <rect x="0" y={top} width={Math.max(xs(highlight[0]), 0)} height={height - bottom - top} fill="var(--plane)" opacity="0.6" />
        <rect x={xs(highlight[1])} y={top} width={Math.max(W - right - xs(highlight[1]), 0)} height={height - bottom - top} fill="var(--plane)" opacity="0.6" />
      {/if}
      {#each gaps as i}
        <rect x={xs(i) - (W - right) / (n - 1) / 2} y={top} width={(W - right) / Math.max(n - 1, 1) + 0.5} height={height - bottom - top} fill={`url(#${pid})`} />
      {/each}
      {#if band && bandPath}<path d={bandPath} fill={band.color} opacity="0.18" />{/if}
      {#each [...series].reverse() as s (s.id)}
        <path
          d={pathFor(s.values)}
          fill="none"
          stroke={s.color}
          stroke-width={s.role === "faint" ? 1.25 : s.role === "context" ? 1.5 : 2.25}
          stroke-dasharray={s.dashed ? "4 3" : undefined}
          stroke-linejoin="round"
          stroke-linecap="round"
        />
      {/each}
      {#if marker}
        <line x1={xs(marker.index)} x2={xs(marker.index)} y1={top} y2={height - bottom} stroke="var(--ink-2)" stroke-dasharray="2 3" />
        <text class="axis-label" x={xs(marker.index) + 4} y={top + 10}>{marker.label}</text>
      {/if}
      <line x1="0" x2={W - right} y1={height - bottom + 0.5} y2={height - bottom + 0.5} stroke="var(--muted)" />
      {#each years as y}
        <line x1={xs(y.i)} x2={xs(y.i)} y1={height - bottom} y2={height - bottom + 5} stroke="var(--muted)" />
        <text class="axis-label" x={xs(y.i) + 3} y={height - 6}>{y.label}</text>
      {/each}
      {#each monthTicks as m}
        {#if !years.some((y) => y.i === m.i)}<text class="axis-label" x={xs(m.i) + 3} y={height - 6}>{m.label}</text>{/if}
      {/each}
      {#each labels as l}
        <text class="mark-label" x={W - right + 6} y={l.y + 4} style:fill={l.color}>{l.text}</text>
      {/each}
      {#if hover !== null}
        <line x1={xs(hover)} x2={xs(hover)} y1={top} y2={height - bottom} stroke="var(--ink)" opacity="0.4" />
        {#each series as s}
          {#if s.values[hover] !== null && s.role !== "faint"}
            <circle cx={xs(hover)} cy={scale(s.values[hover] ?? 0)} r="3.5" fill={s.color} stroke="var(--plane)" stroke-width="1.5" />
          {/if}
        {/each}
      {/if}
      <rect
        class="hit"
        x="0"
        y={top}
        width={W - right}
        height={height - bottom - top}
        fill="transparent"
        tabindex="0"
        role="slider"
        aria-label={`${ariaLabel}. Arrow keys read each week.`}
        aria-valuemin="0"
        aria-valuemax={n - 1}
        aria-valuenow={hover ?? n - 1}
        aria-valuetext={hover !== null ? `${day(x[hover])}: ${tipRows.map((r) => `${r.label} ${r.value}`).join(", ")}` : undefined}
        onpointermove={move}
        onpointerleave={() => (hover = null)}
        onkeydown={key}
        onfocus={() => (hover = hover ?? n - 1)}
        onblur={() => (hover = null)}
      />
    </svg>
    {#if hover !== null}
      <Tooltip x={xs(hover)} y={top} width={W} visible={true} title={`Week ending ${day(x[hover])}`} rows={tipRows} />
    {/if}
  {/if}
</div>

<style>
  .line {
    position: relative;
    width: 100%;
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
