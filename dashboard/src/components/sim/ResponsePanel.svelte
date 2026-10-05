<script lang="ts">
  import { pct } from "../../lib/format";
  import type { Segment } from "../../lib/sim/scenario";
  import { sim } from "../../lib/sim/store.svelte";
  import Field from "./Field.svelte";

  let r = $derived(sim.resolved!);
  let resp = $derived(r.response);
  const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const week = (d: number) => `week ${Math.round(d / 7)}`;
  let vaccineDay = $derived(resp.vaccine_day ?? r.pathogen.vaccine_day);

  function setSegment(i: number, patch: Partial<Segment>) {
    const segments = resp.segments.map((s, k) => (k === i ? { ...s, ...patch } : s));
    sim.setSegments(segments);
  }
  function addSegment() {
    const last = resp.segments[resp.segments.length - 1];
    const start = last ? Math.min(last.end_day, r.days - 28) : 28;
    sim.setSegments([...resp.segments, { start_day: start, end_day: Math.min(start + 84, r.days), level: 50 }]);
  }
</script>

<div class="panel">
  {#if sim.spec.plan === "custom"}
    {#each resp.segments as seg, i}
      <div class="segment">
        <div class="seg-h"><strong>Period {i + 1}</strong>
          <button class="link-button" onclick={() => sim.setSegments(resp.segments.filter((_, k) => k !== i))}>Remove</button>
        </div>
        <Field label="Starts" value={seg.start_day} min={0} max={r.days - 7} step={7} format={week} onchange={(v) => setSegment(i, { start_day: v, end_day: Math.max(seg.end_day, v + 7) })} />
        <Field label="Ends" value={seg.end_day} min={7} max={r.days} step={7} format={week} onchange={(v) => setSegment(i, { end_day: Math.max(v, seg.start_day + 7) })} />
        <Field label="Strictness (stringency)" value={seg.level} min={0} max={100} step={5} format={(v) => `${Math.round(v)} / 100`} onchange={(v) => setSegment(i, { level: v })} />
      </div>
    {/each}
    {#if resp.segments.length < 3}<button class="more" onclick={addSegment}>Add a period</button>{/if}
  {/if}
  {#if sim.spec.plan === "adaptive"}
    <Field label="Lock down when hospitals reach" value={resp.adaptive_on} min={0.1} max={1.5} step={0.05} format={(v) => `${pct(v)} of beds`} onchange={(v) => sim.setResponse("adaptive_on", v)} hint="Beds available to the epidemic" />
    <Field label="Lift when they fall to" value={resp.adaptive_off} min={0.05} max={resp.adaptive_on} step={0.05} format={(v) => `${pct(v)} of beds`} onchange={(v) => sim.setResponse("adaptive_off", v)} />
    <Field label="Strictness" value={resp.adaptive_level} min={20} max={100} step={5} format={(v) => `${Math.round(v)} / 100`} onchange={(v) => sim.setResponse("adaptive_level", v)} />
  {/if}
  <p class="scale">Stringency follows the Oxford COVID-19 Government Response Tracker: 40 is moderate, 75 a strict lockdown.</p>

  <h3 class="sub-h">Timing</h3>
  <label class="select">
    <span>First infections arrive in</span>
    <select value={resp.start_month} onchange={(e) => sim.setResponse("start_month", Number(e.currentTarget.value))}>
      {#each MONTHS as m, i}<option value={i + 1}>{m}</option>{/each}
    </select>
  </label>
  <div class="seg-row">
    <span>Simulate</span>
    <div class="seg small" role="group" aria-label="Horizon">
      {#each [1, 2, 3] as y}
        <button aria-pressed={sim.spec.years === y} onclick={() => sim.setYears(y as 1 | 2 | 3)}>{y} year{y > 1 ? "s" : ""}</button>
      {/each}
    </div>
  </div>
  <Field label="Border measures delay arrival by" value={resp.border_delay_days} min={0} max={180} step={1} format={(v) => `${Math.round(v)} days`} onchange={(v) => sim.setResponse("border_delay_days", v)} />

  <h3 class="sub-h">Health system</h3>
  <Field label="Testing and isolation" value={resp.isolation} min={0} max={0.3} step={0.01} format={(v) => `−${pct(v)} transmission`} onchange={(v) => sim.setResponse("isolation", v)} provenance="assumption" hint="Up to 30%: an assumption, not estimated from data" />
  <Field label="Extra beds in a surge" value={resp.surge} min={0} max={1} step={0.05} format={(v) => `+${pct(v)}`} onchange={(v) => sim.setResponse("surge", v)} />
  <label class="check">
    <input type="checkbox" checked={Number.isFinite(resp.treatment_day)} onchange={(e) => sim.setResponse("treatment_day", e.currentTarget.checked ? 180 : Infinity)} />
    An effective treatment becomes available
  </label>
  {#if Number.isFinite(resp.treatment_day)}
    <Field label="Available from" value={resp.treatment_day} min={0} max={r.days} step={7} format={week} onchange={(v) => sim.setResponse("treatment_day", v)} />
    <Field label="Hospital deaths it prevents" value={resp.treatment_effect} min={0.05} max={0.6} step={0.05} format={(v) => pct(v)} onchange={(v) => sim.setResponse("treatment_effect", v)} provenance="assumption" hint={`Scaled by access to care (${pct(r.run.place.access)})`} />
  {/if}

  {#if resp.vaccine}
    <h3 class="sub-h">Vaccine</h3>
    <Field
      label="Arrives on"
      value={Number.isFinite(vaccineDay) ? vaccineDay : r.days}
      min={0}
      max={r.days}
      step={7}
      format={(v) => `day ${Math.round(v)} (${week(v)})`}
      onchange={(v) => sim.setVaccineDay(v)}
      provenance={sim.spec.vaccine === "custom" ? "edited" : undefined}
    />
    <div class="seg-row">
      <span>Who first</span>
      <div class="seg small" role="group" aria-label="Vaccine priority">
        <button aria-pressed={resp.vaccine_oldest_first} onclick={() => sim.setResponse("vaccine_oldest_first", true)}>Oldest first</button>
        <button aria-pressed={!resp.vaccine_oldest_first} onclick={() => sim.setResponse("vaccine_oldest_first", false)}>Everyone equally</button>
      </div>
    </div>
  {/if}

  <h3 class="sub-h">Behaviour</h3>
  <label class="check"><input type="checkbox" checked={resp.awareness} onchange={(e) => sim.setResponse("awareness", e.currentTarget.checked)} /> People get more careful as deaths rise</label>
  <p class="scale">
    Learned from 2020: in this place, contacts halve at about {(sim.model!.constants.awareness_deaths_pm * r.run.place.awareness).toFixed(1)} reported deaths per million
    per day. Switching it off gives a plain SEIR model, which overshot real epidemics fourfold.
  </p>
  <label class="check"><input type="checkbox" checked={resp.fatigue} onchange={(e) => sim.setResponse("fatigue", e.currentTarget.checked)} /> Restrictions lose effect after 9 months (fatigue)</label>
</div>

<style>
  .segment {
    margin-top: 10px;
    padding-left: 12px;
    border-left: 2px solid var(--hair-2);
  }
  .seg-h {
    display: flex;
    justify-content: space-between;
    font-size: 14px;
  }
  .scale {
    margin-top: 8px;
    font-size: 12.5px;
    color: var(--muted);
  }
  .sub-h {
    margin-top: 22px;
    font-size: 15px;
  }
  .select {
    display: grid;
    gap: 6px;
    padding: 10px 0 12px;
    border-bottom: 1px solid var(--hair);
    font-size: 14px;
  }
  .seg-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    padding: 10px 0;
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
  .check input {
    accent-color: var(--ink);
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
</style>
