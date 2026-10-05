/**
 * The scenario report as a PDF, drawn directly from the results: story, charts, levers, the full
 * written report, the settings and how the model works. Vector charts, standard fonts, always the
 * light theme. The page loads this module (and jsPDF) only when someone asks for the PDF.
 */
import { scaleLinear } from "d3-scale";
import { jsPDF } from "jspdf";
import { compact } from "../format";
import type { EngineOutputs } from "./engine";
import type { SimModel } from "./model";
import type { EnsembleResult, Summary, TornadoBar } from "./montecarlo";
import { buildReport, settingsRows } from "./report";
import type { Resolved, SimSpec } from "./spec";
import { CAVEAT, didSomething, figures, headline, leverSentence, levers, type Run, scenarioParts, weekly } from "./story";
import { LEVERS } from "./words";

export interface PdfInput {
  model: SimModel;
  spec: SimSpec;
  r: Resolved;
  central: EngineOutputs;
  noAction: EngineOutputs;
  summary: Summary;
  noActionSummary: Summary;
  ensemble: EnsembleResult;
  tornado: { base: number; bars: TornadoBar[] } | null;
  capacity: number;
  link: string;
  date: Date;
}

// --- page geometry (mm) and the light theme's tokens ----------------------------------------------
const PAGE = { w: 210, h: 297 };
const M = { x: 18, top: 18, bottom: 20 };
const CW = PAGE.w - 2 * M.x;
const C = {
  ink: "#172422",
  ink2: "#4e5c59",
  muted: "#6f7b78",
  faint: "#a9b3b0",
  hair: "#dde3e1",
  hair2: "#c9d1ce",
  deaths: "#b3303e",
  hosp: "#b87a00",
  white: "#ffffff",
};
const PT = 0.3528; // mm per point

const rgb = (hex: string): [number, number, number] => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number];
/** `hex` laid over white at `alpha`: an opaque colour, so nothing depends on PDF transparency. */
const tint = (hex: string, alpha: number) =>
  `#${rgb(hex)
    .map((v) => Math.round(255 - (255 - v) * alpha).toString(16).padStart(2, "0"))
    .join("")}`;

/** The standard PDF fonts draw Latin-1 plus WinAnsi's dashes, quotes, bullet and ellipsis; map the rest. */
const REPLACE: Record<string, string> = {
  "\u2212": "-",
  "\u2248": "~",
  "\u2192": "->",
  "\u2190": "<-",
  "\u2191": "",
  "\u2264": "<=",
  "\u2265": ">=",
  "\u00a0": " ",
  "\u202f": " ",
  "\u2009": " ",
};
const DRAWABLE = /[^\x20-\x7e¡-ÿ–—‘’“”•…]/g;
export const clean = (s: string) => s.replace(DRAWABLE, (ch) => REPLACE[ch] ?? "");

class Writer {
  y = M.top;
  constructor(readonly doc: jsPDF) {}

  font(size: number, style: "normal" | "bold" = "normal", color = C.ink) {
    this.doc.setFont("helvetica", style);
    this.doc.setFontSize(size);
    this.doc.setTextColor(...rgb(color));
  }
  lineHeight(size: number, leading = 1.38) {
    return size * PT * leading;
  }
  /** Start a new page if `h` mm won't fit. */
  ensure(h: number) {
    if (this.y + h > PAGE.h - M.bottom) {
      this.doc.addPage();
      this.y = M.top;
    }
  }
  gap(h: number) {
    this.y += h;
  }
  text(s: string, opts: { size?: number; style?: "normal" | "bold"; color?: string; x?: number; width?: number; leading?: number } = {}) {
    const { size = 9.5, style = "normal", color = C.ink, x = M.x, width = CW, leading = 1.38 } = opts;
    this.font(size, style, color);
    const lh = this.lineHeight(size, leading);
    for (const line of this.doc.splitTextToSize(clean(s), width) as string[]) {
      this.ensure(lh);
      this.doc.text(line, x, this.y, { baseline: "top" });
      this.y += lh;
    }
  }
  /** A paragraph with bold stretches, wrapped word by word. */
  rich(runs: Run[], size: number, width = CW) {
    const lh = this.lineHeight(size, 1.32);
    const words = runs.flatMap((r) =>
      clean(r.text)
        .split(/(\s+)/)
        .filter(Boolean)
        .map((w) => ({ w, bold: !!r.bold })),
    );
    let cx = 0;
    this.ensure(lh);
    for (const { w, bold } of words) {
      this.font(size, bold ? "bold" : "normal", C.ink);
      const space = /^\s+$/.test(w);
      const ww = this.doc.getTextWidth(space ? " " : w);
      if (space) {
        if (cx > 0) cx += ww;
        continue;
      }
      if (cx + ww > width && cx > 0) {
        this.y += lh;
        this.ensure(lh);
        cx = 0;
      }
      this.doc.text(w, M.x + cx, this.y, { baseline: "top" });
      cx += ww;
    }
    this.y += lh;
  }
  heading(s: string, sub?: string) {
    this.ensure(18);
    this.text(s, { size: 12.5, style: "bold" });
    if (sub) {
      this.gap(0.6);
      this.text(sub, { size: 8.5, color: C.ink2 });
    }
    this.gap(2.5);
  }
  rule(color = C.hair, y = this.y) {
    this.doc.setDrawColor(...rgb(color));
    this.doc.setLineWidth(0.25);
    this.doc.setLineDashPattern([], 0);
    this.doc.line(M.x, y, M.x + CW, y);
  }
}

