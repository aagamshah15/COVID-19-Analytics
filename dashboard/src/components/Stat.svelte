<script lang="ts">
  let { value, unit = "", label, color }: { value: string; unit?: string; label: string; color?: string } = $props();
</script>

<div class="stat">
  <div class="v">{value}{#if unit}<small>{unit}</small>{/if}</div>
  <div class="l">{#if color}<span class="swatch" style:background={color}></span>{/if}{label}</div>
</div>

<style>
  .v {
    font-size: clamp(30px, 3vw, 40px);
    font-weight: 700;
    line-height: 1;
    letter-spacing: -0.01em;
  }
  small {
    font-size: 0.5em;
    font-weight: 500;
    color: var(--ink-2);
    margin-left: 5px;
    letter-spacing: 0;
  }
  .l {
    margin-top: 8px;
    color: var(--ink-2);
    font-size: 14.5px;
    max-width: 30ch;
  }
  .swatch {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 2px;
    margin-right: 7px;
  }
</style>
