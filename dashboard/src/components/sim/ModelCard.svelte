<script lang="ts">
  /** How the simulator works, what it learned, and how it did on data it never saw. */
  import { pct } from "../../lib/format";
  import type { Score } from "../../lib/sim/model";
  import { sim } from "../../lib/sim/store.svelte";

  let model = $derived(sim.model!);
  let c = $derived(model.constants);
  const REPO = "https://github.com/aagamshah15/COVID-19-Analytics/blob/main";
  const NAMES: Record<string, string> = {
    simulator: "Simulator",
    no_seasonality: "Simulator without seasonality",
    no_policy_effect: "Simulator without the lockdown effect",
    no_awareness: "Plain SEIR (no behaviour feedback)",
    simulator_no_features: "Simulator without country features",
    persistence: "Baseline: last month continues",
    continent_average: "Baseline: continent average",
    nearest_analog: "Baseline: most similar country",
  };
  const rows = (scores: Record<string, Score>) =>
    Object.entries(scores)
      .map(([k, s]) => ({ k, name: NAMES[k] ?? k, ...s }))
      .sort((a, b) => a.mae_weekly_deaths_pm - b.mae_weekly_deaths_pm);
  // Middle 80% of countries' awareness thresholds (reported deaths per million per day).
  let awareRange = $derived.by(() => {
    const v = model.countries
      .filter((x) => x.learned.awareness?.source === "calibrated")
      .map((x) => x.learned.awareness.value * c.awareness_deaths_pm)
      .sort((a, b) => a - b);
    return v.length ? [v[Math.floor(v.length * 0.1)], v[Math.floor(v.length * 0.9)]] : null;
  });
  let trained = $derived(new Date(model.trained_at).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }));
</script>

<div class="card">
  <ol class="how">
    <li>
      <strong>An epidemic engine.</strong> An age-structured SEIR model with vaccination, hospital care and deaths, run day by day in your browser
      (a two-year run takes under a millisecond). The same engine in Python fits the models, and the two agree to nine decimal places.
    </li>
    <li>
      <strong>Fitted to 137 countries' 2020 epidemics.</strong> Each country's transmission and severity, and three settings shared by all, were fitted to
      weekly deaths with the country's real lockdowns:
      <ul>
        <li>a strict lockdown (stringency 80) cuts transmission by <strong>{pct(1 - Math.exp(80 * c.npi_coef))}</strong>;</li>
        <li>
          people halve their contacts once reported deaths reach a country-specific level{#if awareRange}: <strong>{awareRange[0].toFixed(1)}–{awareRange[1].toFixed(1)}</strong>
            deaths per million a day for the middle 80% of countries{/if};
        </li>
        <li>transmission is <strong>{pct((2 * c.covid_seasonality) / (1 + c.covid_seasonality))}</strong> lower in summer than winter at temperate latitudes;</li>
        <li>restrictions lose about <strong>{pct(1 - c.fatigue_ratio)}</strong> of their effect after nine months.</li>
      </ul>
    </li>
    <li>
      <strong>Learned country effects.</strong> Ridge regressions map a country's characteristics (wealth, health system, age, density, …) to its fitted
      transmission, severity and tolerance of deaths, its share of deaths reported, and its vaccine uptake and speed. That's how an edited or made-up country
      gets its settings.
    </li>
    <li>
      <strong>Uncertainty.</strong> Each scenario is rerun 200 times with uncertain inputs drawn from the models' own error, giving the 50% and 90% ranges.
    </li>
  </ol>

  <div class="validation">
    <h3>How it did on data it never saw</h3>
    <p class="note">
      Mean absolute error in weekly deaths per million (lower is better). The rest of 2020: fitted on March–July, then predicting August–December. An
      unseen country: predicted from its characteristics alone.
    </p>
    <div class="tables">
      {#each [["Predicting the rest of 2020", model.validation.temporal_holdout], ["Predicting an unseen country", model.validation.cross_country_hindcast]] as [title, scores]}
        <table>
          <caption>{title}</caption>
          <tbody>
            {#each rows(scores as Record<string, Score>) as row}
              <tr class:ours={row.k === "simulator"}>
                <th scope="row">{row.name}</th>
                <td class="num">{row.mae_weekly_deaths_pm.toFixed(1)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/each}
    </div>
    <p class="reading">
      The simulator beats its own stripped-down versions, which shows each mechanism earns its place. Behaviour feedback matters most. But simple statistical
      baselines predict real death counts better, so this is a tool for comparing scenarios, not a forecaster. Epidemics amplify small differences in
      transmission, which is why the ranges are wide.
    </p>
  </div>
  <p class="links">
    Trained {trained} · model version {model.version} ·
    <a href={`${REPO}/docs/simulator/RESEARCH.md`}>Research brief and sources</a> ·
    <a href={`${REPO}/notebooks/03_simulator_models.ipynb`}>Model review notebook</a>
  </p>
</div>

<style>
  .card {
    display: grid;
    grid-template-columns: minmax(0, 7fr) minmax(0, 5fr);
    gap: 18px 48px;
    align-items: start;
  }
  .links {
    grid-column: 1 / -1;
  }
  .how {
    margin: 0;
    padding-left: 20px;
    max-width: 76ch;
    font-size: 15px;
  }
  .how li + li {
    margin-top: 10px;
  }
  .how ul {
    margin: 6px 0 0;
    padding-left: 18px;
  }
  h3 {
    margin: 0;
  }
  .note,
  .reading {
    margin-top: 6px;
    max-width: 76ch;
    color: var(--ink-2);
    font-size: 14px;
  }
  .reading {
    margin-top: 14px;
  }
  .tables {
    display: grid;
    gap: 20px;
    margin-top: 14px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13.5px;
  }
  caption {
    text-align: left;
    font-weight: 700;
    font-size: 14.5px;
    margin-bottom: 6px;
  }
  th,
  td {
    text-align: left;
    padding: 5px 8px 5px 0;
    border-bottom: 1px solid var(--hair);
    font-weight: 400;
  }
  td {
    text-align: right;
  }
  .ours th,
  .ours td {
    font-weight: 700;
  }
  .links {
    margin-top: 16px;
    font-size: 13.5px;
    color: var(--muted);
  }
  @media (max-width: 960px) {
    .card {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
