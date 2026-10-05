<script lang="ts">
  import ChartFrame from "../components/ChartFrame.svelte";
  import Controls from "../components/Controls.svelte";
  import { inRegion, MIN_RANKING_POPULATION, regionLabel } from "../lib/data/aggregate";
  import type { Dataset, QualityCheck } from "../lib/data/types";
  import { day } from "../lib/format";
  import { app } from "../lib/state/app.svelte";

  let { data }: { data: Dataset } = $props();

  const REPO = "https://github.com/aagamshah15/COVID-19-Analytics";
  const LABELS: Record<string, string> = {
    daily_not_empty: "Data is present",
    coverage_reaches_end_date: "Data reaches the end of the window",
    coverage_starts_at_start_date: "Data starts at the beginning of the window",
    country_count: "Enough countries are covered",
    daily_keys_not_null: "Every row has a country and date",
    daily_unique_iso_date: "No duplicate country-days",
    weekly_unique_iso_week: "No duplicate country-weeks",
    flows_non_negative: "No negative daily counts",
    total_deaths_monotonic: "Cumulative deaths never decrease",
    negative_revisions_clipped: "No negative revisions in the source",
    vaccination_rate_plausible: "Vaccination stays below 110% of population",
    case_fatality_rate_lte_1: "Deaths never exceed cases (after cleaning)",
    cumulative_deaths_lte_cases: "Source never reports more deaths than cases",
    who_join_match_rate: "OWID and WHO records line up",
    death_reporting_active_at_end: "Every country still reports deaths at the end",
    vaccination_coverage_2022: "Vaccination data covers most of 2022",
  };
  const status = (c: QualityCheck) => (c.passed ? "pass" : c.severity === "error" ? "fail" : "warn");
  let checks = $derived([...data.quality.checks].sort((a, b) => ["fail", "warn", "pass"].indexOf(status(a)) - ["fail", "warn", "pass"].indexOf(status(b))));
  let errors = $derived(checks.filter((c) => status(c) === "fail").length);
  let warns = $derived(checks.filter((c) => status(c) === "warn").length);

  // Reporting coverage: one row per country (1M+ people), hatched where deaths weren't reported.
  let coverage = $derived(
    data.countries
      .filter((c) => (c.population ?? 0) >= MIN_RANKING_POPULATION && inRegion(c, app.region))
      .map((c) => {
        const d = data.series[c.iso].d;
        const gaps: [number, number][] = [];
        let start = -1;
        d.forEach((v, i) => {
          if (v === null && start < 0) start = i;
          if ((v !== null || i === d.length - 1) && start >= 0) {
            gaps.push([start, v === null ? i : i - 1]);
            start = -1;
          }
        });
        const reported = d.filter((v) => v !== null).length;
        return { c, gaps, share: reported / d.length };
      })
      .sort((a, b) => a.share - b.share || a.c.name.localeCompare(b.c.name)),
  );
  let full = $derived(coverage.filter((r) => r.share === 1).length);
  let partial = $derived(coverage.filter((r) => r.share < 1));

  let width = $state(0);
  let W = $derived(Math.max(width, 300));
  let labelW = $derived(W < 560 ? 96 : 150);
  const rowH = 14;
  let cell = $derived((W - labelW) / data.weeks.length);
  let years = $derived(data.weeks.map((w, i) => ({ w, i })).filter(({ w, i }) => i === 0 || w.slice(0, 4) !== data.weeks[i - 1].slice(0, 4)));

  let STAGES = $derived([
    { name: "Ingest", note: "OWID, WHO, World Bank" },
    { name: "Transform", note: "Clean, weekly, gaps" },
    { name: "Quality gate", note: `${data.quality.checks.length} checks` },
    { name: "Warehouse", note: "DuckDB star schema" },
    { name: "SQL pack", note: "22 named queries" },
    { name: "Forecast", note: "Backtested model" },
    { name: "Dashboard", note: "This site" },
  ]);
</script>

<Controls {data} showMeasure={false} />

<header class="hero">
  <h1>Can you trust these numbers?</h1>
  <p class="lede">
    Every figure on this site comes from an open, tested pipeline. Here is what it checks, where the data comes from, and where the data runs out.
  </p>
</header>