// --- drawing helpers ----------------------------------------------------------------------------------
function polyline(doc: jsPDF, pts: [number, number][], style: "S" | "F", closed = false) {
  if (pts.length < 2) return;
  const deltas = pts.slice(1).map(([x, y], i) => [x - pts[i][0], y - pts[i][1]]);
  doc.lines(deltas, pts[0][0], pts[0][1], [1, 1], style, closed);
}
function stroke(doc: jsPDF, color: string, width: number, dash: number[] = []) {
  doc.setDrawColor(...rgb(color));
  doc.setLineWidth(width);
  doc.setLineDashPattern(dash, 0);
}

interface Series {
  title: string;
  note: string;
  central: number[];
  fan: number[][] | null;
  compare: number[] | null;
  capacity: number | null;
  policy: number[];
  color: string;
}

/** A weekly line chart: 90% and 50% bands, the no-response path, a capacity rule and the restrictions strip. */
function lineChart(w: Writer, s: Series, days: number) {
  const doc = w.doc;
  const plotH = 46;
  w.ensure(14 + plotH + 22);
  w.text(s.title, { size: 10.5, style: "bold" });
  w.gap(0.5);
  w.text(s.note, { size: 8, color: C.ink2 });
  w.gap(2);

  const n = s.central.length;
  const maxCentral = Math.max(...s.central);
  const vmax = Math.max(
    1e-9,
    maxCentral,
    ...(s.fan ? s.fan[4] : []),
    ...(s.compare ?? []),
    s.capacity !== null && s.capacity < 4 * maxCentral ? s.capacity : 0,
  );
  const yMax = scaleLinear().domain([0, vmax]).nice(4).domain()[1];
  const showCapacity = s.capacity !== null && s.capacity <= yMax;

  // Legend
  const items: { label: string; draw: (x: number, y: number) => void }[] = [
    { label: "Most likely path", draw: (x, y) => (stroke(doc, s.color, 0.6), doc.line(x, y, x + 6, y)) },
  ];
  if (s.fan) {
    items.push({
      label: "9 in 10 runs",
      draw: (x, y) => {
        doc.setFillColor(...rgb(tint(s.color, 0.2)));
        doc.rect(x, y - 1.3, 6, 2.6, "F");
      },
    });
  }
  if (s.compare) items.push({ label: "If nothing were done", draw: (x, y) => (stroke(doc, C.muted, 0.35, [1.2, 0.8]), doc.line(x, y, x + 6, y)) });
  if (showCapacity) items.push({ label: "Hospital beds", draw: (x, y) => (stroke(doc, C.ink2, 0.3, [1.6, 1]), doc.line(x, y, x + 6, y)) });
  items.push({
    label: "Restrictions in place (darker = stricter)",
    draw: (x, y) => {
      doc.setFillColor(...rgb(tint(C.ink, 0.45)));
      doc.rect(x, y - 0.9, 6, 1.8, "F");
    },
  });
  w.font(7.5, "normal", C.ink2);
  let lx = M.x;
  for (const it of items) {
    const width = 8 + doc.getTextWidth(it.label) + 5;
    if (lx + width > M.x + CW) {
      lx = M.x;
      w.y += 4;
    }
    it.draw(lx, w.y + 1.4);
    w.font(7.5, "normal", C.ink2);
    doc.text(it.label, lx + 8, w.y, { baseline: "top" });
    lx += width;
  }
  w.y += 6;

  // Scales
  const yLabelW = 11;
  const x0 = M.x + yLabelW;
  const x1 = M.x + CW;
  const top = w.y;
  const bottom = top + plotH;
  const y = scaleLinear().domain([0, yMax]).range([bottom, top]);
  const x = scaleLinear()
    .domain([0, n - 1])
    .range([x0, x1]);
  const pts = (v: number[]) => v.map((value, i) => [x(i), y(Math.min(value, y.domain()[1]))] as [number, number]);

  // Bands, then gridlines over them, then lines
  if (s.fan) {
    for (const [lo, hi, alpha] of [
      [0, 4, 0.14],
      [1, 3, 0.28],
    ] as const) {
      doc.setFillColor(...rgb(tint(s.color, alpha)));
      polyline(doc, [...pts(s.fan[lo]), ...pts(s.fan[hi]).reverse()], "F", true);
    }
  }
  w.font(7, "normal", C.muted);
  for (const t of y.ticks(4)) {
    if (t <= 0) continue;
    stroke(doc, C.hair, 0.2);
    doc.line(x0, y(t), x1, y(t));
    doc.text(compact(t), x0 - 1.5, y(t), { baseline: "middle", align: "right" });
  }
  if (s.compare) {
    stroke(doc, C.muted, 0.35, [1.2, 0.8]);
    polyline(doc, pts(s.compare), "S");
  }
  if (showCapacity && s.capacity !== null) {
    stroke(doc, C.ink2, 0.3, [1.6, 1]);
    doc.line(x0, y(s.capacity), x1, y(s.capacity));
  }
  stroke(doc, s.color, 0.6);
  doc.setLineJoin("round");
  polyline(doc, pts(s.central), "S");
  stroke(doc, C.muted, 0.25);
  doc.line(x0, bottom, x1, bottom);

  // Restrictions strip
  const stripY = bottom + 1.4;
  const cell = (x1 - x0) / n;
  s.policy.forEach((p, i) => {
    if (p <= 0) return;
    doc.setFillColor(...rgb(tint(C.ink, 0.06 + (p / 100) * 0.5)));
    doc.rect(x0 + i * cell, stripY, cell + 0.05, 2, "F");
  });

  // Time axis
  w.font(7, "normal", C.muted);
  const every = days <= 200 ? 30.4 : days <= 450 ? 91.25 : 182.5;
  for (let d = 0; d <= days; d += every) {
    const months = Math.round(d / 30.4167);
    const label = months === 0 ? "start" : months % 12 === 0 ? `${months / 12} yr` : `${months} mo`;
    const tx = x0 + (d / 7 / Math.max(n - 1, 1)) * (x1 - x0);
    if (tx > x1 + 0.1) break;
    stroke(doc, C.muted, 0.2);
    doc.line(tx, stripY + 2.6, tx, stripY + 3.8);
    doc.text(label, tx, stripY + 4.6, { baseline: "top", align: d === 0 ? "left" : tx > x1 - 4 ? "right" : "center" });
  }
  w.y = stripY + 10;
}

