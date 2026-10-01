<script lang="ts" module>
  export interface Column {
    key: string;
    label: string;
    format?: (v: unknown, row: Record<string, unknown>) => string;
    numeric?: boolean;
  }
</script>

<script lang="ts">
  let { columns, rows, caption }: { columns: Column[]; rows: Record<string, unknown>[]; caption: string } = $props();
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex (scrollable region must be keyboard-focusable) -->
<div class="wrap" tabindex="0" role="region" aria-label={`${caption}: table`}>
  <table>
    <caption class="sr-only">{caption}</caption>
    <thead>
      <tr>
        {#each columns as c}<th scope="col" class:numeric={c.numeric}>{c.label}</th>{/each}
      </tr>
    </thead>
    <tbody>
      {#each rows as row}
        <tr>
          {#each columns as c}
            <td class:numeric={c.numeric}>{c.format ? c.format(row[c.key], row) : (row[c.key] ?? "–")}</td>
          {/each}
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .wrap {
    max-height: 420px;
    overflow: auto;
    border: 1px solid var(--hair);
    border-radius: 8px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13.5px;
  }
  th {
    position: sticky;
    top: 0;
    background: var(--plane);
    text-align: left;
    font-weight: 500;
    color: var(--ink-2);
    padding: 8px 12px;
    border-bottom: 1px solid var(--hair-2);
  }
  td {
    padding: 6px 12px;
    border-bottom: 1px solid var(--hair);
  }
  .numeric {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  tr:last-child td {
    border-bottom: 0;
  }
</style>
