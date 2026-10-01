<script lang="ts" module>
  export interface RankItem {
    key: string;
    label: string;
    value: number;
    note?: string;
    emphasis?: boolean;
    /** True rank when the list skips rows (e.g. top 12 plus the selected country). */
    rank?: number;
  }
</script>

<script lang="ts">
  /** Horizontal ranking. Each row is a button when `onpick` is given (drill-through). */
  let {
    items,
    color,
    format,
    onpick,
    max,
  }: { items: RankItem[]; color: string; format: (v: number) => string; onpick?: (key: string) => void; max?: number } = $props();
  let vmax = $derived(max ?? Math.max(...items.map((i) => i.value), 1e-9));
</script>

<ol class="rank">
  {#each items as item, i (item.key)}
    <li class:emphasis={item.emphasis}>
      <svelte:element
        this={onpick ? "button" : "div"}
        class="row"
        onclick={onpick ? () => onpick(item.key) : undefined}
        aria-label={onpick ? `${item.label}: ${format(item.value)}. Open country page` : undefined}
        role={onpick ? undefined : "presentation"}
      >
        <span class="pos num">{item.rank ?? i + 1}</span>
        <span class="name">{item.label}{#if item.note}<span class="note">{item.note}</span>{/if}</span>
        <span class="bar"><span style:width={`${Math.max((item.value / vmax) * 100, 0.5)}%`} style:background={item.emphasis === false ? "var(--faint)" : color}></span></span>
        <span class="val num">{format(item.value)}</span>
      </svelte:element>
    </li>
  {/each}
</ol>

<style>
  .rank {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .row {
    display: grid;
    grid-template-columns: 22px minmax(110px, 1.1fr) minmax(60px, 1.4fr) 64px;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 5px 4px;
    border: 0;
    border-radius: 6px;
    background: none;
    text-align: left;
    font-size: 14px;
  }
  button.row {
    cursor: pointer;
  }
  button.row:hover {
    background: color-mix(in oklab, var(--ink) 6%, transparent);
  }
  .pos {
    color: var(--muted);
    font-size: 12.5px;
    text-align: right;
  }
  .name {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .note {
    color: var(--muted);
    font-size: 12.5px;
    margin-left: 6px;
  }
  @media (max-width: 560px) {
    .note {
      display: none;
    }
    .row {
      grid-template-columns: 22px minmax(90px, 1.2fr) minmax(40px, 1fr) 58px;
    }
  }
  .emphasis .name {
    font-weight: 700;
  }
  .bar {
    height: 10px;
    display: block;
  }
  .bar span {
    display: block;
    height: 100%;
    border-radius: 0 3px 3px 0;
  }
  .val {
    text-align: right;
    font-weight: 500;
  }
</style>
