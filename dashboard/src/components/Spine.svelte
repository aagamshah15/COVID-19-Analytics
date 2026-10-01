<script lang="ts">
  /**
   * The timeline spine: weekly deaths for the current region as thin bars, a vaccination-coverage
   * ribbon and the dominant-variant eras. Drag across it to choose the period every view uses.
   */
  import { scaleLinear } from "d3-scale";
  import type { AggregateWeek } from "../lib/data/aggregate";
  import { count, day, perMillion, pct } from "../lib/format";
  import type { Measure } from "../lib/state/app.svelte";
  import Tooltip from "./Tooltip.svelte";

  interface Props {
    weeks: string[];
    agg: AggregateWeek[];
    measure: Measure;
    range: [number, number];
    onselect: (from: string, to: string) => void;
    compact?: boolean;
    label: string;
  }
  let { weeks, agg, measure, range, onselect, compact = false, label }: Props = $props();

  // Approximate periods of global dominance (WHO variant tracking).
  const ERAS: [string, string, string][] = [
    ["Ancestral", "2020-01-01", "2020-12-31"],
    ["Alpha", "2021-01-01", "2021-06-06"],
    ["Delta", "2021-06-07", "2021-12-26"],
    ["Omicron", "2021-12-27", "2099-01-01"],
  ];

  let width = $state(0);
  let W = $derived(Math.max(width, 300));
  let narrow = $derived(W < 640);
  let top = $derived(compact ? 6 : narrow ? 46 : 32);
  let barH = $derived(compact ? 54 : narrow ? 170 : 200);
  let axisY = $derived(top + barH);
  let ribbonY = $derived(axisY + (compact ? 18 : 32));
  let ribbonH = $derived(compact ? 6 : 10);
  let eraY = $derived(ribbonY + ribbonH + (compact ? 6 : 28));
  let H = $derived(eraY + (compact ? 18 : 30));

  let n = $derived(weeks.length);
  let step = $derived(W / n);
  let values = $derived(agg.map((w) => (measure === "abs" ? w.deaths : w.dpm)));
  let scale = $derived(scaleLinear().domain([0, Math.max(...values.map((v) => v ?? 0), 1e-9)]).nice(4));
  let max = $derived(scale.domain()[1]);
  const y = (v: number) => axisY - (v / max) * barH;
  let ticks = $derived(scale.ticks(4).filter((t) => t > 0));
  const fmtTick = (v: number) => (measure === "abs" ? (v >= 1000 ? `${Math.round(v / 1000)}k` : `${Math.round(v)}`) : v >= 10 ? `${Math.round(v)}` : v.toFixed(1));

  let years = $derived(
    [2020, 2021, 2022, 2023].map((yr) => ({ yr, i: weeks.findIndex((w) => w >= `${yr}-01-01`) })).filter((d) => d.i >= 0),
  );
  let eras = $derived(
    ERAS.map(([name, a, b]) => {
      const i0 = Math.max(weeks.findIndex((w) => w >= a), 0);
      let i1 = weeks.findIndex((w) => w > b);
      if (i1 < 0) i1 = n;
      return { name, x0: i0 * step, x1: i1 * step };
    }),
  );
  let peak = $derived(values.reduce<number>((best, v, i) => ((v ?? -1) > (values[best] ?? -1) ? i : best), 0));
  let spike2023 = $derived.by(() => {
    const s = weeks.findIndex((w) => w >= "2023-01-01");
    let best = s;
    for (let i = s; i < n; i++) if ((values[i] ?? 0) > (values[best] ?? 0)) best = i;
    // Only call out the China backlog when it stands out in the current region.
    return (values[best] ?? 0) > 2.2 * ((values[best - 2] ?? 0) + (values[best + 2] ?? 0)) / 2 ? best : -1;
  });

  // Interaction: hover readout, drag to select a period.
  let hover = $state<number | null>(null);
  let drag = $state<{ a: number; b: number } | null>(null);
  let svgEl = $state<SVGSVGElement>();
  const indexAt = (clientX: number) => {
    const b = svgEl!.getBoundingClientRect();
    return Math.max(0, Math.min(n - 1, Math.floor(((clientX - b.left) / b.width) * n)));
  };
  let sel = $derived(drag ? ([Math.min(drag.a, drag.b), Math.max(drag.a, drag.b)] as [number, number]) : range);
  const inSel = (i: number) => i >= sel[0] && i <= sel[1];

  function down(e: PointerEvent) {
    const i = indexAt(e.clientX);
    drag = { a: i, b: i };
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
  }
  function move(e: PointerEvent) {
    const i = indexAt(e.clientX);
    hover = i;
    if (drag) drag = { ...drag, b: i };
  }
  function up() {
    if (drag && Math.abs(drag.a - drag.b) >= 1) {
      const [a, b] = [Math.min(drag.a, drag.b), Math.max(drag.a, drag.b)];
      onselect(weeks[a], weeks[b]);
    }
    drag = null;
  }
  function key(e: KeyboardEvent) {
    const i = hover ?? peak;
    if (e.key === "ArrowLeft") hover = Math.max(0, i - 1);
    else if (e.key === "ArrowRight") hover = Math.min(n - 1, i + 1);
    else return;
    e.preventDefault();
  }

  let tip = $derived.by(() => {
    if (hover === null) return null;
    const w = agg[hover];
    return {
      x: (hover + 0.5) * step,
      title: `Week ending ${day(weeks[hover])}`,
      rows: [
        { color: "var(--deaths)", label: "deaths", value: w.deaths === null ? "not reported" : count(w.deaths) },
        { color: "var(--deaths)", label: "per million", value: perMillion(w.dpm) },
        { color: "var(--vax)", label: "fully vaccinated", value: pct(w.vax) },
      ],
    };
  });
