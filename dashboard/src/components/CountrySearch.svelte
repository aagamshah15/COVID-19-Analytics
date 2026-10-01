<script lang="ts">
  import type { Country } from "../lib/data/types";

  /** Accessible combobox: type to filter, arrows to move, Enter to choose. */
  let { countries, onpick, placeholder = "Find a country", label = "Find a country" }: {
    countries: Country[];
    onpick: (c: Country) => void;
    placeholder?: string;
    label?: string;
  } = $props();

  let query = $state("");
  let open = $state(false);
  let active = $state(0);
  const id = `cs-${Math.random().toString(36).slice(2, 8)}`;

  let matches = $derived.by(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const starts = countries.filter((c) => c.name.toLowerCase().startsWith(q) || c.iso.toLowerCase() === q);
    const contains = countries.filter((c) => !starts.includes(c) && c.name.toLowerCase().includes(q));
    return [...starts, ...contains].slice(0, 8);
  });

  function pick(c: Country) {
    onpick(c);
    query = "";
    open = false;
  }

  function onkeydown(e: KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      open = true;
      active = Math.min(active + 1, matches.length - 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      active = Math.max(active - 1, 0);
    } else if (e.key === "Enter" && matches[active]) {
      e.preventDefault();
      pick(matches[active]);
    } else if (e.key === "Escape") {
      open = false;
    }
  }
</script>

<div class="cs">
  <input
    type="search"
    role="combobox"
    aria-label={label}
    aria-expanded={open && matches.length > 0}
    aria-controls={`${id}-list`}
    aria-activedescendant={open && matches[active] ? `${id}-${active}` : undefined}
    aria-autocomplete="list"
    {placeholder}
    bind:value={query}
    oninput={() => {
      open = true;
      active = 0;
    }}
    onfocus={() => (open = true)}
    onblur={() => setTimeout(() => (open = false), 120)}
    {onkeydown}
  />
  {#if open && matches.length}
    <ul id={`${id}-list`} role="listbox">
      {#each matches as c, i}
        <li
          id={`${id}-${i}`}
          role="option"
          aria-selected={i === active}
          onpointerdown={(e) => {
            e.preventDefault();
            pick(c);
          }}
          onpointerenter={() => (active = i)}
        >
          {c.name}<span>{c.continent ?? ""}</span>
        </li>
      {/each}
    </ul>
  {:else if open && query.trim()}
    <div class="none" role="status">No country matches “{query}”.</div>
  {/if}
</div>

<style>
  .cs {
    position: relative;
  }
  input {
    width: 220px;
  }
  ul,
  .none {
    position: absolute;
    z-index: 20;
    top: calc(100% + 4px);
    left: 0;
    min-width: 260px;
    margin: 0;
    padding: 4px;
    list-style: none;
    background: var(--raise);
    border: 1px solid var(--hair-2);
    border-radius: 8px;
    box-shadow: var(--shadow);
    font-size: 14px;
  }
  .none {
    padding: 10px 12px;
    color: var(--ink-2);
  }
  li {
    padding: 7px 10px;
    border-radius: 6px;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    gap: 12px;
  }
  li span {
    color: var(--muted);
    font-size: 12.5px;
  }
  li[aria-selected="true"] {
    background: color-mix(in oklab, var(--ink) 8%, transparent);
  }
  @media (max-width: 560px) {
    input {
      width: 100%;
    }
    .cs {
      flex: 1 1 100%;
    }
  }
</style>
