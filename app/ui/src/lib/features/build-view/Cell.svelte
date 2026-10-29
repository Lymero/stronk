<script lang="ts">
  // One option as its icon and its estimate (ADR-060): a ring around the icon filled by its share
  // of games and its wins per 100 games against the most played option of its row, which reads 0;
  // coloured only when clearly better or worse. Options not compared with it head to head have no
  // number ("few games" when that's why). The accessible name carries the range for screen
  // readers. Lit when the import writes it; clicking it picks it.
  import type { Row } from "../../backend/backend.ts";
  import Icon from "../../ui/Icon.svelte";
  import { figure, spread, verdict, wins } from "./options.ts";

  let {
    icons,
    name,
    row,
    on,
    stronk = false,
    size = "md",
    bare = false,
    onpick,
  }: {
    icons: { src: string | null; name: string }[];
    name: string;
    /** Its numbers; none when nobody took it in these games. */
    row: Row<unknown> | undefined;
    /** What the import writes. */
    on: boolean;
    /** Stronk's choice, marked when the player picked another. */
    stronk?: boolean;
    size?: "sm" | "md";
    /** No numbers of its own (a secondary rune: measured as a pair). */
    bare?: boolean;
    onpick?: () => void;
  } = $props();

  const clear = $derived(row ? verdict(row) : null);
  const tone = $derived(clear?.tone ?? "");
  const half = $derived(row?.ci ? spread(row.ci) : null);
  /** Its number: against the most played option, or 0 for that option when it has an estimate. */
  const number = $derived(
    !row || bare
      ? null
      : row.confidence === "most_played"
        ? row.wpa === null
          ? null
          : "0"
        : figure(row) === null || row.wpa === null
          ? null
          : `${clear ? (clear.tone === "positive" ? "▲" : "▼") : ""}${wins(row.wpa)}`,
  );
  const label = $derived(
    `${name}${
      bare || !row
        ? ""
        : row.confidence === "most_played"
          ? `, most played${number === null ? "" : ", 0"}`
          : row.confidence === "too_few_games"
            ? ", too few games"
            : number === null || row.wpa === null
              ? ""
              : ` ${wins(row.wpa)}${half === null ? "" : ` ± ${half.toFixed(1)}`} wins per 100 against the most played`
    }`,
  );
</script>

<button
  type="button"
  class="cell {size}"
  class:on
  class:stronk={stronk && !on}
  class:bare
  aria-pressed={on}
  aria-label={label}
  disabled={!onpick}
  onclick={() => onpick?.()}
>
  <span class="icons">
    {#each icons as i, n (n)}
      <span class="ring">
        {#if !bare}
          <svg viewBox="0 0 36 36" aria-hidden="true">
            <circle class="track" cx="18" cy="18" r="16.5" />
            {#if row && row.share > 0}
              <circle class="arc" cx="18" cy="18" r="16.5" pathLength="100" stroke-dasharray={`${row.share * 100} 100`} />
            {/if}
          </svg>
        {/if}
        <Icon src={i.src} name={i.name} size={size === "sm" ? "sm" : "md"} />
      </span>
    {/each}
  </span>
  {#if !bare}
    <span class="num {tone}" class:few={number === null}>
      {#if number !== null}{number}{:else if row?.confidence === "too_few_games"}few games{/if}
    </span>
  {/if}
</button>

<style>
  .cell {
    position: relative;
    display: grid;
    grid-template-rows: auto 14px;
    align-content: start;
    justify-items: center;
    gap: 2px;
    min-width: 58px;
    padding: var(--space-1) 2px;
    border: 1px solid transparent;
    border-radius: var(--radius);
    background: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  .cell.bare {
    grid-template-rows: auto;
    min-width: 44px;
  }
  .cell.sm {
    min-width: 50px;
  }
  .cell:disabled {
    cursor: default;
  }
  .cell:not(:disabled):hover {
    border-color: var(--color-border);
  }
  .cell:focus-visible {
    outline: 2px solid var(--color-accent);
  }
  .icons {
    display: flex;
    gap: 2px;
  }
  /* The share of games as an arc around the icon, from the top, clockwise. */
  .ring {
    position: relative;
    display: grid;
    padding: 4px;
  }
  .ring svg {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    transform: rotate(-90deg);
  }
  .ring circle {
    fill: none;
    stroke-width: 2.5;
  }
  .ring .track {
    stroke: var(--color-track);
  }
  .ring .arc {
    stroke: var(--color-muted);
    stroke-linecap: round;
  }
  .on .ring .arc {
    stroke: var(--color-accent);
  }
  .ring :global(.icon) {
    border-radius: 50%;
    filter: grayscale(1);
    opacity: 0.5;
    transition: opacity 0.1s;
  }
  .cell:not(:disabled):hover .ring :global(.icon) {
    opacity: 0.85;
  }
  .on .ring :global(.icon) {
    filter: none;
    opacity: 1;
  }
  /* Stronk's choice when the player picked another: a small dot. */
  .stronk::after {
    position: absolute;
    top: 2px;
    right: 6px;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--color-accent);
    content: "";
  }
  .num {
    color: var(--color-muted);
    font-size: var(--text-xs);
    font-variant-numeric: tabular-nums;
    line-height: 14px;
    white-space: nowrap;
  }
  .on .num {
    color: var(--color-text);
    font-weight: 600;
  }
  .num.positive {
    color: var(--color-positive);
    font-weight: 600;
  }
  .num.negative {
    color: var(--color-negative);
    font-weight: 600;
  }
  .num.few {
    font-size: 10px;
    font-weight: 400;
  }
  @media (prefers-reduced-motion: reduce) {
    .ring :global(.icon) {
      transition: none;
    }
  }
</style>
