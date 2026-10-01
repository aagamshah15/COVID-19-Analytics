<script lang="ts">
  import ChartFrame from "../components/ChartFrame.svelte";
  import CountrySearch from "../components/CountrySearch.svelte";
  import Stat from "../components/Stat.svelte";
  import BarChart from "../lib/charts/BarChart.svelte";
  import LineChart from "../lib/charts/LineChart.svelte";
  import type { Dataset } from "../lib/data/types";
  import { count, day, pct } from "../lib/format";
  import { app } from "../lib/state/app.svelte";

  let { data }: { data: Dataset } = $props();

  const HISTORY = 26;
  let report = $derived(data.model);
  let bt = $derived(report.backtest);
  let focus = $derived(Object.keys(report.focus_countries));
  let forecastable = $derived(data.countries.filter((c) => data.forecast[c.iso]));
  let iso = $derived(app.iso && data.forecast[app.iso] ? app.iso : focus[0]);
  let country = $derived(data.byIso.get(iso)!);

  function fan(code: string) {
    const fc = data.forecast[code];
    const s = data.series[code];
    const hist = data.weeks.slice(-HISTORY);
    const x = [...hist, ...fc.points.map((p) => p.week)];
    const pad = (k: number) => Array<number | null>(k).fill(null);
    const actual = [...s.d.slice(-HISTORY), ...pad(fc.points.length)];
    // The forecast line starts at the last actual week so the two connect.
    const last = s.d[s.d.length - 1];
    const pred = [...pad(HISTORY - 1), last, ...fc.points.map((p) => p.p)];
    return {
      x,
      origin: HISTORY - 1,
      series: [
        { id: "a", label: "Reported deaths", values: actual, color: "var(--deaths)" },
        { id: "p", label: "Forecast", values: pred, color: "var(--deaths)", role: "context" as const, dashed: true },
      ],
      band: {
        lo: [...pad(HISTORY - 1), last, ...fc.points.map((p) => p.lo)],
        hi: [...pad(HISTORY - 1), last, ...fc.points.map((p) => p.hi)],
        color: "var(--deaths)",
        label: "80% range",
      },
      fc,
    };
  }
  let main = $derived(fan(iso));
  let lastPoint = $derived(main.fc.points[main.fc.points.length - 1]);
  let horizons = $derived(
    Object.entries(bt.by_horizon_focus).map(([h, s]) => ({
      key: h,
      value: s.skill_vs_naive,
      tick: `${h}`,
      title: `${h} week${h === "1" ? "" : "s"} ahead: skill vs naive`,
      label: true,
    })),
  );
  let byCountry = $derived(
    Object.entries(bt.by_country)
      .map(([code, s]) => ({ code, name: report.focus_countries[code] ?? code, ...s }))
      .sort((a, b) => (b.skill_vs_naive ?? 0) - (a.skill_vs_naive ?? 0)),
  );
  let wins = $derived(byCountry.filter((r) => (r.skill_vs_naive ?? 0) > 0).length);
  let bestH = $derived(Object.entries(bt.by_horizon_focus).sort((a, b) => (b[1].skill_vs_naive ?? -9) - (a[1].skill_vs_naive ?? -9))[0][0]);
  const signed = (v: number) => `${v > 0 ? "+" : ""}${Math.round(v * 100)}%`;
</script>

<header class="hero">
  <h1>What the model expected next</h1>
  <p class="lede">
    An {report.horizon_weeks}-week forecast of weekly deaths from {day(report.origin_date)}, the last week of data. It's judged against the simplest
    possible forecast, "next week looks like this week", over {bt.folds} backtests from {day(bt.first_cutoff)}.
  </p>
</header>

<div class="stats">
  <Stat value={signed(bt.all_countries.skill_vs_naive ?? 0)} label="lower error than the naive forecast, across all countries" />
  <Stat value={signed(bt.focus_countries.skill_vs_naive ?? 0)} label={`lower error on the ${focus.length} focus countries`} />
  <Stat value={count(forecastable.length)} label="countries forecast" />
  <Stat value={count(report.not_forecast_reporting_stopped.length)} label="skipped because reporting had stopped" />
