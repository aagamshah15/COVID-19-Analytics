/**
 * Talks to the simulation worker. Each kind of request keeps only the newest one in flight:
 * while a visitor drags a slider, stale ensembles are dropped instead of queuing up.
 * Falls back to running on the main thread where workers aren't available.
 */
import { type EnsembleResult, ensemble, type ScenarioRun, sensitivity, type TornadoBar } from "./montecarlo";
import type { Request } from "./sim.worker";

type Kind = Request["kind"];
type Result<K extends Kind> = K extends "ensemble" ? EnsembleResult : { base: number; bars: TornadoBar[] };

export class SimClient {
  private worker: Worker | null = null;
  private next = 1;
  private latest: Partial<Record<Kind, number>> = {};
  private pending = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();

  constructor() {
    if (typeof Worker === "undefined") return;
    this.worker = new Worker(new URL("./sim.worker.ts", import.meta.url), { type: "module" });
    this.worker.onmessage = (event: MessageEvent<{ id: number; result?: unknown; error?: string }>) => {
      const { id, result, error } = event.data;
      const waiter = this.pending.get(id);
      this.pending.delete(id);
      if (!waiter) return;
      if (error) waiter.reject(new Error(error));
      else waiter.resolve(result);
    };
  }

  /** Resolves with the result, or null if a newer request of the same kind superseded it. */
  async request<K extends Kind>(kind: K, run: ScenarioRun, draws = 200, seed = 1): Promise<Result<K> | null> {
    const id = this.next++;
    this.latest[kind] = id;
    let result: unknown;
    if (!this.worker) {
      result = kind === "ensemble" ? ensemble(run, draws, seed) : sensitivity(run);
    } else {
      const message: Request = kind === "ensemble" ? { id, kind, run, draws, seed } : { id, kind: "sensitivity", run };
      result = await new Promise((resolve, reject) => {
        this.pending.set(id, { resolve, reject });
        this.worker!.postMessage(message);
      });
    }
    return this.latest[kind] === id ? (result as Result<K>) : null;
  }

  dispose() {
    this.worker?.terminate();
    this.pending.clear();
  }
}
