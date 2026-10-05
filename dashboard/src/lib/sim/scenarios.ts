/**
 * Ready-made scenarios: complete combinations of place, disease and response that show what the
 * simulator can do in one click. Each one is an ordinary spec, so it can be changed afterwards.
 */
import { EMPTY_SPEC, type SimSpec } from "./spec";

export interface ReadyScenario {
  id: string;
  title: string;
  story: string;
  tags: string[];
  spec: SimSpec;
}

const spec = (patch: Partial<SimSpec>): SimSpec => ({ ...EMPTY_SPEC(), ...patch });

export const READY: ReadyScenario[] = [
  {
    id: "ageing",
    title: "COVID-19 hits an ageing, wealthy country",
    story: "Italy's population is among the oldest in the world. What does an early lockdown buy before a vaccine arrives?",
    tags: ["Italy", "Like COVID-19 (2020)", "Lock down early"],
    spec: spec({ iso: "ITA", pathogen: { preset: "covid_ancestral", edits: {} }, plan: "suppress", vaccine: "1y", response: { start_month: 2 } }),
  },
  {
    id: "measles",
    title: "Measles returns where vaccination has slipped",
    story: "Measles is the most contagious disease we know. Here, only half of adults take the vaccine.",
    tags: ["Nigeria", "Like measles", "Vaccine exists, low uptake"],
    spec: spec({ iso: "NGA", pathogen: { preset: "measles", edits: {} }, plan: "none", vaccine: "exists", learned: { vaccine_acceptance: 0.5 }, years: 1 }),
  },
  {
    id: "flu1918",
    title: "A 1918-style flu in a young, crowded country",
    story: "The 1918 flu killed young adults as well as the old. Bangladesh is young and one of the most densely populated countries on Earth.",
    tags: ["Bangladesh", "Like the 1918 flu", "Light measures"],
    spec: spec({ iso: "BGD", pathogen: { preset: "flu_1918", edits: {} }, plan: "mitigate", vaccine: "none" }),
  },
  {
    id: "lockdown",
    title: "Lockdown or carry on? The same outbreak, two choices",
    story: "The United States meets a COVID-like virus with no vaccine in sight. A strict early lockdown, against doing nothing at all.",
    tags: ["United States", "Like COVID-19 (2020)", "Lock down early, no vaccine"],
    spec: spec({ iso: "USA", pathogen: { preset: "covid_ancestral", edits: {} }, plan: "suppress", vaccine: "none" }),
  },
  {
    id: "mers",
    title: "A deadly virus that barely spreads",
    story: "A third of known MERS cases died, yet it never became a pandemic. Why? Each case infects fewer than one other person.",
    tags: ["Saudi Arabia", "Like MERS", "No restrictions"],
    spec: spec({ iso: "SAU", pathogen: { preset: "mers", edits: {} }, plan: "none", vaccine: "none", years: 1 }),
  },
  {
    id: "diseasex",
    title: "Disease X arrives before any vaccine",
    story: "A new virus nobody has seen. Brazil locks down only when hospitals fill up, while a vaccine is a year away.",
    tags: ["Brazil", "A new disease", "Lock down when hospitals fill"],
    spec: spec({ iso: "BRA", pathogen: { preset: "disease_x", edits: {} }, plan: "adaptive", vaccine: "1y" }),
  },
];
