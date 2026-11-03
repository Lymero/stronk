<script lang="ts">
  import BracketSwitch from "./lib/features/build-view/BracketSwitch.svelte";
  import PlanView from "./lib/features/build-view/PlanView.svelte";
  import ChampSelect from "./lib/features/champ-select/ChampSelect.svelte";
  import Settings from "./lib/features/settings/Settings.svelte";
  import Picker from "./lib/features/viewer/Picker.svelte";
  import type { App } from "./lib/state/app.svelte.ts";
  import { noPicks } from "./lib/state/picks.ts";
  import { clientMissing } from "./lib/ui/labels.ts";

  /** `viewer`: the web build viewer (ADR-086), read-only: the player picks a champion and role
   * instead of champion select, and nothing is imported. */
  let { app, onstep, viewer = false }: { app: App; onstep?: () => void; viewer?: boolean } = $props();
  const state = $derived(app.state);
  const imported = $derived(
    state.imported && state.imported.key === state.plan?.key ? state.imported.value : null,
  );
  const picks = $derived(state.picks && state.picks.key === state.plan?.key ? state.picks.value : noPicks());
  const picked = $derived(picks.runes !== undefined || picks.spells !== undefined || Object.keys(picks.items).length > 0);
  /** The picks, or the bracket the build comes from (ADR-078), changed since that import. */
  const changed = $derived(
    !!imported &&
      (JSON.stringify(state.imported?.picks) !== JSON.stringify(picks) || state.imported?.elo !== state.plan?.value.elo),
  );
  /** The client isn't open: not an error, the app waits for it. */
  const waiting = $derived(clientMissing(state.error));
  const showPlan = $derived(!!state.plan && !!state.champSelect?.champion);
  /** The brackets the data has builds for, highest first (ADR-078). */
  const elos = $derived(state.data?.elos ?? []);
</script>

<main>
  <header>
    <h1><span class="mark" aria-hidden="true"></span>STRONK</h1>
    {#if onstep}<button type="button" class="dev" onclick={onstep}>Next step</button>{/if}
  </header>

  {#if state.error && !waiting}
    <p class="error" role="alert">{state.error.message}</p>
  {/if}

  {#if viewer && state.builds}
    <Picker
      builds={state.builds}
      names={state.names}
      icons={state.icons}
      selected={state.champSelect?.champion && state.champSelect.role ? { champion: state.champSelect.champion, role: state.champSelect.role } : null}
      onchoose={(champion, role) => void app.choose(champion, role)}
    />
  {/if}
  <ChampSelect
    {viewer}
    select={state.champSelect}
    names={state.names}
    icons={state.icons}
    patch={state.data?.patch ?? null}
    noClient={waiting ? (state.error?.message ?? null) : null}
    actions={showPlan ? actions : undefined}
  />
  {#snippet actions()}
    {#if elos.length > 1}<BracketSwitch {elos} value={state.settings.elo} onelo={(elo) => void app.setElo(elo)} />{/if}
    {#if picked}<button type="button" class="quiet" onclick={() => app.resetPicks()}>Use Stronk's picks</button>{/if}
    {#if !viewer}<button type="button" class="primary" onclick={() => void app.importBuild()}>Import</button>{/if}
  {/snippet}

  {#if state.plan && showPlan}
    <PlanView
      plan={state.plan.value}
      wanted={state.plan.elo}
      names={state.names}
      icons={state.icons}
      {picks}
      {imported}
      {changed}
      onpick={(p) => app.pick(p)}
    />
  {/if}

  {#if !viewer}<Settings
    settings={state.settings}
    restore={state.restore}
    onautoimport={(on) => app.setAutoImport(on)}
    onautoitemset={(on) => app.setAutoItemSet(on)}
    onopen={() => void app.loadBackups()}
    onrestore={(location) => void app.restoreItemSets(location)}
  />{/if}

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
    display: flex;
    gap: var(--space-2);
    align-items: center;
    margin: 0;
    font-size: var(--text-md);
    font-weight: 800;
    letter-spacing: 0.22em;
  }
  /* The wordmark's glyph: a forge-amber bar. */
  .mark {
    width: 6px;
    height: 18px;
    border-radius: 2px;
    background: var(--color-accent);
    box-shadow: 0 0 12px var(--color-accent);
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
    color: var(--color-on-accent);
    font-weight: 700;
    letter-spacing: 0.02em;
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
