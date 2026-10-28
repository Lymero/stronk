<script lang="ts">
  // The champion being played, with the build's actions next to it; before champion select, what
  // Stronk is waiting for (ADR-056).
  import type { Snippet } from "svelte";
  import type { ChampSelectState, GameNames } from "../../backend/backend.ts";
  import Facts from "../../ui/Facts.svelte";
  import Icon from "../../ui/Icon.svelte";
  import { type Icons, icon, phase, role } from "../../ui/labels.ts";

  let {
    select,
    names,
    icons,
    patch = null,
    noClient = null,
    actions,
  }: {
    select: ChampSelectState | null;
    names: GameNames | null;
    icons: Icons;
    /** The data's patch, said while waiting. */
    patch?: string | null;
    /** The client isn't open: the error's text, kept as a tooltip. */
    noClient?: string | null;
    /** The build's buttons, next to the champion. */
    actions?: Snippet;
  } = $props();

  /** The champion's name in the client's language, else its key in the data (`LeeSin`). */
  const champion = $derived(
    select?.champion ? (names?.champions[String(select.session?.champion_id)] ?? select.champion) : null,
  );
</script>

<section class="champ-select" class:locked={select?.session?.locked} aria-label="Champion select">
  {#if select?.session}
    <Icon src={icon(icons, "champions", select.session.champion_id)} name={champion ?? "?"} size="lg" round />
    <div class="who">
      <h2>{champion ?? "No champion yet"}</h2>
      <p class="meta">
        <Facts
          facts={[select.role ? role(select.role) : "No role", select.session.locked ? "Locked in" : "Hovering", phase(select.session.phase)]}
        />
      </p>
    </div>
    {#if actions}<div class="actions">{@render actions()}</div>{/if}
  {:else}
    <span class="avatar idle" class:pulse={!noClient} aria-hidden="true"></span>
    <div class="who">
      {#if noClient}
        <p class="waiting" role="status" title={noClient}>League of Legends isn't open</p>
        <p class="meta">Start it and Stronk connects on its own.</p>
      {:else}
        <p class="waiting">Waiting for champion select</p>
        {#if patch}<p class="meta">Builds for patch {patch} are ready.</p>{/if}
      {/if}
    </div>
  {/if}
</section>

<style>
  .champ-select {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3) var(--space-4);
    align-items: center;
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
  }
  .champ-select.locked {
    box-shadow: inset 4px 0 0 var(--color-accent);
  }
  .who {
    flex: 1 1 160px;
    min-width: 0;
  }
  .avatar.idle {
    flex: 0 0 auto;
    width: var(--icon-lg);
    height: var(--icon-lg);
    border-radius: 50%;
    background: var(--color-track);
  }
  .pulse {
    animation: pulse 2s ease-in-out infinite;
  }
  @keyframes pulse {
    50% {
      opacity: 0.5;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .pulse {
      animation: none;
    }
  }
  h2 {
    margin: 0;
    font-size: var(--text-lg);
    line-height: 1.2;
  }
  .waiting {
    margin: 0;
    font-weight: 600;
  }
  .meta {
    margin: 2px 0 0;
    color: var(--color-muted);
    font-size: var(--text-sm);
  }
  .actions {
    display: flex;
    flex: 0 0 auto;
    gap: var(--space-2);
    align-items: center;
    margin-left: auto;
  }
</style>
