<script lang="ts">
  /** The blank start: try a ready-made scenario, or build your own in three steps. */
  import { READY } from "../../lib/sim/scenarios";
  import { sim } from "../../lib/sim/store.svelte";
</script>

<section class="start" aria-labelledby="start-h">
  <h2 id="start-h">Try a ready-made scenario</h2>
  <p class="sub">Each one runs in a second. You can change anything afterwards.</p>
  <ul class="cards">
    {#each READY as s (s.id)}
      <li>
        <button class="card" onclick={() => sim.loadReady(s)}>
          <strong>{s.title}</strong>
          <span class="story">{s.story}</span>
          <span class="tags">
            {#each s.tags as t}<span>{t}</span>{/each}
          </span>
        </button>
      </li>
    {/each}
  </ul>

  <div class="own">
    <div>
      <h2>Or build your own</h2>
      <p class="sub">Three questions: where, what disease, and how the country responds.</p>
    </div>
    <button class="primary" onclick={() => sim.build()}>Start building →</button>
  </div>
</section>

<style>
  .sub {
    margin-top: 4px;
    color: var(--ink-2);
    font-size: 15px;
  }
  .cards {
    list-style: none;
    margin: 18px 0 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 14px;
  }
  .card {
    width: 100%;
    height: 100%;
    text-align: left;
    display: grid;
    align-content: start;
    gap: 8px;
    padding: 18px 18px 16px;
    background: var(--raise);
    border: 1px solid var(--hair-2);
    border-radius: 12px;
    cursor: pointer;
    transition:
      border-color 0.15s,
      transform 0.15s;
  }
  .card:hover {
    border-color: var(--ink-2);
    transform: translateY(-1px);
  }
  .card strong {
    font-size: 17px;
    line-height: 1.3;
  }
  .story {
    color: var(--ink-2);
    font-size: 14px;
    line-height: 1.45;
  }
  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 4px;
  }
  .tags span {
    font-size: 12px;
    color: var(--ink-2);
    border: 1px solid var(--hair-2);
    border-radius: 999px;
    padding: 1px 9px;
  }
  .own {
    margin-top: 40px;
    padding-top: 28px;
    border-top: 1px solid var(--hair);
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
  }
  .primary {
    background: var(--ink);
    color: var(--plane);
    border: 0;
    border-radius: 10px;
    padding: 12px 22px;
    font-size: 16px;
    font-weight: 500;
    cursor: pointer;
  }
  .primary:hover {
    opacity: 0.9;
  }
</style>