<div class="section">
  <h2>From source files to this page</h2>
  <ol class="pipeline">
    {#each STAGES as s, i}
      <li><span class="step num">{i + 1}</span><strong>{s.name}</strong><span>{s.note}</span></li>
    {/each}
  </ol>
  <p class="muted small">
    The pipeline rebuilds weekly from the live sources. A failed download stops the run rather than reusing old data. <a href={REPO}>Read the code</a>
    or the <a href={`${REPO}/blob/main/sql/analytical_queries.sql`}>SQL query pack</a>.
  </p>
</div>

<div class="section grid-7-5">
  <div>
    <h2>Quality gate: {errors === 0 ? "passed" : `${errors} failed`}, with {warns} warnings</h2>
    <p class="sub">Errors stop the pipeline. Warnings are known quirks of the source data, handled and reported here.</p>
    <ul class="checks">
      {#each checks as c}
        {@const st = status(c)}
        <li class={st}>
          <span class="badge" aria-hidden="true">
            {#if st === "pass"}
              <svg viewBox="0 0 16 16"><path d="m3.5 8.5 3 3 6-7" /></svg>
            {:else if st === "warn"}
              <svg viewBox="0 0 16 16"><path d="M8 4v5M8 11.5v.5" /></svg>
            {:else}
              <svg viewBox="0 0 16 16"><path d="m4.5 4.5 7 7M11.5 4.5l-7 7" /></svg>
            {/if}
          </span>
          <div>
            <strong>{LABELS[c.name] ?? c.name}</strong>
            <span class="status">{st === "pass" ? "Passed" : st === "warn" ? "Warning" : "Failed"}</span>
            <p>Found {c.observed}. Expected {c.expectation}.</p>
          </div>
        </li>
      {/each}
    </ul>
  </div>

  <div>
    <h2>Sources</h2>
    {#each Object.entries(data.quality.sources) as [name, src]}
      <div class="source">
        <h3>{name === "owid" ? "Our World in Data" : name === "who" ? "World Health Organization" : name}</h3>
        <p><a href={src.url}>{src.url.replace(/^https:\/\//, "").slice(0, 60)}…</a></p>
        <dl>
          <dt>Downloaded</dt><dd>{day(src.fetched_at_utc.slice(0, 10))}</dd>
          <dt>Size</dt><dd class="num">{(src.bytes / 1e6).toFixed(1)} MB</dd>
          <dt>Fingerprint</dt><dd class="num" title={src.sha256}>{src.sha256.slice(0, 16)}…</dd>
        </dl>
      </div>
    {:else}
      <p class="muted">Source details appear after the pipeline downloads fresh data.</p>
    {/each}
    <p class="muted small">This page was generated {day(data.quality.generatedAt.slice(0, 10))}.</p>

    <h2 class="limits">Limits of the data</h2>
    <ul class="limits-list">
      <li>Reported deaths understate the true toll. The WHO estimates 14.9 million excess deaths in 2020–2021, against 5.4 million reported.</li>
      <li>Recorded cases depend on testing, which collapsed from 2022, so deaths per case is least reliable in 2023.</li>
      <li>Only {data.countries.filter((c) => data.series[c.iso].h.some((v) => v !== null) || data.series[c.iso].icu.some((v) => v !== null)).length} countries published COVID-19 hospital figures.</li>
      <li>Vaccination comparisons between countries are associations, not measured effects.</li>
    </ul>
  </div>
</div>

<div class="section">
  <ChartFrame
    title={`${partial.length} of ${coverage.length} countries have gaps in death reporting`}
    subtitle={`Countries with 1 million or more people${app.region === "all" ? "" : ` in ${regionLabel(app.region)}`}. Hatched weeks were not reported and count as missing, never zero. ${full} countries reported every week and are not shown.`}
    query="q20_reporting_coverage"
    columns={[
      { key: "name", label: "Country" },
      { key: "share", label: "Weeks reported", numeric: true, format: (v) => `${Math.round((v as number) * 100)}%` },
    ]}
    rows={coverage.map((r) => ({ name: r.c.name, share: r.share }))}
  >
    <div class="cov" bind:clientWidth={width}>
      {#if width && partial.length}
        <svg viewBox={`0 0 ${W} ${partial.length * rowH + 24}`} width={W} height={partial.length * rowH + 24} role="img" aria-label="Reporting coverage by country and week. The table view lists each country's share of weeks reported.">
          <defs>
            <pattern id="cov-hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="5" stroke="var(--faint)" stroke-width="1.5" />
            </pattern>
          </defs>
          {#each partial as r, i (r.c.iso)}
            <a href={app.link("country", r.c.iso)} aria-label={`${r.c.name}: ${Math.round(r.share * 100)}% of weeks reported`}>
              <text class="axis-label row" x={labelW - 8} y={i * rowH + rowH - 3} text-anchor="end">{r.c.name.length > 20 ? `${r.c.name.slice(0, 19)}…` : r.c.name}</text>
              <rect x={labelW} y={i * rowH + 2} width={W - labelW} height={rowH - 3} fill="color-mix(in oklab, var(--deaths) 60%, var(--plane))" />
              {#each r.gaps as [a, b]}
                <rect x={labelW + a * cell} y={i * rowH + 2} width={(b - a + 1) * cell} height={rowH - 3} fill="var(--plane)" />
                <rect x={labelW + a * cell} y={i * rowH + 2} width={(b - a + 1) * cell} height={rowH - 3} fill="url(#cov-hatch)" />
              {/each}
            </a>
          {/each}
          {#each years as y}
            <line x1={labelW + y.i * cell} x2={labelW + y.i * cell} y1="0" y2={partial.length * rowH + 4} stroke="var(--hair-2)" />
            <text class="axis-label" x={labelW + y.i * cell + 3} y={partial.length * rowH + 18}>{y.w.slice(0, 4)}</text>
          {/each}
        </svg>
      {:else if width}
        <p class="empty">Every country in this region reported deaths every week.</p>
      {/if}
    </div>
  </ChartFrame>
</div>

<style>
  .hero {
    margin-top: 34px;
  }
  .sub {
    color: var(--ink-2);
    font-size: 14.5px;
    margin-top: 4px;
  }
  .small {
    font-size: 13px;
    margin-top: 12px;
  }
  .pipeline {
    list-style: none;
    padding: 0;
    margin: 16px 0 0;
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: 0;
  }
  .pipeline li {
    position: relative;
    padding: 12px 14px 12px 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 14px;
  }
  .pipeline li:not(:last-child)::after {
    content: "";
    position: absolute;
    top: 23px;
    left: 30px;
    right: 6px;
    border-top: 1px solid var(--hair-2);
  }
  .pipeline span:not(.step) {
    color: var(--ink-2);
    font-size: 13px;
  }
  .step {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 1px solid var(--hair-2);
    display: grid;
    place-items: center;
    font-size: 12px;
    color: var(--ink-2);
    margin-bottom: 6px;
    background: var(--plane);
    position: relative;
    z-index: 1;
  }
  .checks {
    list-style: none;
    margin: 16px 0 0;
    padding: 0;
  }
  .checks li {
    display: flex;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px solid var(--hair);
  }
  .checks p {
    color: var(--ink-2);
    font-size: 13.5px;
    margin-top: 2px;
  }
  .checks strong {
    font-weight: 500;
  }
  .status {
    margin-left: 8px;
    font-size: 12.5px;
    color: var(--ink-2);
  }
  .badge {
    flex: none;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    margin-top: 1px;
  }
  .badge svg {
    width: 14px;
    height: 14px;
    fill: none;
    stroke: #fff;
    stroke-width: 2.2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .pass .badge {
    background: var(--good);
  }
  .warn .badge {
    background: var(--warning);
  }
  .warn .badge svg {
    stroke: #3d2a00;
  }
  .fail .badge {
    background: var(--critical);
  }
  .source {
    margin-top: 16px;
    padding-bottom: 14px;
    border-bottom: 1px solid var(--hair);
  }
  .source p {
    font-size: 13.5px;
    margin-top: 2px;
    word-break: break-all;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 2px 14px;
    margin: 8px 0 0;
    font-size: 13.5px;
  }
  dt {
    color: var(--muted);
  }
  dd {
    margin: 0;
  }
  .limits {
    margin-top: 36px;
  }
  .limits-list {
    margin: 12px 0 0;
    padding-left: 18px;
    color: var(--ink-2);
    font-size: 14.5px;
  }
  .limits-list li + li {
    margin-top: 8px;
  }
  .cov {
    width: 100%;
  }
  .cov svg {
    display: block;
  }
  .cov a:hover .row {
    fill: var(--ink);
    text-decoration: underline;
  }
  .row {
    fill: var(--ink-2);
  }
  @media (max-width: 900px) {
    .pipeline {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .pipeline li::after {
      display: none;
    }
  }
</style>
