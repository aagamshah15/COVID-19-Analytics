<script lang="ts">
  import type { Component } from "svelte";
  import MobileNav from "./components/MobileNav.svelte";
  import Rail from "./components/Rail.svelte";
  import { loadDataset } from "./lib/data/load";
  import type { Dataset } from "./lib/data/types";
  import { app, type PageId } from "./lib/state/app.svelte";
  import CountryPage from "./pages/Country.svelte";
  import DataPage from "./pages/Data.svelte";
  import Hospitals from "./pages/Hospitals.svelte";
  import MapPage from "./pages/Map.svelte";
  import Outlook from "./pages/Outlook.svelte";
  import Overview from "./pages/Overview.svelte";
  import Simulator from "./pages/Simulator.svelte";
  import Vaccines from "./pages/Vaccines.svelte";

  // One entry per page in PAGES (lib/state/app.svelte.ts). A future page plugs in here.
  const VIEWS: Record<PageId, Component<{ data: Dataset }>> = {
    overview: Overview,
    map: MapPage,
    country: CountryPage,
    vaccines: Vaccines,
    hospitals: Hospitals,
    outlook: Outlook,
    simulator: Simulator,
    data: DataPage,
  };

  let data = $state<Dataset | null>(null);
  let error = $state<string | null>(null);
  loadDataset()
    .then((d) => (data = d))
    .catch((e: Error) => (error = e.message));

  let View = $derived(VIEWS[app.page]);
</script>

<a
  class="skip"
  href={app.link(app.page, app.iso)}
  onclick={(e) => {
    // Hash routing owns the URL fragment, so move focus instead of jumping to #main.
    e.preventDefault();
    document.getElementById("main")?.focus();
  }}>Skip to content</a
>
<div class="app">
  <MobileNav />
  <Rail />
  <main id="main" tabindex="-1">
    {#if error}
      <div class="empty" role="alert">
        <h2>The data didn't load</h2>
        <p>{error}</p>
      </div>
    {:else if !data}
      <p class="loading" role="status">Loading four years of data…</p>
    {:else}
      {#key app.page}
        <View {data} />
      {/key}
    {/if}
    <footer class="site">
      <p>
        Built from <a href="https://ourworldindata.org/coronavirus">Our World in Data</a> and
        <a href="https://data.who.int/dashboards/covid19">WHO</a> data by an open pipeline.
        <a href="https://github.com/aagamshah15/COVID-19-Analytics">Source code and methods</a>.
      </p>
    </footer>
  </main>
</div>

<style>
  .app {
    display: grid;
    grid-template-columns: var(--rail-w) minmax(0, 1fr);
    min-height: 100vh;
  }
  main {
    padding: 28px clamp(16px, 4vw, 56px) 48px;
    max-width: 1400px;
    width: 100%;
    min-width: 0;
  }
  .loading {
    margin-top: 120px;
    color: var(--ink-2);
  }
  .skip {
    position: absolute;
    left: -999px;
    top: 8px;
    z-index: 30;
    background: var(--ink);
    color: var(--plane);
    padding: 8px 12px;
    border-radius: 8px;
  }
  .skip:focus {
    left: 8px;
  }
  .site {
    margin-top: 72px;
    padding-top: 18px;
    border-top: 1px solid var(--hair);
    color: var(--muted);
    font-size: 13px;
  }
  @media (max-width: 900px) {
    .app {
      grid-template-columns: minmax(0, 1fr);
    }
    main {
      padding-top: 20px;
      padding-bottom: 32px;
    }
  }
</style>
