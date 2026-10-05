/** Plain-language helpers: everyday descriptions of diseases, levels and results. */
import type { Pathogen } from "./scenario";

/** Disease cards on the second step, in the order shown. The rest sit under "More diseases". */
export const DISEASE_CARDS: { id: string; label: string; blurb: string }[] = [
  { id: "seasonal_flu", label: "Like seasonal flu", blurb: "Spreads slowly; dangerous mainly for the very old." },
  { id: "covid_ancestral", label: "Like COVID-19 (2020)", blurb: "Spreads fast; far deadlier for older people." },
  { id: "covid_omicron", label: "Like the Omicron variant", blurb: "Spreads extremely fast but is milder." },
  { id: "measles", label: "Like measles", blurb: "The most contagious disease known." },
  { id: "flu_1918", label: "Like the 1918 flu", blurb: "Killed young adults as well as the old." },
  { id: "sars_2003", label: "Like SARS (2003)", blurb: "Deadly, but spread less easily." },
  { id: "disease_x", label: "Something new", blurb: "A blank slate to shape yourself." },
];
export const MORE_DISEASES: { id: string; label: string }[] = [
  { id: "covid_delta", label: "Like the Delta variant" },
  { id: "flu_2009", label: "Like the 2009 flu" },
  { id: "flu_1957", label: "Like the 1957 flu" },
  { id: "flu_1968", label: "Like the 1968 flu" },
  { id: "mers", label: "Like MERS" },
  { id: "h5n1_hypothetical", label: "Like bird flu, if it spread (hypothetical)" },
  { id: "smallpox", label: "Like smallpox" },
];
export const diseaseLabel = (id: string | null) =>
  [...DISEASE_CARDS, ...MORE_DISEASES].find((d) => d.id === id)?.label ?? "A disease";

/** Plain levels for the two disease dials. Choosing one sets R0 or the fatality rate. */
export const CONTAGIOUS = [
  { label: "Low", r0: 1.3, note: "like seasonal flu" },
  { label: "Medium", r0: 2.5, note: "like COVID-19 in 2020" },
  { label: "High", r0: 5, note: "like the Delta variant" },
  { label: "Very high", r0: 12, note: "like measles" },
];
export const DEADLY = [
  { label: "Mild", ifr: 0.0005, note: "about 1 in 2,000 infections" },
  { label: "Serious", ifr: 0.005, note: "about 1 in 200" },
  { label: "Severe", ifr: 0.03, note: "about 1 in 30" },
  { label: "Catastrophic", ifr: 0.15, note: "about 1 in 7" },
];
/** Index of the level nearest to a value, on a log scale. */
export function nearestLevel(levels: { r0?: number; ifr?: number }[], value: number, key: "r0" | "ifr"): number {
  let best = 0;
  levels.forEach((l, i) => {
    if (Math.abs(Math.log(l[key]! / value)) < Math.abs(Math.log(levels[best][key]! / value))) best = i;
  });
  return best;
}

/** "about 1 in 4 people", "about 7 in 10 people", "almost everyone, some more than once". */
export function shareInWords(share: number): string {
  if (share >= 1) return "everyone, on average more than once";
  if (share >= 0.95) return "almost everyone";
  if (share >= 0.45 && share < 0.55) return "about half of all people";
  if (share >= 0.45) return `about ${Math.round(share * 10)} in 10 people`;
  if (share >= 0.005) return `about 1 in ${Math.max(2, Math.round(1 / share))} people`;
  if (share >= 0.0001) return `about 1 in ${Math.round(1 / share).toLocaleString("en-US")} people`;
  return "almost no one";
}

/** "about 1.2 million", "about 4,300", "fewer than 10". */
export function aboutPeople(n: number): string {
  if (n < 10) return "fewer than 10";
  const b = rounded(n);
  return `about ${b.value}${b.unit ? ` ${b.unit}` : ""}`;
}

export function weeksInWords(days: number): string {
  if (days <= 0) return "";
  if (days < 10) return `about ${days} days`;
  const weeks = Math.round(days / 7);
  return weeks >= 9 ? `about ${Math.round(days / 30.4)} months` : `about ${weeks} weeks`;
}

export const pathogenSummary = (p: Pathogen) =>
  `${CONTAGIOUS[nearestLevel(CONTAGIOUS, p.r0, "r0")].label.toLowerCase()} spread, ${DEADLY[nearestLevel(DEADLY, p.ifr, "ifr")].label.toLowerCase()}`;

/** A count rounded to two significant figures for display: 377,069 -> "380,000"; 1.41e6 -> "1.4 million". */
export function rounded(n: number): { value: string; unit: string } {
  if (n < 100) return { value: `${Math.round(n)}`, unit: "" };
  if (n >= 1e9) return { value: (n / 1e9).toPrecision(2), unit: "billion" };
  if (n >= 1e6) return { value: (n / 1e6).toPrecision(2), unit: "million" };
  return { value: Number(n.toPrecision(2)).toLocaleString("en-US"), unit: "" };
}

/** Plain names for the sensitivity levers, and what the low and high test cases mean (see montecarlo.sensitivity). */
export const LEVERS: Record<string, { name: string; low: string; high: string }> = {
  r0: { name: "How contagious it is", low: "it were 20% less contagious", high: "it were 20% more contagious" },
  ifr: { name: "How deadly it is", low: "it were a third less deadly", high: "it were 50% deadlier" },
  transmission: { name: "How easily it spreads here", low: "it spread less easily here", high: "it spread more easily here" },
  severity: { name: "How badly older people are hit", low: "it were milder for older people", high: "it were worse for older people" },
  npi: { name: "How well restrictions work", low: "restrictions worked half as well", high: "restrictions worked 50% better" },
  awareness: { name: "How careful people are", low: "people were less careful", high: "people were more careful" },
  beds: { name: "Hospital beds", low: "there were half as many beds", high: "there were twice as many beds" },
  vaccine_day: { name: "When the vaccine arrives", low: "the vaccine came 3 months later", high: "it came 3 months sooner" },
  acceptance: { name: "How many take the vaccine", low: "15% fewer people took it", high: "15% more people took it" },
  stringency: { name: "How strict the rules are", low: "the rules were looser", high: "the rules were stricter" },
};
