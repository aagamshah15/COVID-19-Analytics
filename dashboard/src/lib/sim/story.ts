/**
 * The plain-language story of a run: what was simulated, the headline sentence, the four big
 * numbers and the biggest levers. The results page and the PDF report share it, so both say the same.
 */
import { compact } from "../format";
import type { EnsembleResult, Summary, TornadoBar } from "./montecarlo";
import { PLANS, type Resolved, type SimSpec, VACCINES } from "./spec";
import { aboutPeople, diseaseLabel, LEVERS, rounded, shareInWords, weeksInWords } from "./words";

/** A stretch of text, optionally bold. */
export interface Run {
  text: string;
  bold?: boolean;
}

export const placeLabel = (r: Resolved, s: SimSpec) =>
  r.edited.place.length || s.simple.age || s.simple.care ? `a place like ${r.country.name}` : r.country.name;

/** The choices behind a run: place, disease, restrictions, vaccine. */
export function scenarioParts(r: Resolved, s: SimSpec): string[] {
  return [
    placeLabel(r, s),
    `${diseaseLabel(s.pathogen.preset)}${r.edited.pathogen.length ? " (adjusted)" : ""}`,
    PLANS.find((p) => p.id === s.plan)?.label ?? "Custom restrictions",
    s.vaccine === "custom" ? "Vaccine on a custom date" : (VACCINES.find((v) => v.id === s.vaccine)?.label ?? ""),
  ];
}

export const didSomething = (s: SimSpec) => s.plan !== "none" || s.vaccine !== "none";

/** "Over 2 years, about 1 in 4 people would catch it and about 380,000 would die. …" */
export function headline(s: SimSpec, days: number, summary: Summary, noAction: Summary): Run[] {
  const years = days / 365;
  const saved = noAction.deaths - summary.deaths;
  const runs: Run[] = [
    { text: `Over ${years} year${years > 1 ? "s" : ""}, ` },
    { text: shareInWords(summary.attack_rate), bold: true },
    { text: " would catch it and " },
    { text: aboutPeople(summary.deaths), bold: true },
    { text: " would die. " },
  ];
  if (summary.days_over_capacity > 0) {
    runs.push({ text: "Hospitals would be overwhelmed for " }, { text: weeksInWords(summary.days_over_capacity), bold: true }, { text: "." });
  } else {
    runs.push({ text: "Hospitals would cope." });
  }
  if (didSomething(s) && saved > Math.max(10, summary.deaths * 0.02)) {
    runs.push({ text: " The response would save " }, { text: aboutPeople(saved), bold: true }, { text: " lives compared with doing nothing." });
  }
  return runs;
}

export interface Figure {
  value: string;
  unit: string;
  label: string;
  notes: string[];
}

/** The four big numbers under the headline. */
export function figures(s: SimSpec, summary: Summary, noAction: Summary, ensemble: EnsembleResult): Figure[] {
  const q = ensemble.summary.quantiles.deaths;
  const deaths = rounded(summary.deaths);
  const saved = rounded(Math.max(noAction.deaths - summary.deaths, 0));
  const acted = didSomething(s);
  const deathNotes = [`likely ${compact(q[0])} to ${compact(q[4])}`];
  if (q[4] > 20 * Math.max(q[0], 1)) deathNotes.push("A wide range: small differences decide whether this outbreak takes off at all.");
  return [
    { value: deaths.value, unit: deaths.unit, label: "deaths", notes: deathNotes },
    {
      value: `${Math.min(100, Math.round(summary.attack_rate * 100))}%`,
      unit: "",
      label: `of people infected${summary.attack_rate > 1 ? " (some more than once)" : ""}`,
      notes: [],
    },
    {
      value: `${summary.days_over_capacity > 0 ? Math.max(1, Math.round(summary.days_over_capacity / 7)) : 0}`,
      unit: "weeks",
      label: "hospitals overwhelmed",
      notes: [],
    },
    acted
      ? { value: saved.value, unit: saved.unit, label: "lives saved by the response", notes: [] }
      : { value: "–", unit: "", label: "no response to compare", notes: [] },
  ];
}

export interface Lever {
  name: string;
  /** The two test cases, fewer deaths first. */
  cases: { text: string; deaths: number }[];
}

/** The inputs that move deaths the most, in plain words (see montecarlo.sensitivity). */
export function levers(tornado: { bars: TornadoBar[] } | null, n = 3): Lever[] {
  return (tornado?.bars ?? []).slice(0, n).map((b) => {
    const words = LEVERS[b.key] ?? { name: b.label, low: b.lowLabel, high: b.highLabel };
    const cases = [
      { text: words.low, deaths: b.low },
      { text: words.high, deaths: b.high },
    ].sort((x, y) => x.deaths - y.deaths);
    return { name: words.name, cases };
  });
}

export const leverSentence = (l: Lever) => `If ${l.cases[0].text}: ${compact(l.cases[0].deaths)} deaths. If ${l.cases[1].text}: ${compact(l.cases[1].deaths)}.`;

/** Daily values summed (flows) or sampled at the week's end (stocks) into weeks. */
export function weekly(values: ArrayLike<number>, flow: boolean): number[] {
  const out: number[] = [];
  for (let w = 0; w * 7 < values.length; w++) {
    const end = Math.min(values.length, w * 7 + 7);
    let s = 0;
    for (let d = w * 7; d < end; d++) s += values[d];
    out.push(flow ? s : values[end - 1]);
  }
  return out;
}

export const CAVEAT =
  "This is a “what if” simulation, not a prediction. It's built on real data from 2020–2023, but outbreaks swing on small differences, so read the numbers as rough sizes, not exact counts.";
