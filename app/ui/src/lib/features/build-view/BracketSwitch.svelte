<script lang="ts">
  // The elo bracket builds come from, switched beside the import (ADR-078): one click asks the
  // plan again from the bracket chosen, which the app remembers.
  import { elo } from "../../ui/labels.ts";

  let {
    elos,
    value,
    onelo,
  }: {
    /** The brackets the data has builds for, highest first. */
    elos: string[];
    value: string;
    onelo: (elo: string) => void;
  } = $props();

  const about =
    "Each bracket includes the games of those above it. A champion with no build in yours shows the closest bracket's, and says so.";
</script>

<div class="switch" role="radiogroup" aria-label="Builds from" title={about}>
  {#each elos as id (id)}
    <label class:on={id === value}>
      <input type="radio" name="elo" value={id} checked={id === value} onchange={() => onelo(id)} />
      {elo(id)}
    </label>
  {/each}
</div>

<style>
  .switch {
    display: inline-flex;
    padding: 2px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-bg);
  }
  label {
    padding: var(--space-1) var(--space-3);
    border-radius: var(--radius-sm);
    color: var(--color-muted);
    font-size: var(--text-sm);
    font-weight: 600;
    cursor: pointer;
  }
  label:hover {
    color: var(--color-text);
  }
  label.on {
    background: var(--color-surface);
    box-shadow: var(--shadow);
    color: var(--color-text);
  }
  label:has(input:focus-visible) {
    outline: 2px solid var(--color-accent);
    outline-offset: 1px;
  }
  /* The radio is the label: the dot would only take room. */
  input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }
</style>
