/**
 * Sequential ramp between the surface-adjacent base (--seq-0), the metric hue and its
 * mode-specific far end (--<metric>-hi). Lightness moves monotonically away from the surface
 * in both themes; resolved by the browser, so it follows the active theme with no JS.
 */
export function rampColor(metric: "deaths" | "vax" | "hosp", t: number): string {
  const p = Math.max(0, Math.min(1, t));
  if (p <= 0.6) return `color-mix(in oklab, var(--${metric}) ${Math.round(18 + (p / 0.6) * 82)}%, var(--seq-0))`;
  return `color-mix(in oklab, var(--${metric}-hi) ${Math.round(((p - 0.6) / 0.4) * 100)}%, var(--${metric}))`;
}

export const RAMP_STEPS = [0, 0.2, 0.4, 0.6, 0.8, 1];
