/**
 * App state: route + global filters, mirrored in the URL hash so every view is linkable.
 *   #/<page>[/<ISO3>]?from=YYYY-MM-DD&to=YYYY-MM-DD&region=<key>&measure=pm|abs
 * Adding a page = one entry in PAGES (see App.svelte for the component map).
 */

export const PAGES = [
  { id: "overview", label: "Overview", short: "Overview" },
  { id: "map", label: "Where it hit", short: "Map" },
  { id: "country", label: "Country", short: "Country" },
  { id: "vaccines", label: "Vaccines", short: "Vaccines" },
  { id: "hospitals", label: "Hospitals", short: "Hospitals" },
  { id: "outlook", label: "Outlook", short: "Outlook" },
  { id: "data", label: "Data", short: "Data" },
] as const;

export type PageId = (typeof PAGES)[number]["id"];
export type Measure = "pm" | "abs";
export type Theme = "system" | "light" | "dark";

export const START = "2020-01-01";
export const END = "2023-12-31";
export const DEFAULT_COUNTRY = "USA";

export const PRESETS = [
  { label: "Whole pandemic", from: START, to: END },
  { label: "2020", from: "2020-01-01", to: "2020-12-31" },
  { label: "2021", from: "2021-01-01", to: "2021-12-31" },
  { label: "2022", from: "2022-01-01", to: "2022-12-31" },
  { label: "2023", from: "2023-01-01", to: "2023-12-31" },
];

const isPage = (p: string): p is PageId => PAGES.some((x) => x.id === p);

function parse(hash: string) {
  const [path, query = ""] = hash.replace(/^#\/?/, "").split("?");
  const [page, iso] = path.split("/");
  const q = new URLSearchParams(query);
  const date = (v: string | null, fallback: string) => (v && /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : fallback);
  return {
    page: isPage(page) ? page : ("overview" as PageId),
    iso: iso && /^[A-Z_]{3,8}$/.test(iso) ? iso : null,
    from: date(q.get("from"), START),
    to: date(q.get("to"), END),
    region: q.get("region") || "all",
    measure: (q.get("measure") === "abs" ? "abs" : "pm") as Measure,
  };
}

class AppState {
  page = $state<PageId>("overview");
  iso = $state<string | null>(null);
  from = $state(START);
  to = $state(END);
  region = $state("all");
  measure = $state<Measure>("pm");
  theme = $state<Theme>("system");

  constructor() {
    if (typeof window === "undefined") return;
    this.read();
    window.addEventListener("hashchange", () => this.read());
    try {
      const t = localStorage.getItem("theme");
      if (t === "light" || t === "dark") this.theme = t;
    } catch {
      /* storage unavailable: stay on system theme */
    }
  }

  private read() {
    const s = parse(location.hash);
    this.page = s.page;
    this.iso = s.iso;
    this.from = s.from;
    this.to = s.to;
    this.region = s.region;
    this.measure = s.measure;
  }

  private href(page: PageId, iso: string | null, filters: Partial<Pick<AppState, "from" | "to" | "region" | "measure">> = {}) {
    const f = { from: this.from, to: this.to, region: this.region, measure: this.measure, ...filters };
    const q = new URLSearchParams();
    if (f.from !== START) q.set("from", f.from);
    if (f.to !== END) q.set("to", f.to);
    if (f.region !== "all") q.set("region", f.region);
    if (f.measure !== "pm") q.set("measure", f.measure);
    const qs = q.toString();
    return `#/${page}${iso ? `/${iso}` : ""}${qs ? `?${qs}` : ""}`;
  }

  /** Link to a page, keeping the current filters. */
  link(page: PageId, iso: string | null = null) {
    return this.href(page, iso);
  }

  go(page: PageId, iso: string | null = null) {
    location.hash = this.href(page, iso);
    if (page !== this.page) window.scrollTo({ top: 0 });
  }

  set(filters: Partial<Pick<AppState, "from" | "to" | "region" | "measure">>) {
    const next = this.href(this.page, this.iso, filters);
    history.replaceState(null, "", next);
    Object.assign(this, filters);
  }

  setTheme(theme: Theme) {
    this.theme = theme;
    if (theme === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
    try {
      if (theme === "system") localStorage.removeItem("theme");
      else localStorage.setItem("theme", theme);
    } catch {
      /* storage unavailable: theme still applies for this visit */
    }
  }

  get isWholePeriod() {
    return this.from === START && this.to === END;
  }
}

export const app = new AppState();