/** Each age group's share of people against its share of deaths. */
function ageBars(w: Writer, shares: number[], deathsByAge: ArrayLike<number>) {
  const doc = w.doc;
  const total = Array.from(deathsByAge).reduce((a, b) => a + b, 0) || 1;
  const deathShares = Array.from(deathsByAge, (d) => d / total);
  const max = Math.max(...shares, ...deathShares, 1e-9);
  const labelW = 14;
  const barW = 70;
  w.ensure(8 + 5 * 8.4);
  w.font(7.5, "normal", C.ink2);
  doc.setFillColor(...rgb(C.faint));
  doc.rect(M.x, w.y + 0.4, 2.6, 2.6, "F");
  doc.text("Share of people", M.x + 4, w.y, { baseline: "top" });
  doc.setFillColor(...rgb(C.deaths));
  doc.rect(M.x + 30, w.y + 0.4, 2.6, 2.6, "F");
  doc.text("Share of deaths", M.x + 34, w.y, { baseline: "top" });
  w.y += 6;
  ["0-19", "20-39", "40-59", "60-79", "80+"].forEach((band, i) => {
    w.font(8, "normal", C.ink);
    doc.text(band, M.x, w.y + 2.6, { baseline: "middle" });
    for (const [k, v, color] of [
      [0, shares[i], C.faint],
      [1, deathShares[i], C.deaths],
    ] as const) {
      const by = w.y + k * 3.1;
      const bw = Math.max((v / max) * barW, 0.4);
      doc.setFillColor(...rgb(color));
      doc.rect(M.x + labelW, by, bw, 2.5, "F");
      w.font(7, "normal", C.ink2);
      doc.text(`${Math.round(v * 100)}%`, M.x + labelW + bw + 1.5, by + 1.25, { baseline: "middle" });
    }
    w.y += 8.4;
  });
}

