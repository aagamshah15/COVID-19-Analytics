/**
 * The written scenario report: plain-language findings generated from the results, plus the
 * tables and the CSV a reader can take away. Every number here comes from the simulation.
 */
import { big, compact, pct } from "../format";
import type { EngineOutputs } from "./engine";
import { analogs, featureVector, type SimModel } from "./model";
import type { EnsembleResult, Summary, TornadoBar } from "./montecarlo";
import { bandSeverity } from "./scenario";
import type { Resolved, SimSpec } from "./spec";
import { LEVERS } from "./words";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const TRAINED = { r0: [2.5, 9], ifr: [0.001, 0.02] };

/** Three significant figures: "2.49 million", "243,000". Exact counts would claim false precision. */
const people = (n: number) => {
  const b = big(n >= 1e6 ? n : Number(n.toPrecision(3)));
  return b.unit ? `${b.value} ${b.unit}` : b.value;
};
const when = (day: number) => {
  const months = day / 30.4167;
  return months < 1.5 ? `${Math.round(day / 7)} weeks in` : `${months.toFixed(0)} months in`;
};

export interface Report {
  paragraphs: string[];
  warnings: string[];
  metrics: { label: string; median: string; range: string }[];
}

export function buildReport(
  model: SimModel,
  r: Resolved,
  summary: Summary,
  ensemble: EnsembleResult | null,
  tornado: { base: number; bars: TornadoBar[] } | null,
): Report {
  const p = r.pathogen;
  const place = r.run.place;
  const pop = place.population;
  const { ifr } = bandSeverity(p, place, model.constants);
  const localIfr = ifr.reduce((s, v, b) => s + v * place.age_shares[b], 0);
  const q = ensemble?.summary.quantiles;
  const capacity = ((place.beds_per_thousand * pop) / 1000) * place.bed_availability * (1 + r.response.surge);
  const range = (k: keyof Summary, f: (v: number) => string) => (q ? `${f(q[k][0])}–${f(q[k][4])}` : "…");

  const edits = r.edited.place.length + Object.keys(r.run.sources).filter((k) => r.run.sources[k as keyof typeof r.run.sources] === "user").length;
  const paragraphs = [
    `This scenario simulates ${p.name} (R0 ${p.r0.toFixed(2)}; ${pct(p.ifr, p.ifr < 0.01 ? 2 : 1)} of infections fatal at world-average ages, ${pct(localIfr, localIfr < 0.01 ? 2 : 1)} with this age structure) arriving in a place based on ${r.country.name}${edits ? ` with ${edits} setting${edits > 1 ? "s" : ""} changed` : ""}, in ${MONTHS[r.response.start_month - 1]}, over ${r.days / 365} year${r.days > 365 ? "s" : ""}.`,
    `In the median run, ${pct(summary.attack_rate)} of people are infected${summary.attack_rate > 1 ? " (counting reinfections)" : ""} and ${people(summary.deaths)} die, ${compact((summary.deaths / pop) * 1e6)} per million people.${q ? ` Across ${ensemble!.draws} runs with uncertain inputs, 90% end between ${compact(q.deaths[0])} and ${compact(q.deaths[4])} deaths.` : ""} If ${pct(place.death_reporting)} of deaths are reported, as the model estimates for ${r.country.name}, official counts would show about ${people(summary.reported_deaths)}.`,
    `Deaths peak about ${when(summary.peak_deaths_day)}. Hospital demand peaks at ${people(summary.peak_hospital)} patients, ${(summary.peak_hospital / Math.max(capacity, 1)).toFixed(1)} times the ${people(capacity)} beds available to the epidemic.${summary.days_over_capacity > 0 ? ` Hospitals are over capacity for ${summary.days_over_capacity} days, which raises the death rate of patients needing intensive care.` : " Hospitals stay within capacity."}`,
  ];
  if (ensemble) {
    const averted = ensemble.noResponse.deaths - summary.deaths;
    paragraphs.push(
      averted > 0
        ? `Compared with no restrictions and no vaccine, this response averts about ${people(averted)} deaths (${pct(averted / Math.max(ensemble.noResponse.deaths, 1))}). People's own caution as deaths rise is included in both.`
        : `This response averts no deaths compared with no restrictions and no vaccine.`,
    );
  }
  if (r.response.vaccine && summary.vaccinated > 0) {
    paragraphs.push(`By the end, ${people(summary.vaccinated)} people (${pct(summary.vaccinated / pop)}) have been vaccinated${r.response.vaccine_oldest_first ? ", oldest first" : ""}.`);
  }
  if (tornado && tornado.bars.length >= 2) {
    const name = (b: TornadoBar) => (LEVERS[b.key]?.name ?? b.label).toLowerCase();
    paragraphs.push(`The result is most sensitive to ${name(tornado.bars[0])} and ${name(tornado.bars[1])}: the inputs worth getting right first.`);
  }
  const near = analogs(model, featureVector(model, r.settings.signals), 3);
  paragraphs.push(`The real countries most like this place are ${near.nearest.map((n) => n.country.name).join(", ")}.`);

  const warnings: string[] = [];
  const outside = p.r0 < TRAINED.r0[0] || p.r0 > TRAINED.r0[1] || p.ifr < TRAINED.ifr[0] || p.ifr > TRAINED.ifr[1] || p.age_profile !== "steep";
  if (outside) warnings.push(`${p.name} lies outside the SARS-CoV-2 range the country models were trained on, so the country effects are an extrapolation.`);
  if (near.outOfRange) warnings.push("This combination of country characteristics is unlike any real country, so the learned country effects are an extrapolation.");
  if (r.basePathogen.kind === "hypothetical") warnings.push("The disease is hypothetical: its transmissibility is an assumption, not an observation.");
  warnings.push("A scenario, not a forecast: tested on data it never saw, the simulator didn't beat simple statistical baselines at predicting real death counts.");

  const metrics = [
    { label: "Deaths", median: compact(summary.deaths), range: range("deaths", compact) },
    { label: "Reported deaths", median: compact(summary.reported_deaths), range: range("reported_deaths", compact) },
    { label: "Share infected", median: pct(summary.attack_rate), range: range("attack_rate", (v) => pct(v)) },
    { label: "Peak hospital patients", median: compact(summary.peak_hospital), range: range("peak_hospital", compact) },
    { label: "Days over hospital capacity", median: `${summary.days_over_capacity}`, range: range("days_over_capacity", (v) => `${Math.round(v)}`) },
    { label: "People vaccinated", median: compact(summary.vaccinated), range: range("vaccinated", compact) },
  ];
  return { paragraphs, warnings, metrics };
}

