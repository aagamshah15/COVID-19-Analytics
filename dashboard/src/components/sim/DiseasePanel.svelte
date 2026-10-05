<script lang="ts">
  import { pct } from "../../lib/format";
  import { type AgeProfile, bandSeverity, type Pathogen } from "../../lib/sim/scenario";
  import { sim } from "../../lib/sim/store.svelte";
  import Field, { type Provenance } from "./Field.svelte";
  import PathogenMap from "./PathogenMap.svelte";

  let r = $derived(sim.resolved!);
  let model = $derived(sim.model!);
  let p = $derived(r.pathogen);
  let showMore = $state(false);

  function provenance(key: keyof Pathogen, assumptionKey: string = key): Provenance {
    if (key in sim.spec.pathogen.edits) return "edited";
    if (r.basePathogen.kind === "blank") return "assumption";
    return r.basePathogen.assumptions.includes(assumptionKey) ? "assumption" : "literature";
  }
  const ifrText = (v: number) => (v >= 0.01 ? pct(v, 1) : v >= 0.001 ? pct(v, 2) : `${(v * 100).toPrecision(2)}%`);
  let localIfr = $derived.by(() => {
    const { ifr } = bandSeverity(p, r.run.place, model.constants);
    return ifr.reduce((s, v, b) => s + v * r.run.place.age_shares[b], 0);
  });
  const PROFILES: { id: AgeProfile; label: string }[] = [
    { id: "steep", label: "Rises steeply with age (COVID-19)" },
    { id: "rises", label: "Rises with age (influenza)" },
    { id: "w_shaped", label: "Young adults hit hard (1918)" },
    { id: "young", label: "Children and older adults (measles)" },
    { id: "flat", label: "Same at every age" },
  ];
  const days = (v: number) => `${v.toFixed(v < 10 ? 1 : 0)} days`;
  let lifelong = $derived(!Number.isFinite(p.immunity_days));
  let variantOn = $derived(sim.spec.variant !== null);
  const DEFAULT_VARIANT = { day: 270, transmission: 1.6, severity: 1.0, escape: 0.3 };
</script>