/** Total deaths when each input is pushed to a plausible low and high value, one at a time. */
function tornadoChart(w: Writer, t: { base: number; bars: TornadoBar[] }) {
  const doc = w.doc;
  const labelW = 62;
  const x0 = M.x + labelW;
  const x1 = M.x + CW - 16;
  const lo = Math.min(t.base, ...t.bars.map((b) => Math.min(b.low, b.high)));
  const hi = Math.max(t.base, ...t.bars.map((b) => Math.max(b.low, b.high)));
  const x = scaleLinear().domain([lo, hi]).range([x0 + 12, x1 - 12]);
  const rowH = 5.6;
  w.ensure(t.bars.length * rowH + 10);
  const top = w.y;
  for (const b of t.bars) {
    w.font(8, "normal", C.ink);
    doc.text(clean(LEVERS[b.key]?.name ?? b.label), M.x, w.y + rowH / 2, { baseline: "middle" });
    const a = x(Math.min(b.low, b.high));
    const z = x(Math.max(b.low, b.high));
    doc.setFillColor(...rgb(C.deaths));
    doc.rect(a, w.y + 1.4, Math.max(z - a, 0.4), rowH - 2.8, "F");
    w.font(7, "normal", C.ink2);
    doc.text(compact(Math.min(b.low, b.high)), a - 1.2, w.y + rowH / 2, { baseline: "middle", align: "right" });
    doc.text(compact(Math.max(b.low, b.high)), z + 1.2, w.y + rowH / 2, { baseline: "middle" });
    w.y += rowH;
  }
  stroke(doc, C.ink, 0.3);
  doc.line(x(t.base), top - 1, x(t.base), w.y + 1);
  w.font(7, "normal", C.ink2);
  doc.text(`${compact(t.base)} deaths in this scenario`, x(t.base), w.y + 2, { baseline: "top", align: "center" });
  w.y += 7;
}

interface Column {
  label: string;
  width: number;
  align?: "left" | "right";
  muted?: boolean;
}

function table(w: Writer, title: string, columns: Column[], rows: string[][], bold?: (i: number) => boolean) {
  const doc = w.doc;
  const pad = 1.6;
  const lh = w.lineHeight(8.3, 1.3);
  w.ensure(16);
  w.text(title, { size: 10, style: "bold" });
  w.gap(1.5);
  const header = () => {
    w.font(7.5, "normal", C.muted);
    let cx = M.x;
    for (const c of columns) {
      doc.text(c.label, c.align === "right" ? cx + c.width - pad : cx, w.y, { baseline: "top", align: c.align ?? "left" });
      cx += c.width;
    }
    w.y += 4.2;
    w.rule(C.hair2);
  };
  header();
  rows.forEach((row, i) => {
    w.font(8.3, bold?.(i) ? "bold" : "normal", C.ink);
    const cells = row.map((cell, k) => doc.splitTextToSize(clean(cell), columns[k].width - pad * 2) as string[]);
    const h = Math.max(...cells.map((c) => c.length)) * lh + 2.6;
    if (w.y + h > PAGE.h - M.bottom) {
      doc.addPage();
      w.y = M.top;
      header();
      w.font(8.3, bold?.(i) ? "bold" : "normal", C.ink);
    }
    let cx = M.x;
    cells.forEach((lines, k) => {
      const c = columns[k];
      doc.setTextColor(...rgb(c.muted ? C.ink2 : C.ink));
      lines.forEach((line, j) => doc.text(line, c.align === "right" ? cx + c.width - pad : cx, w.y + 1.3 + j * lh, { baseline: "top", align: c.align ?? "left" }));
      cx += c.width;
    });
    w.y += h;
    w.rule();
  });
  w.gap(5);
}