</div>

<div class="section">
  <div class="picker">
    <div class="seg" role="group" aria-label="Focus countries">
      {#each focus as code}
        <button aria-pressed={iso === code} onclick={() => app.go("outlook", code)}>{report.focus_countries[code]}</button>
      {/each}
    </div>
    <CountrySearch countries={forecastable} onpick={(c) => app.go("outlook", c.iso)} placeholder="Another country" label="Forecast another country" />
  </div>

  <ChartFrame
    title={`${country.name}: about ${count(lastPoint.p)} deaths expected in the week ending ${day(lastPoint.week)}`}
    subtitle={`Last ${HISTORY} weeks of reported deaths, then the forecast with its 80% range. The range widens with each week ahead.`}
    query="q21_forecast_outlook"
    columns={[
      { key: "week", label: "Week ending" },
      { key: "h", label: "Weeks ahead", numeric: true },
      { key: "p", label: "Forecast", numeric: true, format: (v) => count(v as number) },
      { key: "lo", label: "80% low", numeric: true, format: (v) => count(v as number) },
      { key: "hi", label: "80% high", numeric: true, format: (v) => count(v as number) },
    ]}
    rows={main.fc.points.map((p) => ({ ...p }))}
  >
    {#snippet legend()}
      <span><span class="key" style:border-color="var(--deaths)"></span>Reported</span>
      <span><span class="key dashed" style:border-color="var(--deaths)"></span>Forecast</span>
      <span><span class="band"></span>80% range</span>
    {/snippet}
    <LineChart
      x={main.x}
      series={main.series}
      band={main.band}
      height={300}
      format={count}
      hatchGaps={false}
      marker={{ index: main.origin, label: "Forecast starts" }}
      ariaLabel={`${country.name}: weekly deaths for the last ${HISTORY} weeks and the ${report.horizon_weeks}-week forecast`}
    />
  </ChartFrame>
</div>

<div class="section">
  <ChartFrame title="The five focus countries" subtitle="The countries with the most deaths among those still reporting. Each panel has its own scale." query="q21_forecast_outlook">
    <div class="multiples">
      {#each focus as code}
        {@const f = fan(code)}
        <button class="panel" class:current={code === iso} onclick={() => app.go("outlook", code)}>
          <h3>{report.focus_countries[code]}</h3>
          <LineChart x={f.x} series={f.series} band={f.band} height={130} format={count} hatchGaps={false} compact ariaLabel={`${report.focus_countries[code]} forecast`} />
        </button>
      {/each}
    </div>
  </ChartFrame>
</div>

<div class="section grid-2">
  <ChartFrame
    title={`The model helps most around ${bestH} weeks ahead`}
    subtitle="Skill against the naive forecast on the focus countries, by weeks ahead. Above zero means lower error than the naive forecast."
    source="Backtest in reports/forecast_metrics.json"
    columns={[
      { key: "h", label: "Weeks ahead", numeric: true },
      { key: "skill", label: "Skill vs naive", numeric: true, format: (v) => signed(v as number) },
      { key: "mae", label: "Model error (deaths/week)", numeric: true, format: (v) => count(v as number) },
      { key: "naive", label: "Naive error", numeric: true, format: (v) => count(v as number) },
    ]}
    rows={Object.entries(bt.by_horizon_focus).map(([h, s]) => ({ h, skill: s.skill_vs_naive, mae: s.mae_deaths, naive: s.mae_naive_deaths }))}
  >
    <BarChart bars={horizons} color="var(--deaths)" negativeColor="var(--faint)" height={220} min={-0.1} max={0.25} ticks={[-0.1, 0, 0.1, 0.2]} format={signed} ariaLabel="Forecast skill by weeks ahead" />
  </ChartFrame>

  <ChartFrame
    title={`It beats the naive forecast for ${wins} of the ${byCountry.length} focus countries`}
    subtitle="Average over all horizons. WAPE is total absolute error as a share of total deaths."
    source="Backtest in reports/forecast_metrics.json"
  >
    <table>
      <thead><tr><th>Country</th><th class="r">Skill vs naive</th><th class="r">WAPE</th><th class="r">Weeks tested</th></tr></thead>
      <tbody>
        {#each byCountry as r}
          <tr>
            <td><button class="link-button" onclick={() => app.go("outlook", r.code)}>{r.name}</button></td>
            <td class="r num" class:neg={(r.skill_vs_naive ?? 0) < 0}>{signed(r.skill_vs_naive ?? 0)}</td>
            <td class="r num">{pct(r.wape, 0)}</td>
            <td class="r num">{r.n}</td>
          </tr>
        {/each}
      </tbody>
    </table>
    <p class="explain">India's reported deaths include occasional dumps of backlogged deaths that no model can anticipate.</p>
  </ChartFrame>
</div>

<div class="section grid-2">
  <div class="method">
    <h2>How the forecast works</h2>
    <ul>
      <li>One model is trained on {report.training_universe}, using weekly deaths per million on a log scale. A single country has too few weeks to learn from alone.</li>
      <li>It predicts the change from the current week, then blends that 50/50 with "no change". Weekly deaths move slowly, so this damped approach beats predicting the level directly.</li>
      <li>Each horizon has its own model using only what was known on the forecast date: recent deaths, recent cases and their growth, vaccination and boosters, median age and hospital beds.</li>
      <li>The 80% range comes from the model's own backtest errors at each horizon.</li>
    </ul>
  </div>
  <div class="method">
    <h2>Not forecast</h2>
    <p>
      {report.not_forecast_reporting_stopped.length} countries had stopped reporting deaths by {day(report.origin_date)}. Forecasting them would mean
      forecasting zero, so they are left out:
    </p>
    <p class="muted list">{report.not_forecast_reporting_stopped.join(", ")}.</p>
  </div>
</div>

<style>
  .hero {
    margin-top: 34px;
  }
  .stats {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 28px;
    margin-top: 30px;
  }
  .picker {
    display: flex;
    flex-wrap: wrap;
    gap: 12px 18px;
    align-items: center;
    margin-bottom: 22px;
  }
  .picker .seg {
    max-width: 100%;
    overflow-x: auto;
  }
  .key {
    display: inline-block;
    width: 16px;
    border-top: 2px solid;
    vertical-align: middle;
    margin-right: 6px;
  }
  .key.dashed {
    border-top-style: dashed;
  }
  .band {
    display: inline-block;
    width: 16px;
    height: 10px;
    background: color-mix(in oklab, var(--deaths) 22%, var(--plane));
    vertical-align: middle;
    margin-right: 6px;
  }
  .multiples {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 18px;
  }
  .panel {
    background: none;
    border: 0;
    padding: 6px;
    text-align: left;
    border-radius: 8px;
    cursor: pointer;
    min-width: 0;
  }
  .panel:hover {
    background: color-mix(in oklab, var(--ink) 4%, transparent);
  }
  .panel.current h3 {
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .panel h3 {
    font-size: 14px;
    font-weight: 500;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }
  th {
    text-align: left;
    font-weight: 500;
    color: var(--ink-2);
    border-bottom: 1px solid var(--hair-2);
    padding: 7px 4px;
  }
  td {
    padding: 7px 4px;
    border-bottom: 1px solid var(--hair);
  }
  .r {
    text-align: right;
  }
  .neg {
    color: var(--ink-2);
  }
  .explain {
    margin-top: 12px;
    color: var(--ink-2);
    font-size: 14px;
  }
  .method ul {
    margin: 12px 0 0;
    padding-left: 18px;
    color: var(--ink-2);
    max-width: 62ch;
  }
  .method li + li {
    margin-top: 8px;
  }
  .method p {
    margin-top: 12px;
    color: var(--ink-2);
    max-width: 62ch;
  }
  .list {
    font-size: 14px;
  }
  @media (max-width: 1100px) {
    .multiples {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }
  @media (max-width: 900px) {
    .stats {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
  @media (max-width: 560px) {
    .multiples {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
