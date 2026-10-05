<script lang="ts" module>
  export type Provenance = "data" | "calibrated" | "observed" | "predicted" | "assumption" | "edited" | "learned" | "literature";

  export const PROVENANCE_TEXT: Record<Provenance, string> = {
    data: "from data",
    calibrated: "calibrated",
    observed: "observed",
    predicted: "predicted",
    assumption: "assumption",
    edited: "edited",
    learned: "learned",
    literature: "from studies",
  };

  export const PROVENANCE_HELP: Record<Provenance, string> = {
    data: "This country's published value (OWID or World Bank).",
    calibrated: "Fitted so the model replays this country's 2020 epidemic.",
    observed: "Measured from this country's 2021-2022 vaccine rollout or excess deaths.",
    predicted: "Predicted from the country's characteristics by a model trained on other countries.",
    assumption: "Not available from data: a stated assumption you can change.",
    edited: "You changed this from the data value.",
    learned: "Estimated from 2020-2023 data across countries.",
    literature: "A published estimate for this pathogen (sources in the research brief).",
  };
</script>

<script lang="ts">
  /** A labelled slider that says where its value came from, with a reset once edited. */
  interface Props {
    label: string;
    value: number;
    min: number;
    max: number;
    step?: number;
    log?: boolean;
    format: (v: number) => string;
    onchange: (v: number) => void;
    provenance?: Provenance;
    onreset?: () => void;
    hint?: string;
    disabled?: boolean;
  }
  let { label, value, min, max, step, log = false, format, onchange, provenance, onreset, hint, disabled = false }: Props = $props();

  const id = `f-${Math.random().toString(36).slice(2, 8)}`;
  // Log sliders move through orders of magnitude evenly: position 0-1000 maps to min..max.
  let position = $derived(log ? (1000 * Math.log(Math.max(value, min) / min)) / Math.log(max / min) : value);
  function input(e: Event) {
    const raw = Number((e.currentTarget as HTMLInputElement).value);
    onchange(log ? min * Math.exp((raw / 1000) * Math.log(max / min)) : raw);
  }
</script>

<div class="field" class:disabled>
  <div class="top">
    <label for={id}>{label}</label>
    <output for={id} class="num">{format(value)}</output>
  </div>
  <input
    {id}
    type="range"
    min={log ? 0 : min}
    max={log ? 1000 : max}
    step={log ? 1 : (step ?? "any")}
    value={position}
    oninput={input}
    {disabled}
    aria-valuetext={format(value)}
  />
  {#if provenance || hint}
    <div class="meta">
      {#if provenance}
        <span class="badge" class:edited={provenance === "edited"} class:assumption={provenance === "assumption"} title={PROVENANCE_HELP[provenance]}>
          {PROVENANCE_TEXT[provenance]}
        </span>
      {/if}
      {#if provenance === "edited" && onreset}
        <button class="reset" onclick={onreset} aria-label={`Reset ${label} to the data value`}>Reset</button>
      {/if}
      {#if hint}<span class="hint">{hint}</span>{/if}
    </div>
  {/if}
</div>

<style>
  .field {
    padding: 10px 0 12px;
    border-bottom: 1px solid var(--hair);
  }
  .field.disabled {
    opacity: 0.5;
  }
  .top {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 12px;
  }
  label {
    font-size: 14px;
    color: var(--ink);
  }
  output {
    font-size: 14px;
    font-weight: 700;
    white-space: nowrap;
  }
  input[type="range"] {
    width: 100%;
    margin: 8px 0 2px;
    accent-color: var(--ink);
    cursor: pointer;
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 10px;
    font-size: 12px;
    color: var(--muted);
  }
  .badge {
    border: 1px solid var(--hair-2);
    border-radius: 999px;
    padding: 0 8px;
    line-height: 18px;
    color: var(--ink-2);
    cursor: help;
  }
  .badge.edited {
    border-color: var(--ink-2);
    color: var(--ink);
  }
  .badge.assumption {
    border-style: dashed;
  }
  .reset {
    background: none;
    border: 0;
    padding: 0;
    font-size: 12px;
    color: var(--ink);
    text-decoration: underline;
    text-underline-offset: 2px;
    cursor: pointer;
  }
  .hint {
    color: var(--muted);
  }
</style>