function bullets(w: Writer, items: string[], size = 9, color = C.ink) {
  for (const item of items) {
    w.ensure(w.lineHeight(size));
    w.font(size, "normal", color);
    w.doc.text("•", M.x + 1, w.y, { baseline: "top" });
    w.text(item, { size, color, x: M.x + 5, width: CW - 5 });
    w.gap(1);
  }
}

export function pdfFilename(input: PdfInput): string {
  const slug = (s: string) =>
    s
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
  return `pandemic-scenario-${slug(input.r.country.name)}-${slug(input.spec.pathogen.preset ?? "disease")}.pdf`;
}

export function buildPdf(input: PdfInput): jsPDF {
  const { model, spec, r, central, noAction, summary, noActionSummary, ensemble, tornado, capacity } = input;
  const doc = new jsPDF({ unit: "mm", format: "a4", compress: true });
  const parts = scenarioParts(r, spec);
  doc.setProperties({ title: `Pandemic scenario report: ${parts.join(", ")}`, subject: "Pandemic simulator scenario report", creator: "COVID-19 Analytics pandemic simulator" });
  const w = new Writer(doc);
  const date = input.date.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

  // --- page 1: the story ------------------------------------------------------------------------
  w.text("COVID-19 ANALYTICS  ·  PANDEMIC SIMULATOR", { size: 7.5, style: "bold", color: C.muted });
  w.gap(2);
  w.text("Pandemic scenario report", { size: 19, style: "bold", leading: 1.2 });
  w.gap(1.5);
  w.text(parts.join("  ·  "), { size: 10, color: C.ink2 });
  w.gap(0.5);
  w.text(`Simulated over ${r.days / 365} year${r.days > 365 ? "s" : ""} with ${ensemble.draws} runs of uncertain inputs  ·  ${date}`, { size: 8, color: C.muted });
  w.gap(4);
  w.rule();
  w.gap(5);
  w.rich(headline(spec, r.days, summary, noActionSummary), 13);
  w.gap(5);

  // The four big numbers
  const figs = figures(spec, summary, noActionSummary, ensemble);
  const colW = CW / figs.length;
  const figTop = w.y;
  let figBottom = figTop;
  figs.forEach((f, i) => {
    const fx = M.x + i * colW;
    let fy = figTop;
    w.font(20, "bold", C.ink);
    doc.text(clean(f.value), fx, fy, { baseline: "top" });
    if (f.unit) {
      const vw = doc.getTextWidth(clean(f.value));
      w.font(9.5, "normal", C.ink2);
      doc.text(f.unit, fx + vw + 1.2, fy + 3.2, { baseline: "top" });
    }
    fy += 9;
    w.font(8.5, "normal", C.ink2);
    for (const line of doc.splitTextToSize(f.label, colW - 4) as string[]) {
      doc.text(line, fx, fy, { baseline: "top" });
      fy += 3.8;
    }
    w.font(7.3, "normal", C.muted);
    for (const note of f.notes) {
      for (const line of doc.splitTextToSize(clean(note), colW - 4) as string[]) {
        doc.text(line, fx, fy, { baseline: "top" });
        fy += 3.2;
      }
    }
    figBottom = Math.max(figBottom, fy);
  });
  w.y = figBottom + 6;

  const acted = didSomething(spec);
  const fan = (b: number[][] | undefined, n: number) => (b && b[0].length === n ? b : null);
  const policy = weekly(central.stringency, false);
  lineChart(
    w,
    {
      title: "How full hospitals get",
      note: "Hospital patients at the end of each week, against the beds available to the epidemic.",
      central: weekly(central.hospital, false),
      fan: fan(ensemble.bands.weekly.hospital, policy.length),
      compare: acted ? weekly(noAction.hospital, false) : null,
      capacity,
      policy,
      color: C.hosp,
    },
    r.days,
  );
  w.gap(2);
  lineChart(
    w,
    {
      title: "Deaths each week",
      note: "True deaths, including those official counts would miss.",
      central: weekly(central.deaths, true),
      fan: fan(ensemble.bands.weekly.deaths, policy.length),
      compare: acted ? weekly(noAction.deaths, true) : null,
      capacity: null,
      policy,
      color: C.deaths,
    },
    r.days,
  );

  // --- page 2: what drives it, who is hit, the written report -----------------------------------
  doc.addPage();
  w.y = M.top;
  const top = levers(tornado);
  if (tornado && top.length) {
    w.heading("What makes the biggest difference", "Total deaths when each input is pushed to a plausible low and high value, one at a time.");
    tornadoChart(w, tornado);
    for (const l of top) {
      w.rich([{ text: `${l.name}. `, bold: true }, { text: leverSentence(l) }], 9);
      w.gap(1.2);
    }
    w.gap(4);
  }

  w.heading("Who dies", "Each age group's share of the population, against its share of deaths.");
  ageBars(w, r.run.place.age_shares, central.deaths_by_age);
  w.gap(4);

  const report = buildReport(model, r, summary, ensemble, tornado);
  w.heading("Scenario report");
  for (const p of report.paragraphs) {
    w.text(p, { size: 9.5 });
    w.gap(2.2);
  }
  w.gap(1);
  bullets(w, report.warnings, 8.5, C.ink2);
  w.gap(4);

  // --- the numbers and where the settings came from ------------------------------------------------
  table(
    w,
    "Key numbers",
    [
      { label: "Outcome", width: 90 },
      { label: "Median run", width: 40, align: "right" },
      { label: "90% range", width: 44, align: "right" },
    ],
    report.metrics.map((m) => [m.label, m.median, m.range]),
  );
  table(
    w,
    "Where the settings came from",
    [
      { label: "Setting", width: 64 },
      { label: "Value", width: 56 },
      { label: "Source", width: 54, muted: true },
    ],
    settingsRows(model, r, spec).map((s) => [s.label, s.value, s.source]),
  );

  // --- how the model works ------------------------------------------------------------------------
  const c = model.constants;
  const v = model.validation;
  const pct = (x: number) => `${Math.round(x * 100)}%`;
  w.heading("How the simulator works");
  bullets(w, [
    "An age-structured epidemic model (SEIR) with vaccination, hospital care and deaths, run day by day.",
    `Fitted to 137 countries' 2020 epidemics with their real lockdowns: a strict lockdown (stringency 80) cuts transmission by ${pct(1 - Math.exp(80 * c.npi_coef))}; people pull back as reported deaths rise; transmission is ${pct((2 * c.covid_seasonality) / (1 + c.covid_seasonality))} lower in summer than winter at temperate latitudes; restrictions lose about ${pct(1 - c.fatigue_ratio)} of their effect after nine months.`,
    "Ridge regressions map a country's characteristics (wealth, health system, age, density and more) to its transmission, severity, caution, death reporting and vaccine uptake. That's how an edited or made-up country gets its settings.",
    `Each scenario is rerun ${ensemble.draws} times with uncertain inputs drawn from the models' own error, giving the ranges.`,
  ]);
  w.gap(2);
  const mae = (scores: Record<string, { mae_weekly_deaths_pm: number }>, k: string) => scores[k]?.mae_weekly_deaths_pm.toFixed(1) ?? "n/a";
  w.text(
    `On data it never saw, the simulator's error was ${mae(v.temporal_holdout, "simulator")} weekly deaths per million predicting the rest of 2020 (last month continuing: ${mae(v.temporal_holdout, "persistence")}), and ${mae(v.cross_country_hindcast, "simulator")} for a country it hadn't seen (continent average: ${mae(v.cross_country_hindcast, "continent_average")}). Simple baselines predict real counts better, so use it to compare scenarios, not to forecast.`,
    { size: 8.8, color: C.ink2 },
  );
  w.gap(4);
  w.text(CAVEAT, { size: 8.8, color: C.ink2 });
  w.gap(4);
  const trained = new Date(model.trained_at).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
  w.text(`Data: Our World in Data, WHO and World Bank World Development Indicators. Model version ${model.version}, trained ${trained}.`, { size: 8, color: C.muted });
  w.gap(1.5);
  w.ensure(5);
  w.font(8.5, "bold", C.ink);
  doc.textWithLink("Open this scenario in the simulator", M.x, w.y, { url: input.link, baseline: "top" });
  w.y += 5;

  // --- footers ------------------------------------------------------------------------------------
  const pages = doc.getNumberOfPages();
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i);
    const fy = PAGE.h - M.bottom + 8;
    w.rule(C.hair, fy - 2.5);
    w.font(7, "normal", C.muted);
    doc.text(clean(`${parts.slice(0, 2).join(" · ")}  ·  A scenario, not a forecast`), M.x, fy, { baseline: "top" });
    doc.text(`Page ${i} of ${pages}`, M.x + CW, fy, { baseline: "top", align: "right" });
  }
  return doc;
}

export function downloadPdf(input: PdfInput) {
  buildPdf(input).save(pdfFilename(input));
}
