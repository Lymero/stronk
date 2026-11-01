<script lang="ts">
  import type { AppState, Settings } from "../../state/app.svelte.ts";

  let {
    settings,
    restore,
    onautoimport,
    onopen,
    onrestore,
  }: {
    settings: Settings;
    restore: AppState["restore"];
    onautoimport: (on: boolean) => void;
    /** Settings were opened: list the backups. */
    onopen: () => void;
    onrestore: (location: string) => void;
  } = $props();

  let chosen = $state<string | null>(null);
  let confirming = $state(false);
  const selected = $derived(chosen ?? restore.backups?.[0]?.location ?? null);

  const when = (ms: number | null) =>
    ms === null ? "Unknown time" : new Date(ms).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  const savedAt = (location: string) => when(restore.backups?.find((b) => b.location === location)?.saved_at_ms ?? null);

  function confirm(): void {
    if (selected) onrestore(selected);
    confirming = false;
    chosen = null;
  }
</script>

<details class="settings" ontoggle={(e) => e.currentTarget.open && onopen()}>
  <summary>Settings</summary>

  <label class="toggle">
    <input type="checkbox" checked={settings.autoImport} onchange={(e) => onautoimport(e.currentTarget.checked)} />
    Auto-import on lock-in
  </label>

  <section aria-label="Item set backups">
    <h3>Item set backups</h3>
    <p class="meta">
      Stronk saves your item sets before every import. Restoring one puts those sets back in the client, and saves the
      current ones first.
    </p>
    {#if restore.backups === null}
      <p class="meta">{restore.error ? "" : "Loading backups…"}</p>
    {:else if restore.backups.length === 0}
      <p class="meta">No backups yet: Stronk hasn't changed your item sets.</p>
    {:else}
      <fieldset>
        <legend class="meta">Newest first</legend>
        {#each restore.backups as backup (backup.location)}
          <label class="backup" title={backup.location}>
            <input
              type="radio"
              name="backup"
              value={backup.location}
              checked={backup.location === selected}
              onchange={() => {
                chosen = backup.location;
                confirming = false;
              }}
            />
            {when(backup.saved_at_ms)}
          </label>
        {/each}
      </fieldset>
      {#if confirming && selected}
        <div class="confirm" role="group" aria-label="Confirm restore">
          <p>Replace your item sets in the client with the backup from {savedAt(selected)}?</p>
          <button type="button" class="primary" onclick={confirm}>Restore</button>
          <button type="button" onclick={() => (confirming = false)}>Cancel</button>
        </div>
      {:else}
        <button type="button" disabled={!selected} onclick={() => (confirming = true)}>Restore this backup</button>
      {/if}
    {/if}
    {#if restore.done}
      <p class="meta" role="status">
        Restored {restore.done.sets} item {restore.done.sets === 1 ? "set" : "sets"}. The sets they replaced were backed up
        first.
      </p>
    {/if}
    {#if restore.error}
      <p class="error" role="alert">{restore.error.message}</p>
    {/if}
  </section>
</details>

<style>
  .settings {
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-surface);
  }
  summary {
    cursor: pointer;
    font-weight: 600;
  }
  .toggle {
    display: block;
    margin-top: var(--space-3);
  }
  h3 {
    margin: var(--space-4) 0 var(--space-1);
    font-size: var(--text-md);
  }
  .meta {
    margin: 0 0 var(--space-2);
    color: var(--color-muted);
    font-size: var(--text-sm);
  }
  fieldset {
    margin: 0 0 var(--space-3);
    padding: 0;
    border: 0;
  }
  legend {
    padding: 0;
  }
  .backup {
    display: block;
    padding: var(--space-1) 0;
  }
  .confirm p {
    margin: 0 0 var(--space-2);
  }
  button {
    padding: var(--space-1) var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
  }
  button.primary {
    border-color: var(--color-accent);
    background: var(--color-accent);
    color: var(--color-surface);
  }
  .error {
    margin: var(--space-2) 0 0;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius);
    background: var(--color-warning-bg);
    color: var(--color-negative);
  }
</style>
