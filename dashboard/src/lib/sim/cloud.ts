/**
 * The optional cloud service (api/, docs/simulator/CLOUD.md): the Python reference engine running
 * thousands of draws and a Sobol sensitivity analysis, more than is comfortable in a browser tab.
 *
 * The page never depends on it. Without `VITE_SIM_API_URL` at build time the feature is off; if
 * the service doesn't answer, the panel that offers it stays hidden.
 */
import type { ScenarioRun, Summary } from "./montecarlo";

const BASE = String(import.meta.env.VITE_SIM_API_URL ?? "")
  .trim()
  .replace(/\/+$/, "");
export const cloudConfigured = BASE !== "";

const HEALTH_TIMEOUT_MS = 20_000; // a sleeping service takes a few seconds to wake
const DEEP_TIMEOUT_MS = 110_000; // the service itself gives up at 120 seconds

export interface SobolFactor {
  key: string;
  label: string;
  /** Share of the outcome's variance this input explains on its own. */
  first: number;
  first_interval: [number, number];
  /** The same, plus every interaction with other inputs it takes part in. */
  total: number;
  total_interval: [number, number];
}

export interface DeepResult {
  summary: Summary;
  monte_carlo: {
    draws: number;
    quantile_levels: number[];
    quantiles: Record<keyof Summary, number[]>;
    weekly: Record<"deaths" | "hospital" | "infections", number[][]>;
  };
  sobol: { output: string; n: number; evaluations: number; confidence: number; factors: SobolFactor[] };
  ms: number;
}

/** Why a request didn't produce a result; `retryAfter` is in seconds when the service gave one. */
export class CloudError extends Error {
  constructor(
    readonly kind: "busy" | "unavailable" | "rejected",
    readonly retryAfter: number | null = null,
  ) {
    super(kind);
  }
}

async function request(path: string, timeout: number, init: RequestInit = {}): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    return await fetch(`${BASE}${path}`, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

/** What the service says about itself: how many draws a deep analysis runs. */
export interface CloudService {
  draws: number;
}

let health: Promise<CloudService | null> | null = null;

/** The service if it answers, else null. Asked once per visit; the question also wakes a sleeping service. */
export function cloudService(): Promise<CloudService | null> {
  if (!cloudConfigured) return Promise.resolve(null);
  health ??= request("/health", HEALTH_TIMEOUT_MS)
    .then(async (r) => {
      const body = r.ok ? await r.json() : null;
      return body?.status === "ok" && body.deep_draws > 0 ? { draws: body.deep_draws as number } : null;
    })
    .catch(() => null);
  return health;
}

/** The scenario as the service expects it. JSON has no Infinity: "never" and "lifelong" travel as null. */
export function scenarioJson(run: ScenarioRun): string {
  return JSON.stringify(run);
}

export async function deepAnalysis(run: ScenarioRun, seed = 1): Promise<DeepResult> {
  let response: Response;
  try {
    response = await request("/analyze/deep", DEEP_TIMEOUT_MS, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: `{"scenario":${scenarioJson(run)},"seed":${seed}}`,
    });
  } catch {
    throw new CloudError("unavailable");
  }
  if (response.status === 429 || response.status === 503) {
    const wait = Number(response.headers.get("retry-after"));
    throw new CloudError("busy", Number.isFinite(wait) && wait > 0 ? wait : null);
  }
  if (!response.ok) throw new CloudError(response.status === 422 ? "rejected" : "unavailable");
  try {
    return (await response.json()) as DeepResult;
  } catch {
    throw new CloudError("unavailable");
  }
}

/** The part of an input's share that appears only in combination with other inputs. */
export function combinedShare(f: SobolFactor): number {
  return Math.max(0, f.total - f.first);
}

/** "about 40 seconds", "about 3 minutes", "about 2 hours": how long to wait before trying again. */
export function waitWords(seconds: number): string {
  if (seconds < 90) return `about ${Math.max(5, Math.round(seconds / 5) * 5)} seconds`;
  if (seconds < 5400) return `about ${Math.round(seconds / 60)} minutes`;
  const hours = Math.round(seconds / 3600);
  return `about ${hours} hour${hours === 1 ? "" : "s"}`;
}
