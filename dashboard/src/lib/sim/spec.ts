/**
 * A scenario as the visitor builds it: a base country plus edits, a pathogen preset plus edits,
 * and a response. Only differences from the data-backed defaults are stored, so share links stay
 * short and a scenario re-reads the latest trained model when it's opened.
 *
 * A draft starts empty (nothing is chosen for the visitor); `isComplete` says when it can run.
 * `resolve` turns a spec into everything the engine and the page need.
 */
import { ageStructureFor, buildPlace, type CountryProfile, type Learned, type LearnedName, type PlaceSettings, type Signals, type SimModel, settingsFor } from "./model";
import type { ScenarioRun, ValueSource } from "./montecarlo";
import { DEFAULT_RESPONSE, NO_VARIANT, type Pathogen, type Response, type Segment, type Variant } from "./scenario";

export type PlanId = "none" | "mitigate" | "suppress" | "custom" | "adaptive";
export type Overridable = "reporting" | "vaccine_acceptance" | "vaccine_capacity";
export type VaccineChoice = "none" | "6m" | "1y" | "exists" | "custom";
export type Shift = -1 | 0 | 1;

export interface SimSpec {
  iso: string | null;
  /** The two plain adjustments on the first step: younger/older, weaker/stronger healthcare. */
  simple: { age: Shift; care: Shift };
  place: {
    population?: number;
    median_age?: number;
    latitude?: number;
    icu_share_of_beds?: number;
    signals?: Partial<Signals>;
  };
  learned: Partial<Record<Overridable, number>>;
  pathogen: { preset: string | null; edits: Partial<Pathogen> };
  plan: PlanId | null;
  segments?: Segment[];
  vaccine: VaccineChoice | null;
  response: Partial<Omit<Response, "segments" | "vaccine" | "vaccine_day">> & { vaccine_day?: number };
  variant: Variant | null;
  years: 1 | 2 | 3;
}

export const EMPTY_SPEC = (): SimSpec => ({
  iso: null,
  simple: { age: 0, care: 0 },
  place: {},
  learned: {},
  pathogen: { preset: null, edits: {} },
  plan: null,
  vaccine: null,
  response: {},
  variant: null,
  years: 2,
});

export const isComplete = (s: SimSpec) => s.iso !== null && s.pathogen.preset !== null && s.plan !== null && s.vaccine !== null;

export const PLANS: { id: PlanId; label: string; note: string }[] = [
  { id: "none", label: "Carry on as normal", note: "No restrictions. People still get more careful as deaths rise." },
  { id: "mitigate", label: "Light measures", note: "Distancing, limits on gatherings, some closures from week 4." },
  { id: "suppress", label: "Lock down early, then ease", note: "A strict lockdown for 12 weeks from week 3, then lighter measures." },
  { id: "adaptive", label: "Lock down whenever hospitals fill up", note: "Strict measures switch on when hospitals reach 80% and off again at 40%." },
  { id: "custom", label: "Design your own", note: "Set up to three periods of restrictions yourself." },
];

export const VACCINES: { id: Exclude<VaccineChoice, "custom">; label: string }[] = [
  { id: "none", label: "No vaccine" },
  { id: "1y", label: "Ready in a year" },
  { id: "6m", label: "Ready in 6 months" },
  { id: "exists", label: "Already exists" },
];
const VACCINE_DAY: Record<Exclude<VaccineChoice, "none" | "custom">, number> = { "6m": 182, "1y": 365, exists: 0 };

export function planSegments(plan: PlanId, days: number, custom?: Segment[]): Segment[] {
  if (plan === "mitigate") return [{ start_day: 21, end_day: days, level: 45 }];
  if (plan === "suppress") return [{ start_day: 14, end_day: 98, level: 75 }, { start_day: 98, end_day: days, level: 40 }];
  if (plan === "custom") return custom ?? [{ start_day: 28, end_day: 140, level: 60 }];
  return [];
}

/** "Younger" / "Older" shift the median age; "Weaker" / "Stronger" healthcare scale its resources. */
const AGE_SHIFT = 8;
const CARE = {
  [-1]: { scale: 0.5, uhc: -15 },
  [1]: { scale: 1.75, uhc: 15 },
} as const;

function applySimple(model: SimModel, country: CountryProfile, simple: SimSpec["simple"], signals: Signals): Partial<Signals> & { median_age?: number } {
  const out: Partial<Signals> & { median_age?: number } = {};
  if (simple.age !== 0 && country.signals.median_age !== null) {
    out.median_age = Math.min(55, Math.max(15, country.signals.median_age + simple.age * AGE_SHIFT));
  }
  if (simple.care !== 0) {
    const c = CARE[simple.care];
    const median = (name: keyof Signals) => {
      const v = model.countries.map((x) => x.signals[name]).filter((x): x is number => x !== null).sort((a, b) => a - b);
      return v[Math.floor(v.length / 2)];
    };
    const base = (name: keyof Signals) => signals[name] ?? median(name);
    out.hospital_beds_per_thousand = base("hospital_beds_per_thousand") * c.scale;
    out.physicians_per_thousand = base("physicians_per_thousand") * c.scale;
    out.health_exp_per_capita = base("health_exp_per_capita") * (simple.care === 1 ? 2 : 0.5);
    out.uhc_index = Math.min(95, Math.max(20, base("uhc_index") + c.uhc));
  }
  return out;
}