/** Where each setting came from: the user, the data, a calibrated model or an assumption. */
export function settingsRows(model: SimModel, r: Resolved, spec: SimSpec): { label: string; value: string; source: string }[] {
  const src = (s: string) => (s === "user" ? "set by you" : s);
  return [
    { label: "Base country", value: r.country.name, source: "your choice" },
    { label: "Disease", value: r.pathogen.name, source: r.edited.pathogen.length ? `preset, ${r.edited.pathogen.length} setting(s) changed` : "preset" },
    { label: "Transmission multiplier", value: `×${r.learned.transmission.value.toFixed(2)}`, source: r.learned.transmission.source },
    { label: "Severity multiplier (60+)", value: `×${r.learned.severity.value.toFixed(2)}`, source: r.learned.severity.source },
    {
      label: "People pull back at",
      value: `${(model.constants.awareness_deaths_pm * r.learned.awareness.value).toFixed(1)} reported deaths/M/day`,
      source: r.learned.awareness.source,
    },
    { label: "Share of deaths reported", value: `${Math.round(r.run.place.death_reporting * 100)}%`, source: src(r.run.sources.reporting) },
    { label: "Vaccine acceptance", value: `${Math.round(r.run.place.vaccine_acceptance * 100)}%`, source: src(r.run.sources.vaccine_acceptance) },
    {
      label: "Lockdown effect at stringency 80",
      value: `${Math.round((1 - Math.exp(80 * model.constants.npi_coef * r.run.place.adherence)) * 100)}% less transmission`,
      source: "calibrated (all countries) × adherence",
    },
    { label: "ICU beds", value: `${Math.round(r.settings.icu_share_of_beds * 100)}% of beds`, source: spec.place.icu_share_of_beds === undefined ? "assumption" : "set by you" },
    { label: "Beds available to the epidemic", value: "50% of all beds", source: "assumption" },
  ];
}

/** Daily results as CSV: the median run plus the 5th, 50th and 95th percentiles across runs. */
export function toCsv(central: EngineOutputs, ensemble: EnsembleResult | null): string {
  const cols: [string, ArrayLike<number>][] = [
    ["infections", central.infections],
    ["hospital_patients", central.hospital],
    ["icu_patients", central.icu],
    ["deaths", central.deaths],
    ["reported_deaths", central.reported_deaths],
    ["effective_r", central.rt],
    ["stringency", central.stringency],
    ["vaccinated_total", central.vaccinated],
  ];
  if (ensemble) {
    for (const [name, key] of [
      ["deaths", "deaths"],
      ["hospital_patients", "hospital"],
      ["infections", "infections"],
    ] as const) {
      const b = ensemble.bands.daily[key];
      cols.push([`${name}_p05`, b[0]], [`${name}_p50`, b[2]], [`${name}_p95`, b[4]]);
    }
  }
  const rows = [["day", ...cols.map(([n]) => n)].join(",")];
  for (let d = 0; d < central.deaths.length; d++) rows.push([d + 1, ...cols.map(([, v]) => Number(v[d].toPrecision(6)))].join(","));
  return rows.join("\n") + "\n";
}
