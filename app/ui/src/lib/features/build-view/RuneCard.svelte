<script lang="ts">
  // One rune or shard as a card (ADR-063), read like a row of the item lists: its icon and name,
  // its wins per 100 games against the most played option of its row (0 for that one, coloured
  // only when clearly better or worse, nothing when short of games, or why an option with plenty
  // of games has none) and its games, its share of games as a bar along the bottom as in the item
  // lists. What the import writes is outlined in
  // amber; clicking a card picks it. The accessible name carries the range for screen readers.
  import type { Row } from "../../backend/backend.ts";
  import Icon from "../../ui/Icon.svelte";
  import { games } from "../../ui/labels.ts";
  import { figure, spread, verdict, wins } from "./options.ts";

  let {
    icon,
    name,
    row,
    on,
    stronk = false,
    size = "md",
    onpick,
  }: {
    icon: string | null;
    name: string;
    /** Its numbers; none when nobody took it in these games. */
    row: Row<unknown> | undefined;
    /** What the import writes. */
    on: boolean;
    /** Stronk's choice, marked when the player picked another. */
    stronk?: boolean;
    size?: "sm" | "md";
    onpick: () => void;
  } = $props();

  /** Games, short enough for a card: "4.1K games" from a thousand on; the exact count is in its name. */
  const count = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}K games` : games(n));
  const clear = $derived(row ? verdict(row) : null);
  const half = $derived(row?.ci ? spread(row.ci) : null);
  /** Its number: against the most played option, or 0 for that option when it has an estimate. */
  const number = $derived(
    !row
      ? null
      : row.confidence === "most_played"
        ? row.wpa === null
          ? null
          : "0"
        : figure(row) === null || row.wpa === null
          ? null
          : `${clear ? (clear.tone === "positive" ? "▲ " : "▼ ") : ""}${wins(row.wpa)}`,
  );
  const why = $derived(
    row?.confidence === "almost_always" ? "almost always" : row?.confidence === "too_few_to_compare" ? "too few to compare" : null,
  );
  const label = $derived(
    `${name}${
      !row
        ? ""
        : row.confidence === "almost_always"
          ? ", almost always taken"
          : row.confidence === "most_played"
            ? `, most played${number === null ? "" : ", 0"}`
            : row.confidence === "too_few_games"
              ? ", too few games"
              : row.confidence === "too_few_to_compare"
                ? ", too few to compare"
                : number === null || row.wpa === null
                  ? ""
                  : ` ${wins(row.wpa)}${half === null ? "" : ` ± ${half.toFixed(1)}`} wins per 100 against the most played`
    }${row ? `, ${games(row.played)}` : ", not played"}`,
  );
</script>

<button
  type="button"
  class="cell {size}"
  class:on
  class:stronk={stronk && !on}
  aria-pressed={on}
  aria-label={label}
  onclick={onpick}
>
  <Icon src={icon} {name} size="sm" round />
  <span class="text">
    <span class="title">{name}</span>
    <span class="stats">
      <span class="num {clear?.tone ?? ''}" class:why={number === null && why !== null}>{number ?? why ?? ""}</span>
      <!-- "almost always" and "too few to compare" already say the games are plenty: the bar shows how many. -->
      {#if row && !why}<span class="games">{count(row.played)}</span>{/if}
    </span>
  </span>
  <span class="share" aria-hidden="true"><span style:width={`${(row?.share ?? 0) * 100}%`}></span></span>
</button>

<style>
  .cell {
    position: relative;
    display: grid;
    overflow: hidden;
    height: 48px;
    grid-template-columns: auto minmax(0, 1fr);
    gap: var(--space-2);
    align-items: center;
    min-width: 0;
    padding: var(--space-2);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .cell:hover {
    background: var(--color-raised);
  }
  .cell:focus-visible {
    outline: 2px solid var(--color-accent);
  }
  /* What the import writes. */
  .cell.on {
    border-color: var(--color-accent);
    background: var(--color-accent-bg);
  }
  .cell :global(.icon) {
    filter: grayscale(0.7);
    opacity: 0.6;
  }
  .cell.on :global(.icon),
  .cell:hover :global(.icon) {
    filter: none;
    opacity: 1;
  }
  .cell :global(.icon) {
    width: 26px;
    height: 26px;
  }
  .cell.on :global(.icon) {
    box-shadow: 0 0 0 2px var(--color-accent);
  }
  .sm :global(.icon) {
    width: 20px;
    height: 20px;
  }
  /* Stronk's choice when the player picked another: a small amber dot. */
  .stronk::after {
    position: absolute;
    top: 6px;
    right: 6px;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--color-accent);
    content: "";
  }
  .text {
    display: grid;
    min-width: 0;
  }
  .title {
    overflow: hidden;
    color: var(--color-muted);
    font-size: var(--text-sm);
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .on .title {
    color: var(--color-text);
  }
  .stats {
    display: flex;
    gap: var(--space-2);
    align-items: baseline;
    height: 17px;
    overflow: hidden;
    color: var(--color-muted);
    font-size: var(--text-xs);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .num {
    color: var(--color-text);
    font-size: var(--text-sm);
    font-weight: 700;
  }
  .num:empty {
    display: none;
  }
  .num.why {
    font-size: var(--text-xs);
    font-weight: 600;
  }
  /* The share of games, along the bottom. */
  .share {
    position: absolute;
    right: 0;
    bottom: 0;
    left: 0;
    height: 3px;
    background: var(--color-track);
  }
  .share span {
    display: block;
    height: 100%;
    background: var(--color-muted);
  }
  .on .share span {
    background: var(--color-accent);
  }
  .num.positive {
    color: var(--color-positive);
  }
  .num.negative {
    color: var(--color-negative);
  }
  .games {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .sm {
    height: 40px;
    padding: var(--space-1) var(--space-2);
  }
  .sm .title {
    font-size: var(--text-xs);
  }
</style>
