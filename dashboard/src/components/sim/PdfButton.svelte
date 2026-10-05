<script lang="ts">
  /** Builds and downloads the PDF report. The PDF code loads on first click, so it says so while it works. */
  let { make, label = "Download PDF", variant = "ghost" }: { make: () => Promise<void>; label?: string; variant?: "ghost" | "plain" } = $props();
  let busy = $state(false);
  let failed = $state(false);

  async function click() {
    busy = true;
    failed = false;
    try {
      await make();
    } catch (e) {
      console.error(e);
      failed = true;
    } finally {
      busy = false;
    }
  }
</script>

<button class={variant} onclick={click} disabled={busy} aria-live="polite">
  {busy ? "Preparing PDF…" : failed ? "Couldn't make the PDF. Try again" : label}
</button>

<style>
  button {
    border-radius: 10px;
    cursor: pointer;
  }
  button:disabled {
    cursor: progress;
    opacity: 0.7;
  }
  .ghost {
    background: none;
    border: 1px solid var(--hair-2);
    padding: 8px 14px;
    font-size: 14.5px;
  }
  .plain {
    border: 1px solid var(--hair-2);
    background: var(--plane);
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 14px;
  }
  .plain:hover,
  .ghost:hover {
    background: color-mix(in oklab, var(--ink) 6%, transparent);
  }
</style>
