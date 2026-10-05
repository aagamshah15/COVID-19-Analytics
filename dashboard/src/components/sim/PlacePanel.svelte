<script lang="ts">
  import { compact, pct } from "../../lib/format";
  import type { SignalName } from "../../lib/sim/model";
  import { sim } from "../../lib/sim/store.svelte";
  import Field, { type Provenance } from "./Field.svelte";

  let r = $derived(sim.resolved!);
  let model = $derived(sim.model!);
  let showMore = $state(false);

  interface SignalField {
    name: SignalName;
    label: string;
    min: number;
    max: number;
    log?: boolean;
    step?: number;
    format: (v: number) => string;
  }
  const money = (v: number) => `$${compact(v)}`;
  const one = (v: number) => v.toFixed(v < 10 ? 1 : 0);
  const share = (v: number) => `${Math.round(v)}%`;

  const MAIN: SignalField[] = [
    { name: "gdp_per_capita", label: "GDP per person", min: 500, max: 150000, log: true, format: money },
    { name: "health_exp_per_capita", label: "Health spending per person", min: 10, max: 12000, log: true, format: money },
    { name: "uhc_index", label: "Access to care (UHC index)", min: 20, max: 95, step: 1, format: (v) => `${Math.round(v)} / 100` },
    { name: "physicians_per_thousand", label: "Doctors per 1,000 people", min: 0.02, max: 7, step: 0.01, format: one },
    { name: "hospital_beds_per_thousand", label: "Hospital beds per 1,000 people", min: 0.2, max: 14, step: 0.1, format: one },
  ];
  const MORE: SignalField[] = [
    { name: "urban_share", label: "Living in cities", min: 10, max: 100, step: 1, format: share },
    { name: "population_density", label: "People per km²", min: 1, max: 8000, log: true, format: (v) => compact(v) },
    { name: "diabetes_prevalence", label: "Adults with diabetes", min: 1, max: 25, step: 0.1, format: (v) => `${v.toFixed(1)}%` },
    { name: "basic_sanitation", label: "Basic sanitation", min: 10, max: 100, step: 1, format: share },
    { name: "extreme_poverty", label: "In extreme poverty", min: 0, max: 80, step: 0.5, format: (v) => `${v.toFixed(1)}%` },
    { name: "out_of_pocket_share", label: "Health costs paid out of pocket", min: 5, max: 85, step: 1, format: share },
    { name: "measles_immunization", label: "Children vaccinated against measles", min: 30, max: 99, step: 1, format: share },
  ];

  const medianOf = (name: SignalName) => {
    const values = model.countries.map((c) => c.signals[name]).filter((v): v is number => v !== null).sort((a, b) => a - b);
    return values[Math.floor(values.length / 2)];
  };
  function provenance(name: SignalName): Provenance {
    if (sim.spec.place.signals?.[name] !== undefined) return "edited";
    return r.country.signals[name] === null ? "assumption" : "data";
  }
  const signalValue = (name: SignalName) => r.settings.signals[name] ?? medianOf(name);

  const latitudeText = (v: number) => {
    const zone = Math.abs(v) < 23.5 ? "tropics" : Math.abs(v) < 40 ? "subtropics" : "temperate";
    return `${Math.abs(Math.round(v))}°${v >= 0 ? "N" : "S"} · ${zone}`;
  };
  const SOURCE: Record<string, Provenance> = { calibrated: "calibrated", observed: "observed", predicted: "predicted", user: "edited" };
</script>

