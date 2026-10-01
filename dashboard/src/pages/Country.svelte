<script lang="ts">
  import ChartFrame from "../components/ChartFrame.svelte";
  import Controls from "../components/Controls.svelte";
  import Stat from "../components/Stat.svelte";
  import LineChart from "../lib/charts/LineChart.svelte";
  import RankBars from "../lib/charts/RankBars.svelte";
  import { aggregateWeekly, countryPeriod, MIN_RANKING_POPULATION, regionCountries, WHO_REGIONS, weekRange } from "../lib/data/aggregate";
  import type { Dataset } from "../lib/data/types";
  import { big, count, day, perMillion, pct } from "../lib/format";
  import { app, DEFAULT_COUNTRY } from "../lib/state/app.svelte";

  let { data }: { data: Dataset } = $props();

  let country = $derived(data.byIso.get(app.iso ?? DEFAULT_COUNTRY) ?? data.byIso.get(DEFAULT_COUNTRY)!);
  let s = $derived(data.series[country.iso]);
  let range = $derived(weekRange(data.weeks, app.from, app.to));
  let period = $derived(countryPeriod(data, country, range));
  let continentCountries = $derived(country.continent ? regionCountries(data, `continent:${country.continent}`) : []);
  let continentAgg = $derived(aggregateWeekly(data, continentCountries));
  let worldAgg = $derived(aggregateWeekly(data, data.countries));
  let pop = $derived(big(country.population));
  let abs = $derived(app.measure === "abs");
  let deaths = $derived(big(period.deaths));

  let curve = $derived(
    abs
      ? [{ id: "c", label: country.name, values: s.d, color: "var(--deaths)" }]
      : [
          { id: "c", label: country.name, values: s.dpm, color: "var(--deaths)" },
          { id: "r", label: country.continent ?? "Continent", values: continentAgg.map((w) => w.dpm), color: "var(--muted)", role: "context" as const },
          { id: "w", label: "World", values: worldAgg.map((w) => w.dpm), color: "var(--faint)", role: "faint" as const, dashed: true },
        ],
  );

  let hasVax = $derived(s.v.some((v) => v !== null && v > 0));
  let rollout = $derived([
    { id: "v1", label: "At least one dose", short: "1+ dose", values: s.v1, color: "color-mix(in oklab, var(--vax) 50%, var(--plane))", role: "context" as const },
    { id: "v", label: "Fully vaccinated", short: "Full", values: s.v, color: "var(--vax)" },
    { id: "vb", label: "Boosters per person", short: "Boosters", values: s.vb, color: "var(--vax)", role: "context" as const, dashed: true },
  ]);

  let publishing = $derived(data.countries.filter((c) => data.series[c.iso].h.some((v) => v !== null) || data.series[c.iso].icu.some((v) => v !== null)).length);
  let hasHosp = $derived(s.h.some((v) => v !== null) || s.icu.some((v) => v !== null));
  let peakOcc = $derived(Math.max(...s.occ.map((v) => v ?? 0)));
  let hosp = $derived([
    { id: "h", label: "In hospital", short: "Hospital", values: s.h, color: "var(--hosp)" },
    { id: "icu", label: "In intensive care", short: "ICU", values: s.icu, color: "var(--hosp)", role: "context" as const, dashed: true },
  ]);

  let peers = $derived.by(() => {
    const rows = continentCountries
      .filter((c) => (c.population ?? 0) >= MIN_RANKING_POPULATION || c.iso === country.iso)
      .map((c) => ({ c, v: countryPeriod(data, c, range).deathsPerMillion }))
      .filter((r): r is { c: typeof country; v: number } => r.v !== null)
      .sort((a, b) => b.v - a.v);
    const pos = rows.findIndex((r) => r.c.iso === country.iso);
    const shown = rows.slice(0, 12).map((r, i) => ({ ...r, rank: i + 1 }));
    if (pos >= 12) shown.push({ ...rows[pos], rank: pos + 1 });
    return {
      pos,
      total: rows.length,
      items: shown.map((r) => ({ key: r.c.iso, label: r.c.name, value: r.v, rank: r.rank, emphasis: r.c.iso === country.iso })),
    };
  });

  let reported = $derived(s.d.map((v) => v !== null));
  let firstGap = $derived(reported.findIndex((r, i) => !r && reported.slice(0, i).some(Boolean)));
  let forecast = $derived(data.forecast[country.iso]);
  let periodText = $derived(app.isWholePeriod ? "from 2020 to 2023" : `from ${day(data.weeks[range[0]])} to ${day(data.weeks[range[1]])}`);
