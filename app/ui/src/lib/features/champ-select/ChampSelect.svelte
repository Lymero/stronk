<script lang="ts">
  import type { ChampSelectState } from "../../backend/backend.ts";

  let { select }: { select: ChampSelectState | null } = $props();
</script>

<section class="champ-select" aria-label="Champion select">
  {#if select?.session}
    <h2>{select.champion ?? "No champion yet"}</h2>
    <p class="meta">
      {select.role ?? "No role"} · {select.session.locked ? "Locked in" : "Hovering"} · {select.session.phase}
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
