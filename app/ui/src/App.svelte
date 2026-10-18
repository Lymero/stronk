<script lang="ts">
  import PlanView from "./lib/features/build-view/PlanView.svelte";
  import ChampSelect from "./lib/features/champ-select/ChampSelect.svelte";
  import type { App } from "./lib/state/app.svelte.ts";

  let { app, onstep }: { app: App; onstep?: () => void } = $props();
  const state = $derived(app.state);
  const imported = $derived(
    state.imported && state.imported.key === state.plan?.key ? state.imported.value : null,
  );
</script>

<main>
  <header>
    <h1>Stronk</h1>
    {#if state.data}<span class="meta">Data {state.data.patch}</span>{/if}
    <label class="toggle">
      <input
        type="checkbox"
        checked={state.settings.autoImport}
        onchange={(e) => app.setAutoImport(e.currentTarget.checked)}
      />
      Auto-import on lock-in
    </label>
    {#if onstep}<button type="button" onclick={onstep}>Next step</button>{/if}
  </header>

  {#if state.error}
    <p class="error" role="alert">{state.error.message}</p>
  {/if}

  <ChampSelect select={state.champSelect} />
  {#if state.plan && state.champSelect?.champion}
    <PlanView plan={state.plan.value} {imported} onimport={() => void app.importBuild()} />
  {/if}
</main>

<style>
  main {
    display: grid;
    gap: var(--space-4);
    max-width: 720px;
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
  .toggle {
    margin-left: auto;
    color: var(--color-muted);
    font-size: var(--text-sm);
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
