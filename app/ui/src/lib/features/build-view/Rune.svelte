<script lang="ts">
  // One rune or shard as the client draws it (ADR-063): a round icon, in colour with an amber ring
  // when the import writes it, greyed otherwise, its name on hover as in the client. Under it, its
  // number against the most played option of its row when it has one (a picked rune's is on the
  // line under its row, with its name). The accessible name says
  // everything, games and range included, for screen readers.
  import type { Row } from "../../backend/backend.ts";
  import Icon from "../../ui/Icon.svelte";
  import { games } from "../../ui/labels.ts";
  import { reading, spread, wins } from "./options.ts";

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
    /** Keystones are the largest, shards the smallest, as in the client. */
    size?: "lg" | "md" | "sm";
    onpick: () => void;
  } = $props();

  const read = $derived(reading(row));
  const half = $derived(row?.ci ? spread(row.ci) : null);
  const label = $derived(
    `${name}${
      !row
        ? ""
        : row.confidence === "almost_always"
          ? ", almost always taken"
          : row.confidence === "most_played"
            ? `, most played${read.number === null ? "" : ", 0"}`
            : row.confidence === "too_few_games"
              ? ", too few games"
              : row.confidence === "too_few_to_compare"
                ? ", too few to compare"
                : read.number === null || row.wpa === null
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
  title={name}
  onclick={onpick}
>
  <span class="disc"><Icon src={icon} {name} size="md" round /></span>
  <span class="num {read.tone}">{read.number ?? ""}</span>
</button>

<style>
  .cell {
    position: relative;
    display: grid;
    width: max(var(--size), 40px);
    gap: 2px;
    justify-items: center;
    padding: 0;
    border: none;
    background: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  .cell:focus-visible {
    outline: none;
  }
  .cell:focus-visible .disc {
    outline: 2px solid var(--color-accent);
    outline-offset: 3px;
  }
  .disc {
    display: grid;
    border-radius: 50%;
    box-shadow: 0 0 0 1px var(--color-border);
  }
  .disc :global(.icon) {
    width: var(--size);
    height: var(--size);
    border-radius: 50%;
    filter: grayscale(1);
    opacity: 0.45;
    transition:
      opacity 0.1s,
      filter 0.1s;
  }
  .lg {
    --size: 48px;
  }
  .md {
    --size: 36px;
  }
  .sm {
    --size: 26px;
  }
  .cell:hover .disc :global(.icon) {
    filter: none;
    opacity: 0.85;
  }
  /* What the import writes: in colour, ringed in amber, as the client lights a picked rune. */
  .on .disc {
    box-shadow:
      0 0 0 2px var(--color-accent),
      0 0 10px var(--color-accent);
  }
  .on .disc :global(.icon) {
    filter: none;
    opacity: 1;
  }
  /* Stronk's choice when the player picked another: a small amber dot. */
  .stronk::after {
    position: absolute;
    top: -2px;
    right: -2px;
    width: 8px;
    height: 8px;
    border: 2px solid var(--color-surface);
    border-radius: 50%;
    background: var(--color-accent);
    content: "";
  }
  .num {
    height: 14px;
    color: var(--color-muted);
    font-size: var(--text-xs);
    font-variant-numeric: tabular-nums;
    line-height: 14px;
  }
  /* The picked rune's number is on the line under its row, with its name. */
  .on .num {
    visibility: hidden;
  }
  .num.positive {
    color: var(--color-positive);
    font-weight: 700;
  }
  .num.negative {
    color: var(--color-negative);
    font-weight: 700;
  }
  @media (prefers-reduced-motion: reduce) {
    .disc :global(.icon) {
      transition: none;
    }
  }
</style>
