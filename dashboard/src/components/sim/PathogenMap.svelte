<script lang="ts">
  /**
   * The pathogen picker: every preset on "how contagious" (R0) against "how deadly" (IFR), both on
   * log scales. Click a dot to load a preset; drag the ringed marker to make your own disease.
   * The shaded box is where the country models were trained (SARS-CoV-2, 2020-2022): outside it,
   * country effects are an extrapolation.
   */
  import { scaleLog } from "d3-scale";
  import type { Pathogen } from "../../lib/sim/scenario";
  import { sim } from "../../lib/sim/store.svelte";
  import Tooltip from "../Tooltip.svelte";

  let { presets, current, presetId, onpick }: { presets: Pathogen[]; current: Pathogen; presetId: string; onpick: (id: string) => void } = $props();

  let width = $state(0);
  let W = $derived(Math.max(width, 240));
  const height = 280;
  const m = { top: 20, right: 10, bottom: 32, left: 44 };
  let x = $derived(scaleLog().domain([0.5, 20]).range([m.left, W - m.right]).clamp(true));
  let y = $derived(scaleLog().domain([0.00001, 0.5]).range([height - m.bottom, m.top]).clamp(true));
  const TRAINED = { r0: [2.5, 9], ifr: [0.001, 0.02] };
  const short: Record<string, string> = {
    seasonal_flu: "Seasonal flu",
    flu_2009: "2009 flu",
    flu_1957: "1957 flu",
    flu_1968: "1968 flu",
    flu_1918: "1918 flu",
    covid_ancestral: "COVID 2020",
    covid_delta: "Delta",
    covid_omicron: "Omicron",
    sars_2003: "SARS",
    mers: "MERS",
    h5n1_hypothetical: "H5N1 (what if)",
    smallpox: "Smallpox",
    measles: "Measles",
    disease_x: "Disease X",
  };
  const ifrText = (v: number) => (v >= 0.01 ? `${(v * 100).toFixed(1)}%` : `${(v * 100).toPrecision(2)}%`);

  // Label placement: the chosen preset first, then the rest in order. Each label tries right, left,
  // above and below its dot, and takes the first spot that clears every dot, every placed label and
  // the plot edges. A label with nowhere to go is left off (its dot still has a tooltip and a button).
  let labelled = $derived.by(() => {
    type Box = { x0: number; x1: number; y0: number; y1: number };
    const hit = (a: Box, b: Box) => a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0;
    const dots: Box[] = presets.map((p) => ({ x0: x(p.r0) - 6, x1: x(p.r0) + 6, y0: y(p.ifr) - 6, y1: y(p.ifr) + 6 }));
    const placed: Box[] = [];
    const order = [...presets].sort((a, b) => Number(b.id === presetId) - Number(a.id === presetId));
    const spots = new Map<string, { lx: number; py: number } | null>();
    for (const p of order) {
      const cx = x(p.r0);
      const cy = y(p.ifr);
      const w = (short[p.id] ?? p.name).length * 6.6;
      const candidates = [
        { lx: cx + 8, py: cy + 4 },
        { lx: cx - 8 - w, py: cy + 4 },
        { lx: cx - w / 2, py: cy - 9 },
        { lx: cx - w / 2, py: cy + 17 },
      ];
      const own = presets.indexOf(p);
      const spot = candidates.find(({ lx, py }) => {
        const box = { x0: lx - 2, x1: lx + w + 2, y0: py - 11, y1: py + 3 };
        if (box.x0 < m.left - 4 || box.x1 > W || box.y0 < m.top - 14 || box.y1 > height - m.bottom) return false;
        return !dots.some((d, i) => i !== own && hit(box, d)) && !placed.some((b) => hit(box, b));
      });
      const chosen = spot ?? (p.id === presetId ? candidates[0] : null);
      if (chosen) placed.push({ x0: chosen.lx - 2, x1: chosen.lx + w + 2, y0: chosen.py - 11, y1: chosen.py + 3 });
      spots.set(p.id, chosen);
    }
    return presets.map((p) => ({ p, spot: spots.get(p.id) ?? null }));
  });
  let edited = $derived(Math.abs(current.r0 - (presets.find((p) => p.id === presetId)?.r0 ?? 0)) > 1e-9 || Math.abs(current.ifr - (presets.find((p) => p.id === presetId)?.ifr ?? 0)) > 1e-12);

  let svgEl = $state<SVGSVGElement>();
  let dragging = $state(false);
  let hover = $state<Pathogen | null>(null);
  function point(e: PointerEvent) {
    const b = svgEl!.getBoundingClientRect();
    return { px: ((e.clientX - b.left) / b.width) * W, py: ((e.clientY - b.top) / b.height) * height };
  }
  function drag(e: PointerEvent) {
    if (!dragging) return;
    const { px, py } = point(e);
    sim.setPathogen("r0", Math.round(x.invert(px) * 100) / 100);
    sim.setPathogen("ifr", Number(y.invert(py).toPrecision(2)));
  }
  function nearest(e: PointerEvent) {
    const { px, py } = point(e);
    let best: Pathogen | null = null;
    let bd = 22 * 22;
    for (const p of presets) {
      const d = (x(p.r0) - px) ** 2 + (y(p.ifr) - py) ** 2;
      if (d < bd) [best, bd] = [p, d];
    }
    return best;
  }