</script>

<div class="spine" class:compact bind:clientWidth={width}>
  {#if width}
    <svg bind:this={svgEl} viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={label}>
      {#if !compact}
        {#each ticks as t}
          <line x1="0" x2={W} y1={y(t)} y2={y(t)} stroke="var(--hair)" />
          <text class="axis-label" x="0" y={y(t) - 5}>{fmtTick(t)}</text>
        {/each}
      {/if}
      {#each values as v, i}
        {#if v !== null}
          <rect
            x={i * step + (step > 4 ? 1 : 0.25)}
            y={y(v)}
            width={Math.max(step - (step > 4 ? 2 : 0.5), 0.5)}
            height={Math.max(axisY - y(v), 0.6)}
            rx={step > 4 ? 1.5 : 0}
            fill={inSel(i) ? "var(--deaths)" : "color-mix(in oklab, var(--deaths) 24%, var(--plane))"}
          />
        {/if}
        <rect
          x={i * step}
          y={ribbonY}
          width={step + 0.5}
          height={ribbonH}
          style:fill={`color-mix(in oklab, var(--vax) ${Math.round((agg[i].vax ?? 0) * 100)}%, var(--seq-0))`}
        />
      {/each}
      <line x1="0" x2={W} y1={axisY + 0.5} y2={axisY + 0.5} stroke="var(--muted)" />
      {#each years as { yr, i }}
        <line x1={i * step + 0.5} x2={i * step + 0.5} y1={axisY} y2={axisY + 5} stroke="var(--muted)" />
        <text class="axis-label" x={i * step + 4} y={axisY + (compact ? 14 : 18)}>{yr}</text>
      {/each}
      {#if !compact}
        <text class="axis-label" x="0" y={ribbonY + ribbonH + 16}>{narrow ? "Fully vaccinated share" : "Share fully vaccinated (deeper teal = higher)"}</text>
        <text class="mark-label" x={W} y={ribbonY + ribbonH + 16} text-anchor="end">{pct(agg[n - 1].vax)}{narrow ? "" : " by Dec 2023"}</text>
      {/if}
      {#each eras as e}
        <g class="era">
          <line x1={e.x0 + 1} x2={e.x1 - 3} y1={eraY + 4} y2={eraY + 4} />
          <line x1={e.x0 + 1} x2={e.x0 + 1} y1={eraY} y2={eraY + 8} />
          {#if !compact || W > 520}<text x={e.x0 + 4} y={eraY + (compact ? 17 : 22)}>{e.name}</text>{/if}
        </g>
      {/each}
      {#if !compact && values[peak] !== null}
        {@const cx = (peak + 0.5) * step}
        {@const ty = top - 14 - (narrow ? 16 : 0)}
        <line x1={cx} x2={cx} y1={y(values[peak] ?? 0) - 3} y2={ty + 3} stroke="var(--ink-2)" />
        <text class="mark-label" x={cx + 5} y={ty}>
          {narrow ? `Peak, ${day(weeks[peak])}` : `Deadliest week, ${day(weeks[peak])}: ${measure === "abs" ? count(values[peak]) : `${perMillion(values[peak])} per million`}`}
        </text>
      {/if}
      {#if !compact && spike2023 > 0}
        {@const cx = (spike2023 + 0.5) * step}
        <line x1={cx} x2={cx} y1={y(values[spike2023] ?? 0) - 3} y2={top - 11} stroke="var(--ink-2)" />
        <text class="mark-label" x={cx - 5} y={top - 14} text-anchor="end">{narrow ? "China backlog" : "China releases backlog of deaths"}</text>
      {/if}
      {#if drag}
        <rect x={sel[0] * step} y={top} width={(sel[1] - sel[0] + 1) * step} height={barH} fill="var(--ink)" opacity="0.07" />
      {/if}
      {#if hover !== null && !drag}
        <line x1={(hover + 0.5) * step} x2={(hover + 0.5) * step} y1={top} y2={axisY} stroke="var(--ink)" opacity="0.45" />
      {/if}
      <rect
        class="hit"
        x="0"
        y={top}
        width={W}
        height={ribbonY + ribbonH - top}
        fill="transparent"
        tabindex="0"
        role="slider"
        aria-label="Weekly deaths. Arrow keys read each week; drag to choose a period."
        aria-valuemin="0"
        aria-valuemax={n - 1}
        aria-valuenow={hover ?? peak}
        aria-valuetext={tip ? `${tip.title}: ${tip.rows[0].value} deaths` : undefined}
        onpointerdown={down}
        onpointermove={move}
        onpointerup={up}
        onpointerleave={() => {
          if (!drag) hover = null;
        }}
        onkeydown={key}
        onfocus={() => (hover = hover ?? peak)}
        onblur={() => (hover = null)}
      />
    </svg>
    {#if tip}
      <Tooltip x={tip.x} y={top} width={W} visible={true} title={tip.title} rows={tip.rows} />
    {/if}
  {/if}
</div>

<style>
  .spine {
    position: relative;
    width: 100%;
    touch-action: pan-y;
    user-select: none;
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
  .era line {
    stroke: var(--ink-2);
    stroke-width: 1.2;
  }
  .era text {
    font: 400 12.5px var(--font);
    fill: var(--ink-2);
  }
  .compact .era text {
    font-size: 11.5px;
  }
</style>
