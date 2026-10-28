<script lang="ts" generics="T">
  // One slot (spells, an item slot, rune pages without a layout) as a row of options to click
  // (ADR-059): the options played in at least 2% of games, the short list and the pick, the rest
  // behind "+N" in the same row. No list to scroll.
  import Cell from "./Cell.svelte";
  import type { Slot } from "./options.ts";

  let {
    title,
    note = null,
    slot,
    label,
    icons,
    onpick,
  }: {
    title: string;
    /** What the slot's header says after its title: a clear result, or "Your pick". */
    note?: { text: string; tone: string; title: string } | null;
    slot: Slot<T>;
    label: (value: T) => string;
    icons: (value: T) => { src: string | null; name: string }[];
    onpick: (value: T) => void;
  } = $props();

  const MIN_SHARE = 0.02;
  let all = $state(false);
  const main = $derived(slot.rows.filter((r) => r.shown || r.share >= MIN_SHARE));
  const rows = $derived(all ? slot.rows : main);
  const hidden = $derived(slot.rows.length - main.length);
</script>

<section class="panel" aria-label={title}>
  <header>
    <h4>{title}</h4>
    {#if note}<span class="note {note.tone}" title={note.title}>{note.text}</span>{/if}
  </header>
  <div class="cells">
    {#each rows as row (row.key)}
      <Cell
        icons={icons(row.value)}
        name={label(row.value)}
        {row}
        on={row.selected}
        stronk={row.chosen}
        onpick={() => onpick(row.value)}
      />
    {/each}
    {#if hidden > 0}
      <button type="button" class="more" aria-expanded={all} onclick={() => (all = !all)}>
        {all ? "Fewer" : `+${hidden}`}
      </button>
    {/if}
  </div>
</section>

<style>
  .panel {
    display: grid;
    gap: var(--space-1);
    overflow: hidden;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
  }
  header {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-3);
    align-items: baseline;
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--color-border);
    background: var(--color-bg);
  }
  h4 {
    margin: 0;
    font-size: var(--text-md);
  }
  .note {
    margin-left: auto;
    font-size: var(--text-sm);
    font-variant-numeric: tabular-nums;
  }
  .note.muted {
    color: var(--color-muted);
  }
  .note.positive {
    color: var(--color-positive);
    font-weight: 600;
  }
  .note.negative {
    color: var(--color-negative);
    font-weight: 600;
  }
  .note.picked {
    color: var(--color-accent);
    font-weight: 600;
  }
  .cells {
    display: flex;
    flex-wrap: wrap;
    gap: 2px;
    padding: var(--space-1) var(--space-2) var(--space-2);
  }
  .more {
    align-self: start;
    min-width: 44px;
    margin-top: var(--space-1);
    padding: var(--space-2) var(--space-1);
    border: 1px dashed var(--color-border);
    border-radius: var(--radius);
    background: none;
    color: var(--color-accent);
    font: inherit;
    font-size: var(--text-sm);
    cursor: pointer;
  }
  .more:hover {
    border-color: var(--color-accent);
  }
  .more:focus-visible {
    outline: 2px solid var(--color-accent);
  }
</style>
