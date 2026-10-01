<script lang="ts">
  /**
   * World choropleth (Equal Earth). Classes are quantiles of the visible values on a one-hue ramp;
   * countries outside the region recede, and the projection zooms to the region.
   */
  import { geoEqualEarth, geoPath } from "d3-geo";
  import { scaleQuantile } from "d3-scale";
  import type { FeatureCollection, Geometry } from "geojson";
  import { feature } from "topojson-client";
  import world from "world-atlas/countries-110m.json";
  import Tooltip from "../../components/Tooltip.svelte";
  import { RAMP_STEPS, rampColor } from "./ramp";

  interface Props {
    values: Map<string, number | null>; // keyed by ISO numeric code
    names: Map<string, { iso: string; name: string }>; // numeric -> country
    inRegion: (numeric: string) => boolean;
    color: string;
    metric: "deaths" | "vax" | "hosp";
    format: (v: number) => string;
    metricLabel: string;
    onpick: (iso: string) => void;
    ariaLabel: string;
  }
  let { values, names, inRegion, color, metric, format, metricLabel, onpick, ariaLabel }: Props = $props();

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const topo = world as any;
  const land = feature(topo, topo.objects.countries) as unknown as FeatureCollection<Geometry, { name: string }>;
  const features = land.features.filter((f) => f.properties.name !== "Antarctica");

  let width = $state(0);
  let W = $derived(Math.max(width, 280));
  let H = $derived(Math.round(W * 0.5));
  let focus = $derived(features.filter((f) => f.id !== undefined && inRegion(String(f.id))));
  let projection = $derived(
    geoEqualEarth().fitExtent(
      [
        [4, 4],
        [W - 4, H - 4],
      ],
      { type: "FeatureCollection", features: focus.length && focus.length < features.length * 0.9 ? focus : features } as FeatureCollection,
    ),
  );
  let path = $derived(geoPath(projection));

  const STEPS = RAMP_STEPS;
  let visible = $derived([...values].filter(([k, v]) => v !== null && inRegion(k)).map(([, v]) => v as number));
  let quant = $derived(scaleQuantile<number>().domain(visible.length ? visible : [0, 1]).range(STEPS));
  let thresholds = $derived(quant.quantiles());
  const fillFor = (numeric: string | undefined) => {
    if (numeric === undefined) return "var(--seq-0)";
    const v = values.get(numeric);
    if (v === null || v === undefined) return "var(--seq-0)";
    return rampColor(metric, quant(v));
  };

  let hover = $state<{ id: string; x: number; y: number } | null>(null);
  let wrap = $state<HTMLDivElement>();
  function move(e: PointerEvent, id: string) {
    const b = wrap!.getBoundingClientRect();
    hover = { id, x: e.clientX - b.left, y: Math.max(e.clientY - b.top - 70, 0) };
  }
</script>

<div class="map" bind:clientWidth={width} bind:this={wrap}>
  {#if width}
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={ariaLabel}>
      <path d={path({ type: "Sphere" }) ?? ""} fill="none" stroke="var(--hair)" />
      {#each features as f (f.id ?? f.properties.name)}
        {@const id = f.id === undefined ? undefined : String(f.id)}
        {@const country = id ? names.get(id) : undefined}
        <path
          d={path(f) ?? ""}
          style:fill={fillFor(id)}
          stroke="var(--plane)"
          stroke-width="0.6"
          opacity={id && !inRegion(id) ? 0.35 : 1}
          class:active={hover?.id === id}
          class:clickable={!!country}
          role="presentation"
          onpointermove={(e) => id && move(e, id)}
          onpointerleave={() => (hover = null)}
          onclick={() => country && onpick(country.iso)}
        />
      {/each}
    </svg>
    {#if hover && names.get(hover.id)}
      {@const v = values.get(hover.id)}
      <Tooltip
        x={hover.x}
        y={hover.y}
        width={W}
        visible={true}
        title={names.get(hover.id)?.name}
        rows={[{ color, label: metricLabel, value: v === null || v === undefined ? "no data" : format(v) }]}
      />
    {/if}
    <div class="legend" aria-label={`Legend: ${metricLabel}`}>
      <span class="swatch none"></span><span>No data</span>
      {#each STEPS as s, i}
        <span class="swatch" style:background={rampColor(metric, s)}></span>
        {#if i === 0}<span>below {format(thresholds[0] ?? 0)}</span>{/if}
        {#if i === STEPS.length - 1}<span>{format(thresholds[thresholds.length - 1] ?? 0)} and above</span>{/if}
      {/each}
    </div>
  {/if}
</div>

<style>
  .map {
    position: relative;
    width: 100%;
  }
  svg {
    display: block;
  }
  path.clickable {
    cursor: pointer;
  }
  path.active {
    stroke: var(--ink);
    stroke-width: 1.2;
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px;
    margin-top: 10px;
    font-size: 12.5px;
    color: var(--ink-2);
  }
  .legend span:not(.swatch) {
    margin: 0 8px 0 4px;
  }
  .swatch {
    width: 22px;
    height: 10px;
    border-radius: 2px;
    display: inline-block;
  }
  .swatch.none {
    background: var(--seq-0);
    border: 1px solid var(--hair-2);
  }
</style>
