<script lang="ts">
  import PlanView from "./lib/features/build-view/PlanView.svelte";
  import ChampSelect from "./lib/features/champ-select/ChampSelect.svelte";
  import Settings from "./lib/features/settings/Settings.svelte";
  import type { App } from "./lib/state/app.svelte.ts";
  import { noPicks } from "./lib/state/picks.ts";

  let { app, onstep }: { app: App; onstep?: () => void } = $props();
  const state = $derived(app.state);
  const imported = $derived(
    state.imported && state.imported.key === state.plan?.key ? state.imported.value : null,
  );
  const picks = $derived(state.picks && state.picks.key === state.plan?.key ? state.picks.value : noPicks());
  const changed = $derived(!!imported && JSON.stringify(state.imported?.picks) !== JSON.stringify(picks));
</script>

<main>
  <header>
    <h1>Stronk</h1>
    {#if state.data}<span class="meta">Data {state.data.patch}</span>{/if}
    {#if onstep}<button type="button" onclick={onstep}>Next step</button>{/if}
  </header>

  {#if state.error}
    <p class="error" role="alert">{state.error.message}</p>
  {/if}

  <ChampSelect select={state.champSelect} names={state.names} />
  {#if state.plan && state.champSelect?.champion}
    <PlanView
      plan={state.plan.value}
      names={state.names}
      {picks}
      {imported}
      {changed}
      onimport={() => void app.importBuild()}
      onpick={(p) => app.pick(p)}
      onreset={() => app.resetPicks()}
    />
  {/if}

  <Settings
    settings={state.settings}
    restore={state.restore}
    onautoimport={(on) => app.setAutoImport(on)}
    onopen={() => void app.loadBackups()}
    onrestore={(location) => void app.restoreItemSets(location)}
  />
</main>

<style>
  main {
    display: grid;
    gap: var(--space-4);
    max-width: 960px;
    margin: 0 auto;
    padding: var(--space-6) var(--space-4);
  }
  header {
    display: flex;
    gap: var(--space-3);
    align-items: baseline;
  }
  h1 {
    margin: 0;
    font-size: var(--text-lg);
  }
  .meta {
    color: var(--color-muted);
  }
  header button {
    margin-left: auto;
  }
  button {
    padding: var(--space-1) var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
  }
  .error {
    margin: 0;
    padding: var(--space-3);
    border-radius: var(--radius);
    background: var(--color-warning-bg);
    color: var(--color-negative);
  }
</style>
