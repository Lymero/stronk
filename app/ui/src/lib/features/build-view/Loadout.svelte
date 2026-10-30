<script lang="ts" module>
  export interface LoadoutSlot {
    key: string;
    /** Above the pick: "Runes", "Spells", "Item 1"… */
    name: string;
    /** The pick, in words: "Conqueror", "Smite + Flash"… */
    value: string;
    /** Under it, when there's more to say: the page's trees. */
    detail?: string;
    icons: { src: string | null; name: string }[];
    /** Stronk takes another option than the most played one: its gain ("+2.1"), and whether it's
     * its best bet rather than a proven gain (ADR-065). */
    changed: { text: string; bet: boolean } | null;
    yours: boolean;
  }
</script>

<script lang="ts">
  // The build the import writes as a sheet (ADR-062): runes, spells and items, each with its pick
  // by name, a tab that opens the slot beside it. A green ▲ with its gain marks a slot where
  // Stronk takes a clearly better option than the most played one, an amber "Best bet" one where
  // it takes its best bet, not yet proven (ADR-065); "Your pick", one the player
  // changed.
  import Icon from "../../ui/Icon.svelte";

  let {
    slots,
    focus,
    onfocus,
  }: {
    slots: LoadoutSlot[];
    focus: string;
    onfocus: (key: string) => void;
  } = $props();

  /** Arrow keys move between the tabs, as a tab list does. */
  function onkeydown(e: KeyboardEvent): void {
    const step = e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const at = slots.findIndex((s) => s.key === focus);
    const next = slots[(at + step + slots.length) % slots.length];
    if (next) {
      onfocus(next.key);
      document.getElementById(`slot-tab-${next.key}`)?.focus();
    }
  }
</script>

<div class="sheet" role="tablist" aria-label="Build to import" aria-orientation="vertical" tabindex="-1" {onkeydown}>
  {#each slots as slot (slot.key)}
    <button
      type="button"
      role="tab"
      id={`slot-tab-${slot.key}`}
      class="slot"
      class:active={focus === slot.key}
      aria-selected={focus === slot.key}
      aria-controls="slot-panel"
      aria-label={`${slot.name}: ${slot.value}${slot.changed ? `, Stronk's ${slot.changed.bet ? "best bet" : "change"} ${slot.changed.text}` : ""}${slot.yours ? ", your pick" : ""}`}
      tabindex={focus === slot.key ? 0 : -1}
      onclick={() => onfocus(slot.key)}
    >
      <span class="icons">{#each slot.icons as i, n (n)}<Icon src={i.src} name={i.name} size="md" round />{/each}</span>
      <span class="text">
        <span class="name">{slot.name}</span>
        <span class="value">{slot.value}</span>
        {#if slot.detail}<span class="detail">{slot.detail}</span>{/if}
      </span>
      {#if slot.changed?.bet}<span class="badge bet">Best bet {slot.changed.text}</span>
      {:else if slot.changed}<span class="badge changed">▲ {slot.changed.text}</span>{/if}
      {#if slot.yours}<span class="badge yours">Your pick</span>{/if}
    </button>
  {/each}
</div>

<style>
  .sheet {
    display: grid;
    gap: 2px;
    outline: none;
  }
  .slot {
    position: relative;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: var(--space-3);
    align-items: center;
    padding: var(--space-2) var(--space-3);
    border: 1px solid transparent;
    border-radius: var(--radius);
    background: none;
    color: var(--color-text);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .slot:hover {
    background: var(--color-raised);
  }
  .slot.active {
    border-color: var(--color-accent);
    background: var(--color-accent-bg);
  }
  .slot.active::before {
    position: absolute;
    top: 8px;
    bottom: 8px;
    left: -1px;
    width: 3px;
    border-radius: 0 3px 3px 0;
    background: var(--color-accent);
    content: "";
  }
  .slot:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
  }
  .icons {
    display: flex;
    gap: 3px;
  }
  .icons :global(.icon) {
    box-shadow: 0 0 0 2px var(--color-border);
  }
  .text {
    display: grid;
    min-width: 0;
  }
  .name {
    color: var(--color-muted);
    font-size: var(--text-xs);
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }
  .value,
  .detail {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .value {
    font-weight: 600;
  }
  .detail {
    color: var(--color-muted);
    font-size: var(--text-sm);
  }
  .badge {
    padding: 2px 8px;
    border-radius: 999px;
    font-size: var(--text-xs);
    font-weight: 700;
    white-space: nowrap;
  }
  .badge.bet {
    background: var(--color-accent-bg);
    color: var(--color-accent);
  }
  .badge.changed {
    background: var(--color-positive-bg);
    color: var(--color-positive);
  }
  .badge.yours {
    border: 1px solid var(--color-accent);
    color: var(--color-accent);
  }
</style>
