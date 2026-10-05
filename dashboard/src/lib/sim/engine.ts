/**
 * Simulation engine: an age-structured SEIR model with vaccination and hospital care.
 *
 * A line-for-line port of the Python reference engine (src/covid_pipeline/simulator/engine.py),
 * for one scenario at a time. Operations happen in the same order so floating-point results match;
 * engine.test.ts holds the two within 1e-9 on the golden scenarios. Change both together, then
 * regenerate the fixtures with `covid-pipeline sim-fixtures`.
 *
 * Compartments per age band (0-19, 20-39, 40-59, 60-79, 80+): S susceptible, V vaccinated,
 * Em/Es exposed (mild/severe path), Im/Is infectious, H in hospital, R recovered, D died.
 * See the Python module for the model description.
 */

export const N_BANDS = 5;
export const SUBSTEPS = 4;

/** Bravata et al. (2021): ICU strain -> mortality multiplier for ICU-level patients. */
const OVERLOAD_X = [0.0, 0.5, 0.625, 0.875, 1.0];
const OVERLOAD_Y = [1.0, 1.0, 1.19, 1.94, 1.94];

export type Bands = number[];

/** Engine inputs for one scenario. Infinity means "never" / "off" / "lifelong". */
export interface EngineInputs {
  population: number;
  age_shares: Bands;
  r0: number;
  latent_days: number;
  infectious_days: number;
  ifr: Bands;
  hosp: Bands;
  hosp_days: number;
  icu_share: number;
  immunity_days: number;
  seed_per_million: number;
  seed_day: number;
  seasonality: number;
  season_peak_day: number;
  npi_coef: number;
  npi_coef_late: number;
  fatigue_start: number;
  fatigue_end: number;
  isolation: number;
  awareness_deaths_pm: number;
  awareness_power: number;
  stringency: number[];
  adaptive: number;
  adaptive_on: number;
  adaptive_off: number;
  adaptive_level: number;
  adaptive_min_days: number;
  variant_day: number;
  variant_transmission: number;
  variant_severity: number;
  variant_escape: number;
  vaccine_day: number;
  vaccine_capacity: number;
  vaccine_acceptance: Bands;
  ve_infection: number;
  ve_death: number;
  vaccine_immunity_days: number;
  vaccine_oldest_first: number;
  treatment_day: number;
  treatment_effect: number;
  beds: number;
  icu_beds: number;
  icu_death_share: number;
  unmet_multiplier: number;
  death_reporting: number;
  case_detection: number;
}

export interface EngineOutputs {
  infections: Float64Array;
  admissions: Float64Array;
  hospital: Float64Array;
  icu: Float64Array;
  deaths: Float64Array;
  reported_deaths: Float64Array;
  reported_cases: Float64Array;
  rt: Float64Array;
  stringency: Float64Array;
  vaccinated: Float64Array;
  susceptible: Float64Array;
  infected: Float64Array;
  immune: Float64Array;
  dead: Float64Array;
  deaths_by_age: Bands;
}

export const SERIES = [
  "infections",
  "admissions",
  "hospital",
  "icu",
  "deaths",
  "reported_deaths",
  "reported_cases",
  "rt",
  "stringency",
  "vaccinated",
  "susceptible",
  "infected",
  "immune",
  "dead",
] as const;
export type SeriesName = (typeof SERIES)[number];

/** np.interp over the Bravata points, with numpy's arithmetic. */
function interpOverload(x: number): number {
  const n = OVERLOAD_X.length;
  if (x <= OVERLOAD_X[0]) return OVERLOAD_Y[0];
  if (x >= OVERLOAD_X[n - 1]) return OVERLOAD_Y[n - 1];
  let j = 0;
  while (j < n - 2 && OVERLOAD_X[j + 1] <= x) j++;
  const slope = (OVERLOAD_Y[j + 1] - OVERLOAD_Y[j]) / (OVERLOAD_X[j + 1] - OVERLOAD_X[j]);
  return slope * (x - OVERLOAD_X[j]) + OVERLOAD_Y[j];
}

export function overloadMultiplier(ratio: number, unmet: number): number {
  const within = interpOverload(Math.min(ratio, 1.0));
  const over = Math.max(ratio - 1.0, 0.0);
  return ratio > 1.0 ? (OVERLOAD_Y[OVERLOAD_Y.length - 1] + unmet * over) / Math.max(ratio, 1.0) : within;
}

/** 1 - exp(-rate dt), via expm1 to keep precision when the force of infection is tiny. */
const infectionProbability = (rate: number, dt: number) => -Math.expm1(-rate * dt);
const exitProbability = (duration: number, dt: number) => Math.min(dt / duration, 1.0);

function sum(a: Float64Array): number {
  let s = 0;
  for (let b = 0; b < N_BANDS; b++) s += a[b];
  return s;
}

