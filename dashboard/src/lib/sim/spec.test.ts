import { existsSync, readFileSync } from "node:fs";
import { resolve as resolvePath } from "node:path";
import { describe, expect, it } from "vitest";
import { prepare } from "./model";
import { simulate, summarise } from "./montecarlo";
import { READY } from "./scenarios";
import { decodeSpec, EMPTY_SPEC, encodeSpec, isComplete, resolve } from "./spec";
import { aboutPeople, rounded, shareInWords } from "./words";

describe("scenario spec", () => {
  it("starts empty and can't run until all three questions are answered", () => {
    const spec = EMPTY_SPEC();
    expect(isComplete(spec)).toBe(false);
    expect(isComplete({ ...spec, iso: "IND", pathogen: { preset: "measles", edits: {} }, plan: "none" })).toBe(false);
    expect(isComplete({ ...spec, iso: "IND", pathogen: { preset: "measles", edits: {} }, plan: "none", vaccine: "none" })).toBe(true);
  });

  it("round-trips through a share link, including infinities", () => {
    const spec = { ...READY[0].spec, pathogen: { preset: "covid_ancestral", edits: { immunity_days: Infinity } } };
    expect(decodeSpec(encodeSpec(spec))).toEqual(spec);
  });

  it("refuses a link to an incomplete scenario or garbage", () => {
    expect(decodeSpec(encodeSpec(EMPTY_SPEC()))).toBeNull();
    expect(decodeSpec("not-a-scenario")).toBeNull();
  });
});

describe("plain language", () => {
  it.each([
    [0.25, "about 1 in 4 people"],
    [0.5, "about half of all people"],
    [0.71, "about 7 in 10 people"],
    [0.97, "almost everyone"],
    [1.6, "everyone, on average more than once"],
  ])("describes a %s share as %s", (share, words) => expect(shareInWords(share)).toBe(words));

  it("rounds counts to two significant figures", () => {
    expect(rounded(377_069)).toEqual({ value: "380,000", unit: "" });
    expect(rounded(6_604_211)).toEqual({ value: "6.6", unit: "million" });
    expect(aboutPeople(6_604_211)).toBe("about 6.6 million");
  });
});

const modelPath = resolvePath(__dirname, "../../../public/data/simulator.json");

describe.skipIf(!existsSync(modelPath))("ready-made scenarios with the trained model", () => {
  const model = prepare(JSON.parse(readFileSync(modelPath, "utf8")));

  it.each(READY.map((s) => [s.id, s] as const))("%s resolves to a known country and disease, and runs", (_id, ready) => {
    expect(isComplete(ready.spec)).toBe(true);
    expect(model.byIso.has(ready.spec.iso!)).toBe(true);
    expect(model.presets.some((p) => p.id === ready.spec.pathogen.preset)).toBe(true);
    const r = resolve(model, ready.spec);
    const s = summarise(simulate(r.run), r.run.place.population, 1);
    expect(Number.isFinite(s.deaths)).toBe(true);
    expect(s.deaths).toBeGreaterThanOrEqual(0);
  });

  it("maps vaccine choices to arrival days", () => {
    const base = { ...READY[0].spec };
    expect(resolve(model, { ...base, vaccine: "none" }).response.vaccine).toBe(false);
    expect(resolve(model, { ...base, vaccine: "6m" }).response.vaccine_day).toBe(182);
    expect(resolve(model, { ...base, vaccine: "exists" }).response.vaccine_day).toBe(0);
  });

  it("'Older' and 'Stronger healthcare' move the place the right way", () => {
    const base = { ...READY[0].spec, iso: "IND" };
    const plain = resolve(model, base).settings;
    const older = resolve(model, { ...base, simple: { age: 1, care: 0 } }).settings;
    const stronger = resolve(model, { ...base, simple: { age: 0, care: 1 } }).settings;
    expect(older.age_shares[4]).toBeGreaterThan(plain.age_shares[4]);
    expect(stronger.signals.hospital_beds_per_thousand!).toBeGreaterThan(plain.signals.hospital_beds_per_thousand!);
  });
});
