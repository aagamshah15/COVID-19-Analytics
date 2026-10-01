<script lang="ts">
  import type { Snippet } from "svelte";
  import DataTable, { type Column } from "./DataTable.svelte";

  interface Props {
    title: string;
    subtitle?: string;
    query?: string;
    source?: string;
    columns?: Column[];
    rows?: Record<string, unknown>[];
    children: Snippet;
    legend?: Snippet;
  }

  let { title, subtitle, query, source = "OWID and WHO", columns, rows, children, legend }: Props = $props();
  let view = $state<"chart" | "table">("chart");
  const id = `frame-${Math.random().toString(36).slice(2, 9)}`;
</script>

<figure class="frame" aria-labelledby={`${id}-t`}>
  <h2 id={`${id}-t`}>{title}</h2>
  {#if subtitle}<p class="sub">{subtitle}</p>{/if}
  {#if legend}<div class="legend">{@render legend()}</div>{/if}
  <div class="body">
    {#if view === "chart" || !columns}
      {@render children()}
    {:else}
      <DataTable {columns} rows={rows ?? []} caption={title} />
    {/if}
  </div>
  <figcaption>
    <span>Source: {source}.{#if query}&nbsp;Query <code>{query}</code>{/if}</span>
    {#if columns}
      <span class="seg small" role="group" aria-label="View">
        <button aria-pressed={view === "chart"} onclick={() => (view = "chart")}>Chart</button>
        <button aria-pressed={view === "table"} onclick={() => (view = "table")}>Table</button>
      </span>
    {/if}
  </figcaption>
</figure>

<style>
  .frame {
    margin: 0;
    min-width: 0;
  }
  .sub {
    color: var(--ink-2);
    font-size: 14.5px;
    margin-top: 4px;
    max-width: 72ch;
  }
  .legend {
    margin-top: 10px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px 18px;
    font-size: 13px;
    color: var(--ink-2);
  }
  .body {
    margin-top: 14px;
    position: relative;
  }
  figcaption {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    margin-top: 10px;
    padding-top: 8px;
    border-top: 1px solid var(--hair);
    font-size: 12.5px;
    color: var(--muted);
  }
  code {
    font-size: 12px;
    color: var(--ink-2);
  }
</style>
