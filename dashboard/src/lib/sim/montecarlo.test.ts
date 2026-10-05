import { describe, expect, it } from "vitest";
import golden from "./golden.json";
import type { SimModel } from "./model";
import { capacityOf, ensemble, perturb, QUANTILES, rng, type ScenarioRun, sensitivity, simulate, summarise, withoutResponse } from "./montecarlo";
import { fromJson } from "./scenario";

const UNCERTAINTY: SimModel["uncertainty"] = {
  log_transmission_sd: { calibrated: 0.12, predicted: 0.24 },
  log_severity_sd: { calibrated: 0.3, predicted: 0.6 },
  log_awareness_country_sd: { calibrated: 0.4, predicted: 0.8 },
  logit_reporting_sd: { observed: 0.2, predicted: 1.0 },
  logit_vaccine_acceptance_sd: { observed: 0.2, predicted: 1.0 },
  log_vaccine_capacity_sd: { observed: 0.2, predicted: 0.7 },
  npi_coef_sd: 0.0007,
  log_awareness_sd: 0.3,
  seasonality_sd: 0.05,
  log_r0_sd: 0.1,
  log_ifr_sd: 0.2,
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const c = (golden as any).cases.covid_lockdown_and_vaccine;
const RUN: ScenarioRun = {
  place: c.place,
  sources: { transmission: "calibrated", severity: "calibrated", awareness: "calibrated", reporting: "predicted", vaccine_acceptance: "observed", vaccine_capacity: "observed" },
  pathogen: fromJson.pathogen(c.pathogen),
  response: fromJson.response(c.response),
  variant: fromJson.variant(c.variant),
  constants: fromJson.constants(c.constants),
  uncertainty: UNCERTAINTY,
  days: c.days,
};

describe("ensemble", () => {
  const result = ensemble(RUN, 60, 7);

  it("is reproducible for a given seed", () => {
    const again = ensemble(RUN, 60, 7);
    expect(again.summary.quantiles.deaths).toEqual(result.summary.quantiles.deaths);
  });

  it("orders its quantiles at every step", () => {
    for (const bands of [result.bands.daily.deaths, result.bands.weekly.hospital]) {
      for (let t = 0; t < bands[0].length; t++) {
        for (let q = 1; q < QUANTILES.length; q++) expect(bands[q][t]).toBeGreaterThanOrEqual(bands[q - 1][t]);
      }
    }
  });

  it("weekly flows are sums of the days, not sums of quantiles", () => {
    const weeks = result.bands.weekly.deaths[2].length;
    expect(weeks).toBe(Math.ceil(c.days / 7));
    const centralWeek1 = Array.from(result.central.deaths.slice(7, 14)).reduce((a, b) => a + b, 0);
    expect(centralWeek1).toBeGreaterThanOrEqual(0);
  });

  it("summarises the central run consistently with the engine", () => {
    const direct = summarise(simulate(RUN), RUN.place.population, capacityOf(RUN));
    expect(result.summary.central.deaths).toBeCloseTo(direct.deaths, 6);
    expect(result.summary.quantiles.deaths[0]).toBeLessThanOrEqual(result.summary.quantiles.deaths[4]);
  });

  it("a lockdown and a vaccine avert deaths against no response", () => {
    expect(result.noResponse.deaths).toBeGreaterThan(result.summary.central.deaths);
    expect(withoutResponse(RUN).response.segments).toHaveLength(0);
  });
});

describe("perturbation", () => {
  it("leaves values set by hand untouched", () => {
    const r = rng(3);
    const pinned: ScenarioRun = { ...RUN, sources: { ...RUN.sources, transmission: "user", vaccine_acceptance: "user" } };
    for (let i = 0; i < 20; i++) {
      const draw = perturb(pinned, r.normal);
      expect(draw.place.transmission).toBe(RUN.place.transmission);
      expect(draw.place.vaccine_acceptance).toBe(RUN.place.vaccine_acceptance);
    }
  });

  it("normal draws have the right spread", () => {
    const r = rng(11);
    const xs = Array.from({ length: 20000 }, () => r.normal());
    const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
    const sd = Math.sqrt(xs.reduce((a, b) => a + (b - mean) ** 2, 0) / xs.length);
    expect(Math.abs(mean)).toBeLessThan(0.03);
    expect(sd).toBeCloseTo(1, 1);
  });
});

describe("sensitivity", () => {
  it("ranks inputs by how much they move deaths, and moves them the expected way", () => {
    const { base, bars } = sensitivity(RUN);
    const swing = (b: (typeof bars)[number]) => Math.abs(b.high - b.low);
    for (let i = 1; i < bars.length; i++) expect(swing(bars[i - 1])).toBeGreaterThanOrEqual(swing(bars[i]));
    const r0 = bars.find((b) => b.key === "r0")!;
    expect(r0.high).toBeGreaterThan(base);
    expect(r0.low).toBeLessThan(base);
    const beds = bars.find((b) => b.key === "beds")!;
    expect(beds.high).toBeLessThanOrEqual(beds.low);
  });
});