<div class="panel">
  {#if r.edited.place.length || Object.keys(sim.spec.learned).length}
    <button class="link-button" onclick={() => sim.resetPlaceAll()}>Reset everything to {r.country.name}'s data</button>
  {/if}

  <Field
    label="Population"
    value={r.settings.population}
    min={100_000}
    max={1_500_000_000}
    log
    format={(v) => (v >= 1e9 ? `${(v / 1e9).toFixed(2)} billion` : compact(v))}
    onchange={(v) => sim.setPlace("population", v)}
    provenance={sim.spec.place.population !== undefined ? "edited" : "data"}
    onreset={() => sim.resetPlace("population")}
  />
  <Field
    label="Median age"
    value={r.settings.signals.median_age ?? 30}
    min={15}
    max={55}
    step={0.5}
    format={(v) => `${v.toFixed(1)} years`}
    onchange={(v) => sim.setPlace("median_age", v)}
    provenance={sim.spec.place.median_age !== undefined ? "edited" : r.country.age_source === "imputed_from_median_age" ? "predicted" : "data"}
    onreset={() => sim.resetPlace("median_age")}
    hint={`${pct(r.settings.age_shares[3] + r.settings.age_shares[4])} aged 60+`}
  />
  <Field
    label="Climate (latitude)"
    value={r.settings.latitude ?? 0}
    min={-55}
    max={70}
    step={1}
    format={latitudeText}
    onchange={(v) => sim.setPlace("latitude", v)}
    provenance={sim.spec.place.latitude !== undefined ? "edited" : "data"}
    onreset={() => sim.resetPlace("latitude")}
    hint="Sets how seasonal transmission is"
  />
  {#each MAIN as f (f.name)}
    <Field
      label={f.label}
      value={signalValue(f.name)}
      min={f.min}
      max={f.max}
      log={f.log}
      step={f.step}
      format={f.format}
      onchange={(v) => sim.setSignal(f.name, v)}
      provenance={provenance(f.name)}
      onreset={() => sim.resetSignal(f.name)}
    />
  {/each}
  <Field
    label="ICU beds, share of hospital beds"
    value={r.settings.icu_share_of_beds}
    min={0.01}
    max={0.15}
    step={0.005}
    format={(v) => pct(v, 1)}
    onchange={(v) => sim.setPlace("icu_share_of_beds", v)}
    provenance={sim.spec.place.icu_share_of_beds !== undefined ? "edited" : "assumption"}
    onreset={() => sim.resetPlace("icu_share_of_beds")}
  />

  <button class="more" aria-expanded={showMore} onclick={() => (showMore = !showMore)}>
    {showMore ? "Fewer" : "More"} signals
  </button>
  {#if showMore}
    {#each MORE as f (f.name)}
      <Field
        label={f.label}
        value={signalValue(f.name)}
        min={f.min}
        max={f.max}
        log={f.log}
        step={f.step}
        format={f.format}
        onchange={(v) => sim.setSignal(f.name, v)}
        provenance={provenance(f.name)}
        onreset={() => sim.resetSignal(f.name)}
      />
    {/each}
  {/if}

  <h3 class="learned-h">What the models learned about this place</h3>
  <p class="note">Estimated from 2020-2023 data. Change the signals above and these follow; set the last three yourself if you know better.</p>
  <dl class="learned">
    <div>
      <dt>Transmission</dt>
      <dd>×{r.learned.transmission.value.toFixed(2)} <span class="src">{r.learned.transmission.source}</span></dd>
    </div>
    <div>
      <dt>Severity in people 60+</dt>
      <dd>×{r.learned.severity.value.toFixed(2)} <span class="src">{r.learned.severity.source}</span></dd>
    </div>
    <div>
      <dt>Tolerance of deaths before pulling back</dt>
      <dd>×{r.learned.awareness.value.toFixed(2)} <span class="src">{r.learned.awareness.source}</span></dd>
    </div>
    <div>
      <dt>Lockdown adherence</dt>
      <dd>×{r.learned.adherence.value.toFixed(2)} <span class="src">predicted</span></dd>
    </div>
  </dl>
  <Field
    label="Share of deaths reported"
    value={r.run.place.death_reporting}
    min={0.02}
    max={1}
    step={0.01}
    format={(v) => pct(v)}
    onchange={(v) => sim.setLearned("reporting", v)}
    provenance={SOURCE[r.run.sources.reporting]}
    onreset={() => sim.resetLearned("reporting")}
  />
  <Field
    label="Vaccine acceptance (adults)"
    value={r.run.place.vaccine_acceptance}
    min={0.1}
    max={0.99}
    step={0.01}
    format={(v) => pct(v)}
    onchange={(v) => sim.setLearned("vaccine_acceptance", v)}
    provenance={SOURCE[r.run.sources.vaccine_acceptance]}
    onreset={() => sim.resetLearned("vaccine_acceptance")}
  />
  <Field
    label="Vaccine rollout speed"
    value={r.run.place.vaccine_capacity}
    min={0.0002}
    max={0.02}
    log
    format={(v) => `${(v * 100).toFixed(2)}% a day`}
    onchange={(v) => sim.setLearned("vaccine_capacity", v)}
    provenance={SOURCE[r.run.sources.vaccine_capacity]}
    onreset={() => sim.resetLearned("vaccine_capacity")}
    hint="Share of the population vaccinated per day at full speed"
  />
</div>

<style>
  .more {
    margin: 12px 0 4px;
    background: none;
    border: 1px solid var(--hair-2);
    border-radius: 8px;
    padding: 5px 12px;
    font-size: 13.5px;
    color: var(--ink-2);
    cursor: pointer;
  }
  .learned-h {
    margin-top: 22px;
    font-size: 15px;
  }
  .note {
    margin-top: 4px;
    font-size: 13px;
    color: var(--ink-2);
  }
  .learned {
    margin: 10px 0 0;
    display: grid;
    gap: 6px;
  }
  .learned div {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    font-size: 14px;
  }
  dt {
    color: var(--ink);
  }
  dd {
    margin: 0;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .src {
    font-weight: 400;
    font-size: 12px;
    color: var(--muted);
    margin-left: 6px;
  }
</style>
