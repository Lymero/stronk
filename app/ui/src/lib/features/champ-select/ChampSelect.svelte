<script lang="ts">
  import type { ChampSelectState, GameNames } from "../../backend/backend.ts";
  import { phase, role } from "../../ui/labels.ts";

  let { select, names }: { select: ChampSelectState | null; names: GameNames | null } = $props();

  /** The champion's name in the client's language, else its key in the data (`LeeSin`). */
  const champion = $derived(
    select?.champion ? (names?.champions[String(select.session?.champion_id)] ?? select.champion) : null,
  );
</script>

<section class="champ-select" aria-label="Champion select">
  {#if select?.session}
    <h2>{champion ?? "No champion yet"}</h2>
    <p class="meta">
      {select.role ? role(select.role) : "No role"} · {select.session.locked ? "Locked in" : "Hovering"} · {phase(select.session.phase)}
    </p>
  {:else}
    <p class="meta">Waiting for champion select</p>
  {/if}
</section>

<style>
  .champ-select {
    padding: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-surface);
  }
  h2 {
    margin: 0;
    font-size: var(--text-lg);
  }
  .meta {
    margin: var(--space-1) 0 0;
    color: var(--color-muted);
  }
</style>