export interface Resolved {
  country: CountryProfile;
  settings: PlaceSettings;
  learned: Record<LearnedName, Learned>;
  pathogen: Pathogen;
  basePathogen: Pathogen;
  response: Response;
  variant: Variant;
  days: number;
  run: ScenarioRun;
  edited: { place: string[]; pathogen: string[] };
}

/**
 * Everything the engine and the page need. Works on incomplete drafts too (missing choices fall
 * back to neutral placeholders) so the fine-tune panels can preview values before Run.
 */
export function resolve(model: SimModel, spec: SimSpec): Resolved {
  const country = (spec.iso && model.byIso.get(spec.iso)) || model.byIso.get("USA") || model.countries[0];
  const settings = settingsFor(country);
  const simple = applySimple(model, country, spec.simple, settings.signals);
  const { median_age: simpleAge, ...simpleSignals } = simple;
  if (spec.place.population !== undefined) settings.population = spec.place.population;
  if (spec.place.latitude !== undefined) settings.latitude = spec.place.latitude;
  if (spec.place.icu_share_of_beds !== undefined) settings.icu_share_of_beds = spec.place.icu_share_of_beds;
  settings.signals = { ...settings.signals, ...simpleSignals, ...spec.place.signals };
  const medianAge = spec.place.median_age ?? simpleAge;
  if (medianAge !== undefined) {
    const ages = ageStructureFor(model, medianAge);
    settings.age_shares = ages.shares;
    settings.age_means = ages.means;
    settings.signals = { ...settings.signals, median_age: medianAge, share_65_plus: ages.share65 };
  }

  const { place, learned } = buildPlace(model, country, settings);
  const sources = {
    transmission: learned.transmission.source as ValueSource,
    severity: learned.severity.source as ValueSource,
    awareness: learned.awareness.source as ValueSource,
    reporting: learned.reporting.source as ValueSource,
    vaccine_acceptance: learned.vaccine_acceptance.source as ValueSource,
    vaccine_capacity: learned.vaccine_capacity.source as ValueSource,
  };
  const overrides: Record<Overridable, "death_reporting" | "vaccine_acceptance" | "vaccine_capacity"> = {
    reporting: "death_reporting",
    vaccine_acceptance: "vaccine_acceptance",
    vaccine_capacity: "vaccine_capacity",
  };
  for (const [key, field] of Object.entries(overrides) as [Overridable, "death_reporting" | "vaccine_acceptance" | "vaccine_capacity"][]) {
    const v = spec.learned[key];
    if (v !== undefined) {
      place[field] = v;
      sources[key] = "user";
    }
  }

  const basePathogen = model.presets.find((p) => p.id === spec.pathogen.preset) ?? model.presets.find((p) => p.id === "covid_ancestral") ?? model.presets[0];
  const pathogen: Pathogen = { ...basePathogen, ...spec.pathogen.edits };
  const days = spec.years * 365;
  const vaccine = spec.vaccine ?? "none";
  const response: Response = {
    ...DEFAULT_RESPONSE,
    ...spec.response,
    adaptive: spec.plan === "adaptive",
    segments: planSegments(spec.plan ?? "none", days, spec.segments),
    vaccine: vaccine !== "none",
    vaccine_day: vaccine === "custom" ? (spec.response.vaccine_day ?? null) : vaccine === "none" ? null : VACCINE_DAY[vaccine],
  };
  const variant = spec.variant ?? NO_VARIANT;
  const run: ScenarioRun = { place, sources, pathogen, response, variant, constants: model.constants, uncertainty: model.uncertainty, days };
  return {
    country,
    settings,
    learned,
    pathogen,
    basePathogen,
    response,
    variant,
    days,
    run,
    edited: {
      place: [...Object.keys(spec.place.signals ?? {}), ...Object.keys(spec.place).filter((k) => k !== "signals")],
      pathogen: Object.keys(spec.pathogen.edits),
    },
  };
}

// --------------------------------------------------------------------------- URL encoding

/** JSON -> base64url. Infinity (a never-arriving vaccine, lifelong immunity) is kept as a string. */
export function encodeSpec(spec: SimSpec): string {
  const json = JSON.stringify(spec, (_k, v) => (v === Infinity ? "Infinity" : v));
  const bytes = new TextEncoder().encode(json);
  let binary = "";
  bytes.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function decodeSpec(text: string): SimSpec | null {
  try {
    const b64 = text.replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(b64 + "=".repeat((4 - (b64.length % 4)) % 4));
    const json = new TextDecoder().decode(Uint8Array.from(binary, (c) => c.charCodeAt(0)));
    const parsed = JSON.parse(json, (_k, v) => (v === "Infinity" ? Infinity : v)) as Partial<SimSpec>;
    const spec = { ...EMPTY_SPEC(), ...parsed } as SimSpec;
    return isComplete(spec) ? spec : null;
  } catch {
    return null;
  }
}
