<script lang="ts">
  /**
   * Phone navigation (below 900px; the desktop rail takes over above that): a slim top bar with
   * the page name, and a menu button that opens a drawer listing every page plus the theme.
   * The drawer is a native <dialog>, so focus is trapped and Escape closes it.
   */
  import { CLOSE_ICON, ICONS, MENU_ICON, THEMES } from "../lib/nav";
  import { app, PAGES } from "../lib/state/app.svelte";

  let current = $derived(PAGES.find((p) => p.id === app.page) ?? PAGES[0]);
  let theme = $derived(THEMES.find((t) => t.id === app.theme) ?? THEMES[0]);
  const nextTheme = () => app.setTheme(THEMES[(THEMES.findIndex((t) => t.id === app.theme) + 1) % THEMES.length].id);
  const href = (id: (typeof PAGES)[number]["id"]) => app.link(id, id === "country" ? app.iso : null);

  let drawer = $state<HTMLDialogElement>();
  const open = () => drawer?.showModal();
  const close = () => drawer?.close();

  // Close the drawer once a page is chosen.
  $effect(() => {
    void app.page;
    drawer?.close();
  });
</script>

<header class="topbar">
  <button class="icon" aria-label="Open menu" aria-haspopup="dialog" onclick={open}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d={MENU_ICON} /></svg>
  </button>
  <span class="title">{current.label}</span>
  <button class="icon" onclick={nextTheme} aria-label={`Theme: ${theme.label}. Switch theme`}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d={theme.icon} /></svg>
  </button>
</header>

<dialog class="drawer" bind:this={drawer} aria-label="Pages" onclick={(e) => e.target === drawer && close()}>
  <div class="drawer-head">
    <svg class="mark" viewBox="0 0 40 28" aria-hidden="true">
      <g fill="var(--deaths)">{#each [8, 16, 25, 19, 13, 9, 5, 3] as h, i}<rect x={1 + i * 5} y={28 - h} width="3" height={h} rx="1" />{/each}</g>
    </svg>
    <span>COVID-19 Analytics</span>
    <button class="icon" aria-label="Close menu" onclick={close}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d={CLOSE_ICON} /></svg>
    </button>
  </div>
  <ul>
    {#each PAGES as p}
      <li>
        <a href={href(p.id)} aria-current={app.page === p.id ? "page" : undefined}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[p.id]} /></svg>{p.label}
        </a>
      </li>
    {/each}
  </ul>
  <div class="theme-pick" role="group" aria-label="Theme">
    {#each THEMES as t}
      <button aria-pressed={app.theme === t.id} onclick={() => app.setTheme(t.id)}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d={t.icon} /></svg>{t.label}
      </button>
    {/each}
  </div>
</dialog>

<style>
  svg {
    width: 20px;
    height: 20px;
    stroke: currentColor;
    fill: none;
    stroke-width: 1.7;
    stroke-linecap: round;
    stroke-linejoin: round;
    flex: none;
  }
  svg.mark {
    width: 30px;
    height: 21px;
    stroke: none;
  }
  .topbar,
  dialog {
    display: none;
  }
  @media (max-width: 900px) {
    .topbar {
      display: flex;
    }
    dialog[open] {
      display: block;
    }
  }
  .topbar {
    position: sticky;
    top: 0;
    z-index: 10;
    align-items: center;
    gap: 8px;
    padding: 8px;
    background: color-mix(in oklab, var(--plane) 92%, transparent);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--hair);
  }
  .title {
    flex: 1;
    min-width: 0;
    font-weight: 700;
    font-size: 17px;
  }
  .icon {
    width: 40px;
    height: 40px;
    display: grid;
    place-items: center;
    border: 0;
    border-radius: 10px;
    background: none;
    color: var(--ink);
    cursor: pointer;
  }
  .icon:hover {
    background: color-mix(in oklab, var(--ink) 7%, transparent);
  }
  .drawer {
    position: fixed;
    inset: 0 auto 0 0;
    margin: 0;
    height: 100%;
    max-height: none;
    width: min(300px, 84vw);
    border: 0;
    background: var(--raise);
    color: var(--ink);
    padding: 12px 12px calc(12px + env(safe-area-inset-bottom));
    box-shadow: var(--shadow);
  }
  .drawer[open] {
    animation: slide 0.18s ease-out;
  }
  .drawer::backdrop {
    background: rgb(0 0 0 / 0.4);
  }
  .drawer-head {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 4px 0 14px 6px;
    font-weight: 700;
  }
  .drawer-head span {
    flex: 1;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li a {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 13px 10px;
    border-radius: 10px;
    color: var(--ink);
    text-decoration: none;
    font-size: 16px;
  }
  li a[aria-current="page"] {
    background: color-mix(in oklab, var(--ink) 7%, transparent);
    font-weight: 700;
  }
  .theme-pick {
    display: flex;
    gap: 6px;
    margin-top: 14px;
    padding-top: 14px;
    border-top: 1px solid var(--hair);
  }
  .theme-pick button {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 9px 0;
    border: 1px solid var(--hair-2);
    border-radius: 8px;
    background: none;
    color: var(--ink-2);
    font-size: 14px;
    cursor: pointer;
  }
  .theme-pick button[aria-pressed="true"] {
    background: var(--ink);
    color: var(--plane);
    border-color: var(--ink);
  }
  .theme-pick svg {
    width: 16px;
    height: 16px;
  }
  @keyframes slide {
    from {
      transform: translateX(-24px);
      opacity: 0;
    }
  }
</style>
