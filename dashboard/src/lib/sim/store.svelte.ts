/**
 * Simulator page state.
 *
 * * `spec` is the draft the steps edit; `resolved` previews it for the fine-tune controls.
 * * `applied` is what was last run; `result` resolves it. Results only ever show `applied`, so
 *   what's on screen always matches what was run. Nothing runs until the visitor presses Run.
 */
import type { EngineOutputs } from "./engine";
import { loadSimulator, type SignalName, type SimModel } from "./model";
import type { ReadyScenario } from "./scenarios";
import type { Pathogen, Segment, Variant } from "./scenario";
import { decodeSpec, EMPTY_SPEC, isComplete, type Overridable, type PlanId, resolve, type Shift, type SimSpec, type VaccineChoice } from "./spec";

export type View = "start" | "build" | "results";

/** A scenario pinned on the detailed chart, kept across runs so changes can be compared. */
export interface Pin {
  id: string;
  label: string;
  outputs: EngineOutputs;
  population: number;
  deaths: number;
}

class SimStore {
  model = $state<SimModel | null>(null);
  error = $state<string | null>(null);
  spec = $state<SimSpec>(EMPTY_SPEC());
  applied = $state<SimSpec | null>(null);
  view = $state<View>("start");
  step = $state<1 | 2 | 3>(1);
  /** Bumped on every Run, so the page restarts the computation even for an identical scenario. */
  runId = $state(0);
  readyId = $state<string | null>(null);
  pins = $state<Pin[]>([]);
  resolved = $derived(this.model ? resolve(this.model, this.spec) : null);
  result = $derived(this.model && this.applied ? resolve(this.model, this.applied) : null);
  complete = $derived(isComplete(this.spec));
  private loading: Promise<void> | null = null;

  load(): Promise<void> {
    this.loading ??= loadSimulator()
      .then((m) => {
        this.model = m;
      })
      .catch((e: Error) => {
        this.error = e.message;
      });
    return this.loading;
  }

  /**
   * Open a shared link (straight to its results), a link with a country (first step, that country
   * chosen), or a blank start. Coming back to the page without either resumes where the visitor was.
   */
  open(encoded: string, iso: string | null) {
    if (!encoded && !iso && (this.applied || this.view === "build")) return;
    const decoded = encoded ? decodeSpec(encoded) : null;
    if (decoded && this.applied && JSON.stringify(decoded) === JSON.stringify($state.snapshot(this.applied))) return;
    if (decoded && decoded.iso && this.model?.byIso.has(decoded.iso)) {
      this.spec = decoded;
      this.run();
      return;
    }
    this.spec = EMPTY_SPEC();
    this.applied = null;
    if (iso && this.model?.byIso.has(iso)) {
      this.spec.iso = iso;
      this.view = "build";
      this.step = 1;
    } else {
      this.view = "start";
    }
  }

  // --- flow ---------------------------------------------------------------------------------
  build() {
    this.spec = EMPTY_SPEC();
    this.readyId = null;
    this.view = "build";
    this.step = 1;
  }
  run() {
    if (!isComplete(this.spec)) return;
    this.applied = $state.snapshot(this.spec);
    this.view = "results";
    this.runId++;
  }
  /** Change the last-run scenario: reopen the steps with it. */
  edit(step: 1 | 2 | 3 = 1) {
    if (this.applied) this.spec = $state.snapshot(this.applied);
    this.view = "build";
    this.step = step;
  }
  startOver() {
    this.spec = EMPTY_SPEC();
    this.applied = null;
    this.pins = [];
    this.readyId = null;
    this.view = "start";
  }
  loadReady(s: ReadyScenario) {
    this.spec = structuredClone(s.spec);
    this.readyId = s.id;
    this.run();
  }
  /** True when the draft differs from what was last run. */
  get changed(): boolean {
    return !!this.applied && JSON.stringify($state.snapshot(this.spec)) !== JSON.stringify(this.applied);
  }

  // --- place --------------------------------------------------------------------------------
  setCountry(iso: string) {
    this.spec = { ...this.spec, iso, place: {}, learned: {}, simple: { age: 0, care: 0 } };
  }
  setSimple(key: "age" | "care", value: Shift) {
    this.spec.simple = { ...this.spec.simple, [key]: value };
    // A plain choice replaces fine-tuned values it covers.
    if (key === "age") this.resetPlace("median_age");
    else for (const s of ["hospital_beds_per_thousand", "physicians_per_thousand", "health_exp_per_capita", "uhc_index"] as SignalName[]) this.resetSignal(s);
  }
  setSignal(name: SignalName, value: number) {
    this.spec.place = { ...this.spec.place, signals: { ...this.spec.place.signals, [name]: value } };
  }
  resetSignal(name: SignalName) {
    const { [name]: _, ...rest } = this.spec.place.signals ?? {};
    this.spec.place = { ...this.spec.place, signals: rest };
  }
  setPlace<K extends Exclude<keyof SimSpec["place"], "signals">>(key: K, value: SimSpec["place"][K]) {
    this.spec.place = { ...this.spec.place, [key]: value };
  }
  resetPlace(key: Exclude<keyof SimSpec["place"], "signals">) {
    const { [key]: _, ...rest } = this.spec.place;
    this.spec.place = rest;
  }
  setLearned(key: Overridable, value: number) {
    this.spec.learned = { ...this.spec.learned, [key]: value };
  }
  resetLearned(key: Overridable) {
    const { [key]: _, ...rest } = this.spec.learned;
    this.spec.learned = rest;
  }
  resetPlaceAll() {
    this.spec = { ...this.spec, place: {}, learned: {}, simple: { age: 0, care: 0 } };
  }

  // --- pathogen -----------------------------------------------------------------------------
  setPreset(id: string) {
    this.spec.pathogen = { preset: id, edits: {} };
  }
  setPathogen<K extends keyof Pathogen>(key: K, value: Pathogen[K]) {
    this.spec.pathogen = { ...this.spec.pathogen, edits: { ...this.spec.pathogen.edits, [key]: value } };
  }
  resetPathogen(key: keyof Pathogen) {
    const { [key]: _, ...rest } = this.spec.pathogen.edits;
    this.spec.pathogen = { ...this.spec.pathogen, edits: rest };
  }
  setVariant(variant: Variant | null) {
    this.spec.variant = variant;
  }

  // --- response -----------------------------------------------------------------------------
  setPlan(plan: PlanId) {
    this.spec.plan = plan;
  }
  setSegments(segments: Segment[]) {
    this.spec.segments = segments;
  }
  setVaccine(choice: VaccineChoice) {
    this.spec.vaccine = choice;
    if (choice !== "custom") {
      const { vaccine_day: _, ...rest } = this.spec.response;
      this.spec.response = rest;
    }
  }
  setVaccineDay(day: number) {
    this.spec.vaccine = "custom";
    this.spec.response = { ...this.spec.response, vaccine_day: day };
  }
  setResponse<K extends keyof SimSpec["response"]>(key: K, value: SimSpec["response"][K]) {
    this.spec.response = { ...this.spec.response, [key]: value };
  }
  setYears(years: SimSpec["years"]) {
    this.spec.years = years;
  }
}

export const sim = new SimStore();
