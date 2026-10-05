/**
 * The browser's use of the trained model must reproduce what training exported. Needs
 * `covid-pipeline sim-train` + `web-export`; skipped when simulator.json hasn't been generated.
 */
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { ageStructureFor, analogs, buildPlace, type CountryProfile, featureVector, learnedFor, prepare, settingsFor, type SimModel, waveSeverity } from "./model";

const path = resolve(__dirname, "../../../public/data/simulator.json");

describe.skipIf(!existsSync(path))("trained simulator model", () => {
  // A skipped suite's body still runs to collect its tests, so the file is only read in beforeAll.
  let model!: SimModel;
  let india!: CountryProfile;
  beforeAll(() => {
    model = prepare(JSON.parse(readFileSync(path, "utf8")));
    india = model.byIso.get("IND")!;
  });

  it("standardises features exactly as training did", () => {
    for (const country of model.countries.slice(0, 40)) {
      const z = featureVector(model, country.signals);
      z.forEach((v, i) => expect(v).toBeCloseTo(country.z[i], 3));
    }
  });

  it("an unedited country keeps its own learned values", () => {
    const learned = learnedFor(model, india, india.signals);
    expect(learned.transmission.value).toBe(india.learned.transmission.value);
    expect(learned.reporting.value).toBe(india.learned.reporting.value);
  });

  it("an edit moves values by the model's prediction, keeping the country's residual", () => {
    const richer = { ...india.signals, gdp_per_capita: india.signals.gdp_per_capita! * 4, health_exp_per_capita: india.signals.health_exp_per_capita! * 8 };
    const learned = learnedFor(model, india, richer);
    expect(learned.reporting.value).toBeGreaterThan(india.learned.reporting.value); // richer countries report more deaths
    expect(learned.transmission.source).toBe(india.learned.transmission.source);
  });

  it("builds an engine place from a country", () => {
    const { place } = buildPlace(model, india, settingsFor(india));
    expect(place.population).toBe(india.population);
    expect(place.age_shares.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 6);
    expect(place.access).toBeCloseTo(india.signals.uhc_index! / 100, 6);
  });

  it("finds a country as its own nearest analog", () => {
    const { nearest, unusualness } = analogs(model, india.z);
    expect(nearest[0].country.iso).toBe("IND");
    expect(unusualness).toBeLessThan(0.1);
  });

  it("gives wave-severity probabilities that sum to one and react to lockdowns", () => {
    const loose = waveSeverity(model, india.z, { stringency_first_4w: 0, vaccinated_at_start: 0, log_prior_deaths_pm: 0 }, "delta");
    const strict = waveSeverity(model, india.z, { stringency_first_4w: 90, vaccinated_at_start: 0, log_prior_deaths_pm: 0 }, "delta");
    expect(loose.probabilities.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 9);
    expect(loose.probabilities).toHaveLength(4);
    expect(strict.probabilities).not.toEqual(loose.probabilities);
  });

  it("derives an older age structure for an older median age", () => {
    const young = ageStructureFor(model, 18);
    const old = ageStructureFor(model, 48);
    expect(old.shares[4]).toBeGreaterThan(young.shares[4]);
    expect(old.share65).toBeGreaterThan(young.share65);
  });
});