<div class="panel">
  <PathogenMap presets={model.presets} current={p} presetId={sim.spec.pathogen.preset ?? ""} onpick={(id) => sim.setPreset(id)} />

  {#if r.basePathogen.kind === "hypothetical"}
    <p class="flag">Hypothetical: no such outbreak has happened. Its transmissibility is an assumption.</p>
  {/if}
  {#if r.basePathogen.sources.length}
    <p class="sources">Sources: {r.basePathogen.sources.join("; ")}.</p>
  {/if}

  <Field
    label="How contagious (R0)"
    value={p.r0}
    min={0.5}
    max={20}
    log
    format={(v) => v.toFixed(v < 10 ? 2 : 1)}
    onchange={(v) => sim.setPathogen("r0", v)}
    provenance={provenance("r0")}
    onreset={() => sim.resetPathogen("r0")}
    hint={p.r0 < 1 ? "Below 1: each case infects fewer than one other, so outbreaks die out" : undefined}
  />
  <Field
    label="How deadly (infection fatality rate)"
    value={p.ifr}
    min={0.00001}
    max={0.5}
    log
    format={ifrText}
    onchange={(v) => sim.setPathogen("ifr", v)}
    provenance={provenance("ifr")}
    onreset={() => sim.resetPathogen("ifr")}
    hint={`At world-average ages; in this place ${ifrText(localIfr)}`}
  />
  <label class="select">
    <span>Who it hits hardest</span>
    <select value={p.age_profile} onchange={(e) => sim.setPathogen("age_profile", e.currentTarget.value as AgeProfile)}>
      {#each PROFILES as profile}<option value={profile.id}>{profile.label}</option>{/each}
    </select>
  </label>
  <Field
    label="Needing hospital care"
    value={p.hosp}
    min={0.0005}
    max={1}
    log
    format={(v) => pct(v, v < 0.1 ? 1 : 0)}
    onchange={(v) => sim.setPathogen("hosp", v)}
    provenance={provenance("hosp")}
    onreset={() => sim.resetPathogen("hosp")}
    hint="Share of infections, at world-average ages"
  />

  <button class="more" aria-expanded={showMore} onclick={() => (showMore = !showMore)}>{showMore ? "Fewer" : "More"} disease settings</button>
  {#if showMore}
    <Field label="Incubation before infectious" value={p.latent_days} min={0.5} max={14} step={0.5} format={days} onchange={(v) => sim.setPathogen("latent_days", v)} provenance={provenance("latent_days")} onreset={() => sim.resetPathogen("latent_days")} />
    <Field label="Infectious for" value={p.infectious_days} min={1} max={14} step={0.5} format={days} onchange={(v) => sim.setPathogen("infectious_days", v)} provenance={provenance("infectious_days")} onreset={() => sim.resetPathogen("infectious_days")} />
    <Field label="Hospital stay" value={p.hosp_days} min={2} max={30} step={1} format={days} onchange={(v) => sim.setPathogen("hosp_days", v)} provenance={provenance("hosp_days")} onreset={() => sim.resetPathogen("hosp_days")} />
    <Field
      label="Immunity after infection lasts"
      value={lifelong ? 1825 : p.immunity_days}
      min={60}
      max={1825}
      step={15}
      format={(v) => (lifelong ? "lifelong" : v >= 365 ? `${(v / 365).toFixed(1)} years` : `${Math.round(v / 30.4)} months`)}
      onchange={(v) => sim.setPathogen("immunity_days", v)}
      provenance={provenance("immunity_days")}
      onreset={() => sim.resetPathogen("immunity_days")}
      disabled={lifelong}
    />
    <label class="check"><input type="checkbox" checked={lifelong} onchange={(e) => sim.setPathogen("immunity_days", e.currentTarget.checked ? Infinity : 365)} /> Lifelong immunity</label>
    <Field
      label="Seasonality"
      value={p.seasonality ?? model.constants.covid_seasonality}
      min={0}
      max={0.6}
      step={0.01}
      format={(v) => `${Math.round(((2 * v) / (1 + v)) * 100)}% winter-to-summer drop`}
      onchange={(v) => sim.setPathogen("seasonality", v)}
      provenance={"seasonality" in sim.spec.pathogen.edits ? "edited" : r.basePathogen.seasonality === null ? "learned" : provenance("seasonality")}
      onreset={() => sim.resetPathogen("seasonality")}
      hint="At 40° latitude and above; none in the tropics"
    />
    <Field label="Vaccine protection against infection" value={p.ve_infection} min={0} max={0.98} step={0.01} format={(v) => pct(v)} onchange={(v) => sim.setPathogen("ve_infection", v)} provenance={provenance("ve_infection", "vaccine")} onreset={() => sim.resetPathogen("ve_infection")} />
    <Field label="Vaccine protection against death" value={p.ve_death} min={0} max={0.99} step={0.01} format={(v) => pct(v)} onchange={(v) => sim.setPathogen("ve_death", v)} provenance={provenance("ve_death", "vaccine")} onreset={() => sim.resetPathogen("ve_death")} />
  {/if}

  <h3 class="sub-h">A new variant</h3>
  <label class="check"><input type="checkbox" checked={variantOn} onchange={(e) => sim.setVariant(e.currentTarget.checked ? DEFAULT_VARIANT : null)} /> A variant takes over mid-epidemic</label>
  {#if sim.spec.variant}
    {@const v = sim.spec.variant}
    <Field label="Arrives on day" value={v.day} min={30} max={r.days - 30} step={5} format={(d) => `day ${Math.round(d)} (${(d / 30.4).toFixed(0)} months)`} onchange={(d) => sim.setVariant({ ...v, day: d })} />
    <Field label="More contagious by" value={v.transmission} min={1} max={3} step={0.05} format={(x) => `×${x.toFixed(2)}`} onchange={(x) => sim.setVariant({ ...v, transmission: x })} />
    <Field label="Severity" value={v.severity} min={0.2} max={3} step={0.05} format={(x) => `×${x.toFixed(2)}`} onchange={(x) => sim.setVariant({ ...v, severity: x })} />
    <Field label="Escapes existing immunity" value={v.escape} min={0} max={0.8} step={0.05} format={(x) => pct(x)} onchange={(x) => sim.setVariant({ ...v, escape: x })} />
  {/if}
</div>

<style>
  .flag {
    margin-top: 10px;
    font-size: 13.5px;
    color: var(--ink);
    border-left: 3px solid var(--hosp);
    padding-left: 10px;
  }
  .sources {
    margin-top: 8px;
    font-size: 12.5px;
    color: var(--muted);
  }
  .select {
    display: grid;
    gap: 6px;
    padding: 10px 0 12px;
    border-bottom: 1px solid var(--hair);
    font-size: 14px;
  }
  .check {
    display: flex;
    gap: 8px;
    align-items: center;
    font-size: 14px;
    padding: 8px 0;
  }
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
  .sub-h {
    margin-top: 20px;
    font-size: 15px;
  }
</style>