</script>

<div class="map" bind:clientWidth={width}>
  {#if width}
    <!-- Clicking a dot is a mouse shortcut: the preset buttons below and the draggable handle
         give the same choices to keyboard and screen-reader users. -->
    <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
    <svg
      bind:this={svgEl}
      viewBox={`0 0 ${W} ${height}`}
      width={W}
      {height}
      role="img"
      aria-label="Pathogens by how contagious (R0) and how deadly (infection fatality rate). Use the preset buttons below to choose one."
      onpointermove={(e) => (dragging ? drag(e) : (hover = nearest(e)))}
      onpointerup={() => (dragging = false)}
      onpointerleave={() => ((dragging = false), (hover = null))}
      onclick={(e) => {
        const p = nearest(e as unknown as PointerEvent);
        if (p && !dragging) onpick(p.id);
      }}
    >
      <rect
        x={x(TRAINED.r0[0])}
        y={y(TRAINED.ifr[1])}
        width={x(TRAINED.r0[1]) - x(TRAINED.r0[0])}
        height={y(TRAINED.ifr[0]) - y(TRAINED.ifr[1])}
        fill="var(--ink)"
        opacity="0.05"
        rx="4"
      />
      {#each [1, 2, 5, 10, 20] as t}
        <line x1={x(t)} x2={x(t)} y1={m.top} y2={height - m.bottom} stroke="var(--hair)" />
        <text class="axis-label" x={x(t)} y={height - m.bottom + 15} text-anchor="middle">{t}</text>
      {/each}
      {#each [0.0001, 0.001, 0.01, 0.1] as t}
        <line x1={m.left} x2={W - m.right} y1={y(t)} y2={y(t)} stroke="var(--hair)" />
        <text class="axis-label" x={m.left - 6} y={y(t) + 4} text-anchor="end">{ifrText(t)}</text>
      {/each}
      <line x1={x(1)} x2={x(1)} y1={m.top} y2={height - m.bottom} stroke="var(--muted)" stroke-dasharray="3 3" />
      <text class="axis-label" x={W - m.right} y={height - 2} text-anchor="end">more contagious (R0) →</text>
      <text class="axis-label" x={m.left} y={m.top - 8}>↑ deadlier (infection fatality rate)</text>
      {#each presets as p (p.id)}
        <circle
          cx={x(p.r0)}
          cy={y(p.ifr)}
          r={p.id === presetId ? 6 : 4.5}
          fill={p.id === presetId ? "var(--ink)" : "var(--plane)"}
          stroke={p.id === presetId ? "var(--plane)" : "var(--ink-2)"}
          stroke-width="1.5"
          stroke-dasharray={p.kind === "hypothetical" ? "2 2" : undefined}
        />
      {/each}
      {#each labelled as { p, spot } (p.id)}
        {#if spot}<text class="mark-label halo" x={spot.lx} y={spot.py} style:fill={p.id === presetId ? "var(--ink)" : "var(--ink-2)"}>{short[p.id] ?? p.name}</text>{/if}
      {/each}
      {#if edited}
        <line x1={x(presets.find((p) => p.id === presetId)!.r0)} y1={y(presets.find((p) => p.id === presetId)!.ifr)} x2={x(current.r0)} y2={y(current.ifr)} stroke="var(--ink-2)" stroke-dasharray="2 3" />
      {/if}
      <circle
        class="handle"
        cx={x(current.r0)}
        cy={y(current.ifr)}
        r="10"
        fill="none"
        stroke="var(--deaths)"
        stroke-width="2.5"
        role="slider"
        tabindex="0"
        aria-label="Your disease: drag to change how contagious and how deadly it is"
        aria-valuetext={`R0 ${current.r0.toFixed(2)}, fatality ${ifrText(current.ifr)}`}
        aria-valuenow={current.r0}
        onpointerdown={(e) => {
          e.stopPropagation();
          dragging = true;
          (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
        }}
        onkeydown={(e) => {
          const k = e.shiftKey ? 1.25 : 1.05;
          if (e.key === "ArrowRight") sim.setPathogen("r0", Math.min(20, current.r0 * k));
          else if (e.key === "ArrowLeft") sim.setPathogen("r0", Math.max(0.5, current.r0 / k));
          else if (e.key === "ArrowUp") sim.setPathogen("ifr", Math.min(0.5, current.ifr * k));
          else if (e.key === "ArrowDown") sim.setPathogen("ifr", Math.max(0.00001, current.ifr / k));
          else return;
          e.preventDefault();
        }}
      />
    </svg>
    {#if hover && !dragging}
      <Tooltip x={x(hover.r0)} y={y(hover.ifr)} width={W} visible={true} title={hover.name} rows={[{ label: "R0", value: hover.r0.toFixed(2) }, { label: "Infection fatality", value: ifrText(hover.ifr) }]} />
    {/if}
  {/if}
</div>
<p class="key">
  <span class="box"></span>where the country models were trained
  <span class="ring"></span>your disease: drag it, or pick a preset
</p>
<div class="presets" role="group" aria-label="Pathogen presets">
  {#each presets as p (p.id)}
    <button aria-pressed={p.id === presetId} onclick={() => onpick(p.id)}>{short[p.id] ?? p.name}</button>
  {/each}
</div>

<style>
  .map {
    position: relative;
    width: 100%;
  }
  svg {
    display: block;
    overflow: visible;
    cursor: pointer;
    touch-action: none;
  }
  .halo {
    paint-order: stroke;
    stroke: var(--plane);
    stroke-width: 3px;
    stroke-linejoin: round;
  }
  .handle {
    cursor: grab;
    outline: none;
  }
  .handle:focus-visible {
    stroke: var(--focus);
  }
  .key {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 8px;
    margin-top: 6px;
    font-size: 12px;
    color: var(--muted);
  }
  .box,
  .ring {
    display: inline-block;
    width: 12px;
    height: 12px;
    flex: none;
  }
  .box {
    background: color-mix(in oklab, var(--ink) 10%, transparent);
    border-radius: 3px;
  }
  .ring {
    border: 2px solid var(--deaths);
    border-radius: 50%;
    margin-left: 8px;
  }
  .presets {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 12px;
  }
  .presets button {
    border: 1px solid var(--hair-2);
    background: var(--plane);
    border-radius: 999px;
    padding: 3px 11px;
    font-size: 13px;
    color: var(--ink-2);
    cursor: pointer;
  }
  .presets button[aria-pressed="true"] {
    background: var(--ink);
    border-color: var(--ink);
    color: var(--plane);
  }
</style>
