<script lang="ts">
  import { app, PAGES, type PageId, type Theme } from "../lib/state/app.svelte";

  const ICONS: Record<PageId, string> = {
    overview: "M3 20h18M6 16v-5M10 16V6M14 16v-8M18 16v-3",
    map: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3.6 9h16.8M3.6 15h16.8M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18",
    country: "M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11zM12 7.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z",
    vaccines: "m17 3 4 4M19 5l-9.5 9.5M8 12l4 4M6.5 13.5 4 16l4 4 2.5-2.5M3 21l2-2",
    hospitals: "M3 21V8l9-5 9 5v13M9 21v-6h6v6M12 7v4M10 9h4",
    outlook: "M3 17l5-5 4 3 4-6 5 4M16 9h5v5",
    data: "M12 3l8 3v6c0 4.5-3.4 8.2-8 9-4.6-.8-8-4.5-8-9V6zM9 12l2 2 4-4",
  };
  const THEMES: { id: Theme; label: string; icon: string }[] = [
    { id: "system", label: "Auto", icon: "M4 5h16v11H4zM8 20h8M12 16v4" },
    { id: "light", label: "Light", icon: "M12 4V2M12 22v-2M4 12H2M22 12h-2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z" },
    { id: "dark", label: "Dark", icon: "M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" },
  ];
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
    <a href={app.link(p.id, p.id === "country" ? app.iso : null)} aria-current={app.page === p.id ? "page" : undefined} title={p.label}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[p.id]} /></svg>
      <span class="long">{p.label}</span><span class="short">{p.short}</span>
    </a>
  {/each}
  <button class="theme" onclick={next} aria-label={`Theme: ${current.label}. Switch theme`} title="Switch theme">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d={current.icon} /></svg>
    <span class="theme-label">{current.label}</span>
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
  .short {
    display: none;
  }
  @media (max-width: 900px) {
    .rail {
      position: fixed;
      inset: auto 0 0 0;
      height: 64px;
      flex-direction: row;
      justify-content: space-around;
      padding: 4px 2px calc(4px + env(safe-area-inset-bottom));
      height: auto;
      border-top: 1px solid var(--hair);
    }
    .mark,
    .long {
      display: none;
    }
    .short {
      display: inline;
    }
    a:not(.mark),
    .theme {
      width: auto;
      flex: 1;
      min-width: 0;
      padding: 6px 0;
      font-size: 10.5px;
    }
    a svg,
    .theme svg {
      width: 20px;
      height: 20px;
    }
    .theme {
      margin-top: 0;
    }
  }
  /* Very narrow screens: shrink labels, then fall back to icons (names stay for screen readers). */
  @media (max-width: 380px) {
    a:not(.mark),
    .theme {
      font-size: 9.5px;
    }
    .theme-label {
      display: none;
    }
  }
  @media (max-width: 340px) {
    .short {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0 0 0 0);
      white-space: nowrap;
    }
    a:not(.mark),
    .theme {
      padding: 10px 0;
    }
  }
</style>
