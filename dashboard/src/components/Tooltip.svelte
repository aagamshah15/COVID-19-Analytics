<script lang="ts" module>
  export interface TipRow {
    color?: string;
    label: string;
    value: string;
    dashed?: boolean;
  }
</script>

<script lang="ts">
  /** A single tooltip: the headline value leads, series rows follow (line keys, not boxes). */
  interface Props {
    x: number;
    y: number;
    width: number;
    visible: boolean;
    title?: string;
    rows: TipRow[];
  }
  let { x, y, width, visible, title, rows }: Props = $props();
  const W = 220;
  let left = $derived(x + 14 + W > width ? Math.max(0, x - W - 14) : x + 14);
</script>

<div class="tip" class:visible style:left={`${left}px`} style:top={`${y}px`} role="status" aria-live="polite">
  {#if title}<div class="title">{title}</div>{/if}
  {#each rows as r}
    <div class="row">
      {#if r.color}<span class="key" class:dashed={r.dashed} style:border-color={r.color}></span>{/if}
      <span class="label">{r.label}</span>
      <strong>{r.value}</strong>
    </div>
  {/each}
</div>

<style>
  .tip {
    position: absolute;
    z-index: 4;
    width: 220px;
    pointer-events: none;
    background: var(--raise);
    border: 1px solid var(--hair-2);
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 13px;
    line-height: 1.4;
    box-shadow: var(--shadow);
    opacity: 0;
    transition: opacity 0.1s;
  }
  .visible {
    opacity: 1;
  }
  .title {
    color: var(--ink-2);
    margin-bottom: 4px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .label {
    color: var(--ink-2);
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  strong {
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .key {
    width: 14px;
    border-top: 2px solid;
    flex: none;
  }
  .key.dashed {
    border-top-style: dashed;
  }
</style>
