import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve as resolvePath } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { prepare, type SimModel } from "./model";
import { capacityOf, ensemble, sensitivity, simulate, summarise, withoutResponse } from "./montecarlo";
import { buildPdf, clean, pdfFilename } from "./pdf";
import { READY } from "./scenarios";
import { resolve } from "./spec";

describe("pdf text", () => {
  it("keeps what the standard fonts can draw and maps the rest", () => {
    expect(clean("1.2M–105M × 2 · “quoted” ≈ 3 → 4 ≥ 5")).toBe("1.2M–105M × 2 · “quoted” ~ 3 -> 4 >= 5");
  });
});

const modelPath = resolvePath(__dirname, "../../../public/data/simulator.json");

describe.skipIf(!existsSync(modelPath))("pdf report with the trained model", () => {
  // A skipped suite's body still runs to collect its tests, so the file is only read in beforeAll.
  let model!: SimModel;
  beforeAll(() => {
    model = prepare(JSON.parse(readFileSync(modelPath, "utf8")));
  });

  it.each(READY.map((s) => [s.id, s] as const))("%s builds a multi-page report", (_id, ready) => {
    const r = resolve(model, ready.spec);
    const capacity = capacityOf(r.run);
    const central = simulate(r.run);
    const noAction = simulate(withoutResponse(r.run));
    const doc = buildPdf({
      model,
      spec: ready.spec,
      r,
      central,
      noAction,
      summary: summarise(central, r.run.place.population, capacity),
      noActionSummary: summarise(noAction, r.run.place.population, capacity),
      ensemble: ensemble(r.run, 200, 1),
      tornado: sensitivity(r.run),
      capacity,
      link: "https://example.org/#/simulator",
      date: new Date("2026-10-05"),
    });
    expect(doc.getNumberOfPages()).toBeGreaterThanOrEqual(2);
    expect(pdfFilename({ r, spec: ready.spec } as never)).toMatch(/^pandemic-scenario-[a-z-]+-[a-z0-9-]+\.pdf$/);
    // Set SIM_PDF_OUT to a folder to look at the reports.
    if (process.env.SIM_PDF_OUT) writeFileSync(`${process.env.SIM_PDF_OUT}/${pdfFilename({ r, spec: ready.spec } as never)}`, Buffer.from(doc.output("arraybuffer")));
  });
});
