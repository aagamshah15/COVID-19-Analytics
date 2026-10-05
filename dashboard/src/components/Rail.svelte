<script lang="ts">
  /** Desktop navigation rail. Below 900px it is hidden and MobileNav takes over. */
  import { ICONS, THEMES } from "../lib/nav";
  import { app, COUNTRY_PAGES, PAGES } from "../lib/state/app.svelte";

  let current = $derived(THEMES.find((t) => t.id === app.theme) ?? THEMES[0]);
  const next = () => app.setTheme(THEMES[(THEMES.findIndex((t) => t.id === app.theme) + 1) % THEMES.length].id);
</script>

<nav class="rail" aria-label="Pages">
  <a class="mark" href={app.link("overview")} aria-label="COVID-19 Analytics home">
    <svg viewBox="0 0 40 28" aria-hidden="true">
      <g fill="var(--deaths)">
        {#each [8, 16, 25, 19, 13, 9, 5, 3] as h, i}<rect x={1 + i * 5} y={28 - h} width="3" height={h} rx="1" />{/each}
      </g>
    </svg>
  </a>
  {#each PAGES as p}
    <a href={app.link(p.id, COUNTRY_PAGES.includes(p.id) ? app.iso : null)} aria-current={app.page === p.id ? "page" : undefined} title={p.label}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[p.id]} /></svg>
      <span>{p.label}</span>
    </a>
  {/each}
  <button class="theme" onclick={next} aria-label={`Theme: ${current.label}. Switch theme`} title="Switch theme">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d={current.icon} /></svg>
    <span>{current.label}</span>
  </button>
</nav>

<style>
  .rail {
    background: var(--rail);
    padding: 18px 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    position: sticky;
    top: 0;
    height: 100vh;
    z-index: 10;
  }
  .mark {
    width: 40px;
    height: 28px;
    margin-bottom: 20px;
    display: block;
  }
  .mark svg {
    width: 40px;
    height: 28px;
    /* The logo is solid bars; keep the icon outline style below from applying to it. */
    stroke: none;
  }
  a:not(.mark),
  .theme {
    width: 72px;
    padding: 9px 0 7px;
    border-radius: 10px;
    color: var(--ink-2);
    text-decoration: none;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    font-size: 12px;
    line-height: 1.2;
    text-align: center;
    background: none;
    border: 0;
    cursor: pointer;
  }
  a svg,
  .theme svg {
    width: 22px;
    height: 22px;
    stroke: currentColor;
    fill: none;
    stroke-width: 1.7;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  a:hover,
  .theme:hover {
    color: var(--ink);
  }
  a[aria-current="page"] {
    color: var(--ink);
    background: var(--plane);
    font-weight: 500;
  }
  .theme {
    margin-top: auto;
  }
  @media (max-width: 900px) {
    .rail {
      display: none;
    }
  }
</style>
