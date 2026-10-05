/// <reference lib="webworker" />
/**
 * Runs ensembles and sensitivity analyses off the main thread, so sliders stay smooth while the
 * Monte Carlo draws compute.
 */
import { ensemble, type ScenarioRun, sensitivity } from "./montecarlo";

export type Request =
  | { id: number; kind: "ensemble"; run: ScenarioRun; draws: number; seed: number }
  | { id: number; kind: "sensitivity"; run: ScenarioRun };

self.onmessage = (event: MessageEvent<Request>) => {
  const req = event.data;
  try {
    const result = req.kind === "ensemble" ? ensemble(req.run, req.draws, req.seed) : sensitivity(req.run);
    self.postMessage({ id: req.id, result });
  } catch (error) {
    self.postMessage({ id: req.id, error: (error as Error).message });
  }
};
