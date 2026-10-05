/**
 * Parity: the browser engine and scenario layer must reproduce the Python reference on the golden
 * scenarios (golden.json, written by `covid-pipeline sim-fixtures`). Runs without exported data.
 */
import { describe, expect, it } from "vitest";
import { type EngineInputs, run } from "./engine";
import golden from "./golden.json";
import { buildInputs, fromJson, type ModelConstants, type Pathogen, type Place, type Response, type Variant } from "./scenario";

interface Case {
  days: number;
  place: Place;
  pathogen: Pathogen;
  response: Response;
  variant: Variant;
  constants: ModelConstants;
  inputs: Record<string, number | number[] | null>;
  outputs: Record<string, number[]>;
}

const cases = (golden as unknown as { cases: Record<string, Case> }).cases;

function decodeInputs(raw: Case["inputs"]): EngineInputs {
  const out: Record<string, number | number[]> = {};
  for (const [k, v] of Object.entries(raw)) out[k] = v === null ? Infinity : v;
  return out as unknown as EngineInputs;
}

function close(actual: number, expected: number | null, rtol = 1e-9, atol = 1e-9): boolean {
  const e = expected === null ? Infinity : expected;
  if (!Number.isFinite(e)) return actual === e;
  return Math.abs(actual - e) <= atol + rtol * Math.abs(e);
}

function expectClose(actual: ArrayLike<number>, expected: (number | null)[], label: string) {
  expect(actual.length, label).toBe(expected.length);
  for (let i = 0; i < expected.length; i++) {
    if (!close(actual[i], expected[i])) {
      throw new Error(`${label}[${i}]: got ${actual[i]}, expected ${expected[i]}`);
    }
  }
}

describe.each(Object.entries(cases))("golden scenario %s", (_name, c) => {
  it("builds the same engine inputs as Python", () => {
    const built = buildInputs(
      c.place,
      fromJson.pathogen(c.pathogen),
      fromJson.response(c.response),
      c.days,
      fromJson.constants(c.constants),
      fromJson.variant(c.variant),
    ) as unknown as Record<string, number | number[]>;
    for (const [key, expected] of Object.entries(c.inputs)) {
      const actual = built[key];
      if (Array.isArray(expected)) expectClose(actual as number[], expected, key);
      else expect(close(actual as number, expected), `${key}: got ${actual}, expected ${expected}`).toBe(true);
    }
  });

  it("produces the same outputs as Python", () => {
    const out = run(decodeInputs(c.inputs), c.days) as unknown as Record<string, ArrayLike<number>>;
    for (const [series, expected] of Object.entries(c.outputs)) expectClose(out[series], expected, series);
  });
});

describe("engine invariants", () => {
  const c = cases["covid_lockdown_and_vaccine"];
  const inputs = decodeInputs(c.inputs);
  const out = run(inputs, c.days);

  it("conserves the population", () => {
    for (let d = 0; d < c.days; d++) {
      const total = out.susceptible[d] + out.infected[d] + out.immune[d] + out.hospital[d] + out.dead[d];
      expect(total / inputs.population).toBeCloseTo(1, 9);
    }
  });

  it("never lets a compartment go negative", () => {
    for (const s of [out.susceptible, out.infected, out.immune, out.hospital, out.dead, out.infections]) {
      expect(Math.min(...s)).toBeGreaterThanOrEqual(-1e-6);
    }
  });

  it("runs a two-year scenario in well under a frame", () => {
    const long = { ...inputs, stringency: new Array(730).fill(0) };
    const start = performance.now();
    for (let i = 0; i < 20; i++) run(long, 730);
    expect((performance.now() - start) / 20).toBeLessThan(15);
  });
});
