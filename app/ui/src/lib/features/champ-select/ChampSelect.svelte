<script lang="ts">
  import type { ChampSelectState, GameNames } from "../../backend/backend.ts";
  import { phase, role } from "../../ui/labels.ts";

  let { select, names }: { select: ChampSelectState | null; names: GameNames | null } = $props();

  /** The champion's name in the client's language, else its key in the data (`LeeSin`). */
  const champion = $derived(
    select?.champion ? (names?.champions[String(select.session?.champion_id)] ?? select.champion) : null,
  );
</script>

<section class="champ-select" class:locked={select?.session?.locked} aria-label="Champion select">
  {#if select?.session}
    <span class="avatar" aria-hidden="true">{(champion ?? "?").charAt(0)}</span>
    <div>
      <h2>{champion ?? "No champion yet"}</h2>
      <p class="meta">
        {select.role ? role(select.role) : "No role"} · {select.session.locked ? "Locked in" : "Hovering"} · {phase(select.session.phase)}
      </p>
    </div>
  {:else}
    <span class="avatar idle" aria-hidden="true"></span>
    <p class="meta">Waiting for champion select</p>
  {/if}
</section>

<style>
  .champ-select {
    display: flex;
    gap: var(--space-4);
    align-items: center;
    padding: var(--space-4);
    border: 1px solid var(--color-border);
    border-left: 4px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
  }
  .champ-select.locked {
    border-left-color: var(--color-accent);
  }
  .avatar {
    display: grid;
    flex: 0 0 auto;
    place-items: center;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: var(--color-accent-bg);
    color: var(--color-accent);
    font-size: var(--text-xl);
    font-weight: 700;
  }
  .avatar.idle {
    width: 40px;
    height: 40px;
    background: var(--color-track);
  }
  h2 {
    margin: 0;
    font-size: var(--text-xl);
    line-height: 1.1;
  }
  .meta {
    margin: var(--space-1) 0 0;
    color: var(--color-muted);
  }
</style>
