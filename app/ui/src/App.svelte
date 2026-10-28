<script lang="ts">
  import PlanView from "./lib/features/build-view/PlanView.svelte";
  import ChampSelect from "./lib/features/champ-select/ChampSelect.svelte";
  import Settings from "./lib/features/settings/Settings.svelte";
  import type { App } from "./lib/state/app.svelte.ts";
  import { noPicks } from "./lib/state/picks.ts";
  import { clientMissing } from "./lib/ui/labels.ts";

  let { app, onstep }: { app: App; onstep?: () => void } = $props();
  const state = $derived(app.state);
  const imported = $derived(
    state.imported && state.imported.key === state.plan?.key ? state.imported.value : null,
  );
  const picks = $derived(state.picks && state.picks.key === state.plan?.key ? state.picks.value : noPicks());
  const picked = $derived(picks.runes !== undefined || picks.spells !== undefined || Object.keys(picks.items).length > 0);
  const changed = $derived(!!imported && JSON.stringify(state.imported?.picks) !== JSON.stringify(picks));
  /** The client isn't open: not an error, the app waits for it. */
  const waiting = $derived(clientMissing(state.error));
  const showPlan = $derived(!!state.plan && !!state.champSelect?.champion);
</script>

<main>
  <header>
    <h1>Stronk</h1>
    {#if onstep}<button type="button" class="dev" onclick={onstep}>Next step</button>{/if}
  </header>

  {#if state.error && !waiting}
    <p class="error" role="alert">{state.error.message}</p>
  {/if}

  <ChampSelect
    select={state.champSelect}
    names={state.names}
    icons={state.icons}
    patch={state.data?.patch ?? null}
    noClient={waiting ? (state.error?.message ?? null) : null}
    actions={showPlan ? actions : undefined}
  />
  {#snippet actions()}
    {#if picked}<button type="button" class="quiet" onclick={() => app.resetPicks()}>Use Stronk's picks</button>{/if}
    <button type="button" class="primary" onclick={() => void app.importBuild()}>Import</button>
  {/snippet}

  {#if state.plan && showPlan}
    <PlanView
      plan={state.plan.value}
      names={state.names}
      icons={state.icons}
      {picks}
      {imported}
      {changed}
      onpick={(p) => app.pick(p)}
    />
  {/if}

  <Settings
    settings={state.settings}
    restore={state.restore}
    onautoimport={(on) => app.setAutoImport(on)}
    onopen={() => void app.loadBackups()}
    onrestore={(location) => void app.restoreItemSets(location)}
  />

  <footer>
    Stronk isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone
    officially involved in producing or managing Riot Games properties. Riot Games, and all associated
    properties are trademarks or registered trademarks of Riot Games, Inc.
  </footer>
</main>

<style>
  main {
    display: grid;
    gap: var(--space-3);
    max-width: 1180px;
    margin: 0 auto;
    padding: var(--space-4);
  }
  header {
    display: flex;
    gap: var(--space-3);
    align-items: center;
  }
  h1 {
    margin: 0;
    font-size: var(--text-md);
    letter-spacing: 0.02em;
  }
  .dev {
    margin-left: auto;
    padding: var(--space-1) var(--space-3);
    border: 1px dashed var(--color-border);
    border-radius: var(--radius);
    background: none;
    color: var(--color-muted);
    font: inherit;
    font-size: var(--text-sm);
  }
  .quiet,
  .primary {
    padding: var(--space-2) var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    cursor: pointer;
  }
  .primary {
    padding: var(--space-2) var(--space-6);
    border-color: var(--color-accent);
    background: var(--color-accent);
    color: var(--color-surface);
    font-weight: 600;
  }
  .quiet:hover {
    background: var(--color-bg);
  }
  .primary:hover {
    filter: brightness(1.08);
  }
  .quiet:focus-visible,
  .primary:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
  }
  footer {
    padding-top: var(--space-3);
    border-top: 1px solid var(--color-border);
    color: var(--color-muted);
    font-size: var(--text-xs);
  }
  .error {
    margin: 0;
    padding: var(--space-3);
    border-radius: var(--radius);
    background: var(--color-negative-bg);
    color: var(--color-negative);
  }
</style>