export function run(x: EngineInputs, days: number): EngineOutputs {
  const dt = 1.0 / SUBSTEPS;
  const B = N_BANDS;
  const bands = () => new Float64Array(B);
  const popBand = bands();
  const seed = bands();
  const seedTotal = Math.min((x.seed_per_million * x.population) / 1e6, x.population * 0.01);
  for (let b = 0; b < B; b++) {
    popBand[b] = x.population * x.age_shares[b];
    seed[b] = seedTotal * x.age_shares[b];
  }
  const seedDay = Math.floor(x.seed_day);
  let S = Float64Array.from(popBand);
  let V = bands(), Em = bands(), Es = bands(), Im = bands(), Is = bands(), H = bands(), R = bands(), D = bands();
  const vaccinated = bands();

  const fatality = bands();
  const eligibleCap = bands();
  for (let b = 0; b < B; b++) {
    fatality[b] = Math.min(x.ifr[b] / Math.max(x.hosp[b], 1e-12), 1.0);
    eligibleCap[b] = x.vaccine_acceptance[b] * popBand[b];
  }
  const vaccineSeverity = (1 - x.ve_death) / Math.max(1 - x.ve_infection, 1e-12);
  const beta0 = x.r0 / x.infectious_days;
  const pLatent = exitProbability(x.latent_days, dt);
  const pInfectious = exitProbability(x.infectious_days, dt);
  const pDischarge = exitProbability(x.hosp_days, dt);
  const pWane = exitProbability(x.immunity_days, dt);
  const pVaccineWane = exitProbability(x.vaccine_immunity_days, dt);
  const oldestFirst = x.vaccine_oldest_first > 0.5;

  const series = () => new Float64Array(days);
  const out = {
    infections: series(),
    admissions: series(),
    hospital: series(),
    icu: series(),
    deaths: series(),
    reported_deaths: series(),
    reported_cases: series(),
    rt: series(),
    stringency: series(),
    vaccinated: series(),
    susceptible: series(),
    infected: series(),
    immune: series(),
    dead: series(),
  };
  let adaptiveOn = false;
  let adaptiveSince = 0;
  let escaped = false;
  let recentDeathsPm = 0;

  const toEs = bands(), toEm = bands(), infS = bands(), infV = bands();
  const remaining = bands(), doses = bands();

  for (let day = 0; day < days; day++) {
    // --- once per day: seeding, policy, variant escape, effective reproduction number ----
    if (seedDay === day) {
      for (let b = 0; b < B; b++) {
        const arriving = Math.min(seed[b], S[b]);
        S[b] = S[b] - arriving;
        Im[b] = Im[b] + arriving * (1 - x.hosp[b]);
        Is[b] = Is[b] + arriving * x.hosp[b];
      }
    }

    const occupancy = sum(H) / Math.max(x.beds, 1e-12);
    const switchOn: boolean = x.adaptive > 0.5 && !adaptiveOn && occupancy >= x.adaptive_on;
    const switchOff: boolean = adaptiveOn && occupancy <= x.adaptive_off && day - adaptiveSince >= x.adaptive_min_days;
    adaptiveOn = (adaptiveOn || switchOn) && !switchOff;
    if (switchOn) adaptiveSince = day;
    const stringency = adaptiveOn ? Math.max(x.stringency[day], x.adaptive_level) : x.stringency[day];

    const variant = day >= x.variant_day;
    if (variant && !escaped) {
      for (let b = 0; b < B; b++) {
        const movedR = R[b] * x.variant_escape;
        const movedV = V[b] * x.variant_escape;
        R[b] = R[b] - movedR;
        V[b] = V[b] - movedV;
        S[b] = S[b] + movedR + movedV;
      }
      escaped = true;
    }
    const transmission = variant ? x.variant_transmission : 1.0;
    const severity = variant ? x.variant_severity : 1.0;
    const season = 1.0 + x.seasonality * Math.cos((2 * Math.PI * (day - x.season_peak_day)) / 365.0);
    const fatigue = Math.min(Math.max((day - x.fatigue_start) / Math.max(x.fatigue_end - x.fatigue_start, 1e-12), 0.0), 1.0);
    const npiCoef = x.npi_coef + (x.npi_coef_late - x.npi_coef) * fatigue;
    const awareness = 1.0 / (1.0 + (recentDeathsPm / x.awareness_deaths_pm) ** x.awareness_power);
    const beta = beta0 * season * Math.exp(npiCoef * stringency) * (1 - x.isolation) * transmission * awareness;
    const care = day >= x.treatment_day ? 1 - x.treatment_effect : 1.0;
    const vaccinating = day >= x.vaccine_day;

    let alive = 0;
    for (let b = 0; b < B; b++) alive += S[b] + V[b] + Em[b] + Es[b] + Im[b] + Is[b] + H[b] + R[b];
    out.rt[day] = (beta * x.infectious_days * (sum(S) + (1 - x.ve_infection) * sum(V))) / alive;
    out.stringency[day] = stringency;

    let newInf = 0;
    let newAdm = 0;
    let newDead = 0;
    for (let step = 0; step < SUBSTEPS; step++) {
      alive = 0;
      let infectious = 0;
      for (let b = 0; b < B; b++) {
        alive += S[b] + V[b] + Em[b] + Es[b] + Im[b] + Is[b] + H[b] + R[b];
        infectious += Im[b] + Is[b];
      }
      const force = (beta * infectious) / Math.max(alive, 1e-12);
      const pS = infectionProbability(force, dt);
      const pV = infectionProbability(force * (1 - x.ve_infection), dt);
      for (let b = 0; b < B; b++) {
        infS[b] = S[b] * pS;
        infV[b] = V[b] * pV;
        const severeShare = Math.min(x.hosp[b] * severity, 1.0);
        toEs[b] = infS[b] * severeShare + infV[b] * Math.min(severeShare * vaccineSeverity, 1.0);
        toEm[b] = infS[b] + infV[b] - toEs[b];
      }

      const hospital = sum(H);
      const icuRatio = Math.max((x.icu_share * hospital) / Math.max(x.icu_beds, 1e-12), hospital / Math.max(x.beds, 1e-12));
      const strain = 1 + x.icu_death_share * (overloadMultiplier(icuRatio, x.unmet_multiplier) - 1);

      let admitted = 0;
      let died = 0;
      let infected = 0;
      for (let b = 0; b < B; b++) {
        const onsetM = Em[b] * pLatent;
        const onsetS = Es[b] * pLatent;
        const recoverM = Im[b] * pInfectious;
        const admit = Is[b] * pInfectious;
        const discharge = H[b] * pDischarge;
        const die = discharge * Math.min(fatality[b] * strain * care, 1.0);
        const waneR = R[b] * pWane;
        const waneV = V[b] * pVaccineWane;

        S[b] = S[b] - infS[b] + waneR + waneV;
        V[b] = V[b] - infV[b] - waneV;
        Em[b] = Em[b] + toEm[b] - onsetM;
        Es[b] = Es[b] + toEs[b] - onsetS;
        Im[b] = Im[b] + onsetM - recoverM;
        Is[b] = Is[b] + onsetS - admit;
        H[b] = H[b] + admit - discharge;
        R[b] = R[b] + recoverM + (discharge - die) - waneR;
        D[b] = D[b] + die;
        admitted += admit;
        died += die;
        infected += infS[b] + infV[b];
      }

      // Vaccination: doses go to people who accept and haven't been vaccinated yet.
      const capacity = vaccinating ? x.vaccine_capacity * x.population * dt : 0.0;
      for (let b = 0; b < B; b++) remaining[b] = Math.max(eligibleCap[b] - vaccinated[b], 0.0);
      allocate(capacity, remaining, oldestFirst, doses);
      for (let b = 0; b < B; b++) {
        const reachable = S[b] + R[b];
        let toV = doses[b] * (reachable > 0 ? S[b] / Math.max(reachable, 1e-12) : 0.0);
        toV = Math.min(toV, S[b]);
        S[b] = S[b] - toV;
        V[b] = V[b] + toV;
        vaccinated[b] = vaccinated[b] + doses[b];
      }

      newInf += infected;
      newAdm += admitted;
      newDead += died;
    }
    recentDeathsPm = recentDeathsPm + ((newDead * x.death_reporting * 1e6) / x.population - recentDeathsPm) / 7.0;

    const hospital = sum(H);
    out.infections[day] = newInf;
    out.admissions[day] = newAdm;
    out.deaths[day] = newDead;
    out.reported_deaths[day] = newDead * x.death_reporting;
    out.reported_cases[day] = newInf * x.case_detection;
    out.hospital[day] = hospital;
    out.icu[day] = x.icu_share * hospital;
    out.vaccinated[day] = sum(vaccinated);
    out.susceptible[day] = sum(S);
    let infectedNow = 0;
    let immune = 0;
    for (let b = 0; b < B; b++) {
      infectedNow += Em[b] + Es[b] + Im[b] + Is[b];
      immune += R[b] + V[b];
    }
    out.infected[day] = infectedNow;
    out.immune[day] = immune;
    out.dead[day] = sum(D);
  }
  return { ...out, deaths_by_age: Array.from(D) };
}

/** Split doses across bands: oldest band first, or in proportion to who's left. */
function allocate(capacity: number, remaining: Float64Array, oldestFirst: boolean, into: Float64Array): void {
  if (oldestFirst) {
    let left = capacity;
    for (let b = N_BANDS - 1; b >= 0; b--) {
      const take = Math.min(left, remaining[b]);
      into[b] = take;
      left = left - take;
    }
    return;
  }
  const total = sum(remaining);
  const share = total > 0 ? Math.min(capacity / Math.max(total, 1e-12), 1.0) : 0.0;
  for (let b = 0; b < N_BANDS; b++) into[b] = remaining[b] * share;
}
