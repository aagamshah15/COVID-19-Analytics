const int = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const one = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 0 });

export function count(n: number | null | undefined): string {
  return n === null || n === undefined || Number.isNaN(n) ? "–" : int.format(Math.round(n));
}

/** 7,020,833 -> "7.02 million"; 103,719 -> "103,719" */
export function big(n: number | null | undefined): { value: string; unit: string } {
  if (n === null || n === undefined) return { value: "–", unit: "" };
  if (Math.abs(n) >= 1e9) return { value: (n / 1e9).toFixed(2), unit: "billion" };
  if (Math.abs(n) >= 1e7) return { value: (n / 1e6).toFixed(0), unit: "million" };
  if (Math.abs(n) >= 1e6) return { value: (n / 1e6).toFixed(2), unit: "million" };
  return { value: int.format(Math.round(n)), unit: "" };
}

export function compact(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  const a = Math.abs(n);
  if (a >= 1e6) return `${(n / 1e6).toFixed(a >= 1e7 ? 0 : 1)}M`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(a >= 1e4 ? 0 : 1)}k`;
  if (a >= 10 || n === 0) return int.format(n);
  return n.toFixed(1);
}

export function pct(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  return `${(n * 100).toFixed(digits)}%`;
}

export function perMillion(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  return n >= 100 ? int.format(Math.round(n)) : one.format(n);
}

const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2021-01-24" -> "24 Jan 2021" */
export function day(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${Number(d)} ${months[Number(m) - 1]} ${y}`;
}

/** "2021-01-24" -> "Jan 2021" */
export function month(iso: string): string {
  const [y, m] = iso.split("-");
  return `${months[Number(m) - 1]} ${y}`;
}
