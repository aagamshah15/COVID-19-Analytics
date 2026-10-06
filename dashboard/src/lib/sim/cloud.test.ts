/**
 * The contract with the cloud service: every scenario the page can produce must be one the service
 * accepts. `api/scenario.schema.json` is generated from the service's request models
 * (`python -m api.schemas`; a Python test fails if it is stale), and these tests check the page's
 * scenarios against it.
 */
import { existsSync, readFileSync } from "node:fs";
import { resolve as resolvePath } from "node:path";
import Ajv2020 from "ajv/dist/2020";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import golden from "./golden.json";
import { prepare, type SimModel } from "./model";
import type { ScenarioRun } from "./montecarlo";
import { fromJson, type ModelConstants, type Pathogen, type Place, type Response as PolicyResponse, type Variant } from "./scenario";
import { READY } from "./scenarios";
import { resolve } from "./spec";

const schema = JSON.parse(readFileSync(resolvePath(__dirname, "../../../../api/scenario.schema.json"), "utf8"));
const validate = new Ajv2020({ allErrors: true, strict: false }).compile(schema);

function problems(run: ScenarioRun, toJson: (run: ScenarioRun) => string): string[] {
  validate(JSON.parse(toJson(run)));
  return (validate.errors ?? []).map((e) => `${e.instancePath} ${e.message}`);
}

interface Case {
  days: number;
  place: Place;
  pathogen: Pathogen;
  response: PolicyResponse;
  variant: Variant;
  constants: ModelConstants;
}
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

/** A golden scenario as the page holds it in memory: "never" is Infinity, not null. */
function goldenRun(c: Case): ScenarioRun {
  return {
    place: c.place,
    sources: { transmission: "calibrated", severity: "predicted", awareness: "calibrated", reporting: "observed", vaccine_acceptance: "user", vaccine_capacity: "observed" },
    pathogen: fromJson.pathogen(c.pathogen),
    response: fromJson.response(c.response),
    variant: fromJson.variant(c.variant),
    constants: fromJson.constants(c.constants),
    uncertainty: UNCERTAINTY,
    days: c.days,
  };
}
const cases = Object.entries((golden as unknown as { cases: Record<string, Case> }).cases);

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.resetModules();
});

/** The module reads the service's address when it loads, so each test loads it afresh. */
async function load(url = "https://api.example/") {
  vi.stubEnv("VITE_SIM_API_URL", url);
  return import("./cloud");
}

describe("scenarios sent to the cloud service", () => {
  it.each(cases)("golden scenario %s matches the service's schema", async (_name, c) => {
    const { scenarioJson } = await load();
    expect(problems(goldenRun(c), scenarioJson)).toEqual([]);
  });

  it("sends 'never' as null, which the service reads back as never", async () => {
    const { scenarioJson } = await load();
    const run = goldenRun(cases[0][1]);
    expect(run.variant.day).toBe(Infinity);
    const sent = JSON.parse(scenarioJson(run));
    expect(sent.variant.day).toBeNull();
    expect(sent.response.treatment_day).toBeNull();
    expect(sent.days).toBe(run.days);
  });

  it("the schema refuses what the service would refuse", async () => {
    const { scenarioJson } = await load();
    const run = goldenRun(cases[0][1]);
    expect(problems({ ...run, days: 5000 }, scenarioJson)).toEqual(["/days must be <= 1095"]);
    expect(problems({ ...run, pathogen: { ...run.pathogen, r0: -1 } }, scenarioJson)).toEqual(["/pathogen/r0 must be > 0"]);
    expect(problems({ ...run, extra: 1 } as ScenarioRun, scenarioJson)).toEqual([" must NOT have additional properties"]);
  });
});

const modelPath = resolvePath(__dirname, "../../../public/data/simulator.json");