</script>

<Controls {data} showRegion={false} showCountry />

<header class="hero">
  <h1>{country.name}</h1>
  <p class="lede">
    {[country.continent, country.whoRegion ? `WHO ${WHO_REGIONS[country.whoRegion] ?? country.whoRegion} region` : null].filter(Boolean).join(", ")}.
    Population {pop.value}{pop.unit ? ` ${pop.unit}` : ""}. Figures below cover {periodText}.
  </p>
</header>

<div class="stats">
  <Stat value={deaths.value} unit={deaths.unit} label="deaths reported" color="var(--deaths)" />
  <Stat value={perMillion(period.deathsPerMillion)} label="deaths per million people" color="var(--deaths)" />
  <Stat
    value={period.peakWeek === null ? "–" : abs ? count(s.d[period.peakWeek]) : perMillion(period.peakWeeklyDpm)}
    label={period.peakWeek === null ? "no weekly deaths reported" : `${abs ? "deaths" : "per million"} in the deadliest week, ending ${day(data.weeks[period.peakWeek])}`}
    color="var(--deaths)"
  />
  <Stat value={pct(period.vaccination)} label="fully vaccinated by the end of the period" color="var(--vax)" />
</div>

<div class="section">
  <ChartFrame
    title={abs ? `Weekly deaths in ${country.name}` : `How ${country.name}'s waves compare with ${country.continent ?? "its region"} and the world`}
    subtitle={`${abs ? "Reported deaths per week" : "Reported deaths per million people per week"}. Hatched weeks were not reported${app.isWholePeriod ? "" : "; the selected period is unshaded"}.`}
    columns={[
      { key: "week", label: "Week ending" },
      { key: "d", label: "Deaths", numeric: true, format: (v) => (v === null ? "not reported" : count(v as number)) },
      { key: "dpm", label: "Per million", numeric: true, format: (v) => (v === null ? "–" : perMillion(v as number)) },
    ]}
    rows={data.weeks.map((w, i) => ({ week: w, d: s.d[i], dpm: s.dpm[i] }))}
  >
    {#snippet legend()}
      {#each curve as c}
        <span><span class="key" class:dashed={c.dashed} style:border-color={c.color}></span>{c.label}</span>
      {/each}
    {/snippet}
    <LineChart
      x={data.weeks}
      series={curve}
      height={300}
      format={abs ? count : perMillion}
      highlight={app.isWholePeriod ? null : range}
      ariaLabel={`Weekly deaths ${abs ? "" : "per million "}in ${country.name}`}
    />
  </ChartFrame>
</div>

<div class="section grid-2">
  <ChartFrame
    title={hasVax ? "Vaccination rollout" : "No vaccination data"}
    subtitle="Share of the population. Boosters are doses per person, so they can exceed the fully vaccinated line."
    columns={[
      { key: "week", label: "Week ending" },
      { key: "v1", label: "One dose", numeric: true, format: (v) => pct(v as number) },
      { key: "v", label: "Fully vaccinated", numeric: true, format: (v) => pct(v as number) },
      { key: "vb", label: "Boosters per person", numeric: true, format: (v) => pct(v as number) },
    ]}
    rows={data.weeks.map((w, i) => ({ week: w, v1: s.v1[i], v: s.v[i], vb: s.vb[i] })).filter((r) => r.week >= "2020-12-01")}
  >
    {#if hasVax}
      <LineChart x={data.weeks} series={rollout} height={240} yMax={1} format={(v) => pct(v)} hatchGaps={false} directLabels ariaLabel={`Vaccination rollout in ${country.name}`} />
    {:else}
      <p class="empty">{country.name} hasn't published vaccination figures to OWID.</p>
    {/if}
  </ChartFrame>

  <ChartFrame
    title={hasHosp ? `Hospital strain${peakOcc ? `: up to ${pct(peakOcc)} of all beds` : ""}` : "No hospital data"}
    subtitle="COVID-19 patients per million people. The headline is the peak share of the country's total hospital beds they occupied."
    query={hasHosp ? "q15_peak_covid_bed_occupancy" : undefined}
  >
    {#if hasHosp}
      <LineChart x={data.weeks} series={hosp} height={240} format={perMillion} hatchGaps={false} directLabels ariaLabel={`COVID-19 hospital and ICU patients per million in ${country.name}`} />
    {:else}
      <p class="empty">
        {country.name} doesn't publish COVID-19 hospital figures; only {publishing} countries do. See <a href={app.link("hospitals")}>the countries that do</a>.
      </p>
    {/if}
  </ChartFrame>
</div>

<div class="section grid-2">
  <ChartFrame
    title={peers.pos >= 0 ? `${country.name} ranks ${peers.pos + 1} of ${peers.total} in ${country.continent}` : `Peers in ${country.continent}`}
    subtitle="Deaths per million people in the selected period, countries with at least 1 million people. Select one to switch."
  >
    <RankBars items={peers.items} color="var(--deaths)" format={perMillion} onpick={(iso) => app.go("country", iso)} />
  </ChartFrame>

  <div>
    <ChartFrame
      title={firstGap > 0 ? `Death reporting stopped after ${day(data.weeks[firstGap - 1])}` : "Death reporting"}
      subtitle="Each cell is a week. Hatched weeks were not reported, so they are excluded from totals rather than counted as zero."
      query="q20_reporting_coverage"
    >
      <div class="strip" role="img" aria-label={`${reported.filter(Boolean).length} of ${reported.length} weeks reported`}>
        {#each reported as r, i}<span class:gap={!r} title={`${day(data.weeks[i])}: ${r ? "reported" : "not reported"}`}></span>{/each}
      </div>
      <p class="muted small">{reported.filter(Boolean).length} of {reported.length} weeks reported.</p>
    </ChartFrame>

    {#if forecast}
      <div class="outlook">
        <h3>Outlook</h3>
        <p>
          The model expects about {count(forecast.points[forecast.points.length - 1].p)} deaths in the week ending {day(forecast.points[forecast.points.length - 1].week)}
          (80% range {count(forecast.points[forecast.points.length - 1].lo)} to {count(forecast.points[forecast.points.length - 1].hi)}).
        </p>
        <a href={app.link("outlook", country.iso)}>See the forecast</a>
      </div>
    {/if}
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
  .strip {
    display: grid;
    grid-template-columns: repeat(104, minmax(0, 1fr));
    gap: 1px;
  }
  .strip span {
    height: 14px;
    background: var(--deaths);
    border-radius: 1px;
  }
  .strip span.gap {
    background: repeating-linear-gradient(45deg, var(--faint) 0 1.5px, transparent 1.5px 4px);
  }
  .small {
    font-size: 13px;
    margin-top: 8px;
  }
  .outlook {
    margin-top: 32px;
    padding-top: 20px;
    border-top: 1px solid var(--hair);
  }
  .outlook p {
    color: var(--ink-2);
    margin: 6px 0 8px;
    max-width: 52ch;
  }
  .outlook a {
    font-weight: 500;
    font-size: 14px;
  }
  @media (max-width: 900px) {
    .stats {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