describe.skipIf(!existsSync(modelPath))("scenarios built from the trained model", () => {
  let model!: SimModel;
  beforeAll(() => {
    model = prepare(JSON.parse(readFileSync(modelPath, "utf8")));
  });

  it.each(READY.map((s) => [s.id, s] as const))("ready-made scenario %s matches the service's schema", async (_id, ready) => {
    const { scenarioJson } = await load();
    expect(problems(resolve(model, ready.spec).run, scenarioJson)).toEqual([]);
  });

  it("every country and every disease matches the schema, with every plan and vaccine choice", async () => {
    const { scenarioJson } = await load();
    const base = READY[0].spec;
    const failures: string[] = [];
    const check = (label: string, spec: typeof base) => {
      const found = problems(resolve(model, spec).run, scenarioJson);
      if (found.length) failures.push(`${label}: ${found.slice(0, 3).join("; ")}`);
    };
    for (const country of model.countries) check(country.iso, { ...base, iso: country.iso });
    for (const preset of model.presets) check(preset.id, { ...base, pathogen: { preset: preset.id, edits: {} } });
    for (const plan of ["none", "mitigate", "suppress", "adaptive"] as const) {
      for (const vaccine of ["none", "6m", "1y", "exists"] as const) {
        for (const years of [1, 2, 3] as const) check(`${plan}/${vaccine}/${years}y`, { ...base, plan, vaccine, years });
      }
    }
    expect(failures).toEqual([]);
  });
});

describe("talking to the cloud service", () => {
  const run = goldenRun(cases[0][1]);
  const answer = (status: number, body: unknown = {}, headers: Record<string, string> = {}) =>
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });

  it("is switched off when no address is configured", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const cloud = await load("");
    expect(cloud.cloudConfigured).toBe(false);
    expect(await cloud.cloudAvailable()).toBe(false);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("asks once whether the service is up, and treats any failure as down", async () => {
    const fetch = vi.fn().mockResolvedValue(answer(200, { status: "ok" }));
    vi.stubGlobal("fetch", fetch);
    const cloud = await load();
    expect(await cloud.cloudAvailable()).toBe(true);
    expect(await cloud.cloudAvailable()).toBe(true);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe("https://api.example/health");

    vi.resetModules();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    expect(await (await load()).cloudAvailable()).toBe(false);
    vi.resetModules();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(answer(404)));
    expect(await (await load()).cloudAvailable()).toBe(false);
  });

  it("posts the scenario and returns the analysis", async () => {
    const result = { summary: {}, monte_carlo: { draws: 5000 }, sobol: { factors: [] }, ms: 12 };
    const fetch = vi.fn().mockResolvedValue(answer(200, result));
    vi.stubGlobal("fetch", fetch);
    const cloud = await load();
    expect(await cloud.deepAnalysis(run, 3)).toEqual(result);
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("https://api.example/analyze/deep");
    expect(init.method).toBe("POST");
    const sent = JSON.parse(init.body);
    expect(sent.seed).toBe(3);
    expect(sent.scenario.place.population).toBe(run.place.population);
    expect(sent.scenario.variant.day).toBeNull();
  });

  it.each([
    [429, { "retry-after": "42" }, "busy", 42],
    [503, { "retry-after": "15" }, "busy", 15],
    [429, {}, "busy", null],
    [422, {}, "rejected", null],
    [500, {}, "unavailable", null],
  ] as const)("turns a %s answer into a clear failure", async (status, headers, kind, retryAfter) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(answer(status, { detail: "no" }, headers)));
    const cloud = await load();
    const error = await cloud.deepAnalysis(run).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(cloud.CloudError);
    expect(error).toMatchObject({ kind, retryAfter });
  });

  it("reports an unreachable service as unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const cloud = await load();
    await expect(cloud.deepAnalysis(run)).rejects.toMatchObject({ kind: "unavailable" });
  });
});

describe("reading the analysis", () => {
  const factor = (first: number, total: number) => ({ key: "k", label: "l", first, first_interval: [0, 1] as [number, number], total, total_interval: [0, 1] as [number, number] });

  it("measures what an input explains only in combination with others", async () => {
    const { combinedShare } = await load();
    expect(combinedShare(factor(0.44, 0.52))).toBeCloseTo(0.08);
    expect(combinedShare(factor(0.3, 0.28))).toBe(0); // estimates are noisy: never negative
  });

  it("says how long to wait in everyday words", async () => {
    const { waitWords } = await load();
    expect(waitWords(3)).toBe("about 5 seconds");
    expect(waitWords(42)).toBe("about 40 seconds");
    expect(waitWords(600)).toBe("about 10 minutes");
    expect(waitWords(3600)).toBe("about 60 minutes");
    expect(waitWords(80000)).toBe("about 22 hours");
  });
});
