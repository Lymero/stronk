<script lang="ts">
  // One option as an icon with its numbers under it (ADR-059): win impact (coloured only when
  // clearly better or worse), how precise it is as a bar, and how many games it rests on. Lit
  // when the import writes it; clicking it picks it.
  import type { Row } from "../../backend/backend.ts";
  import Icon from "../../ui/Icon.svelte";
  import { explain, percent, verdict } from "./options.ts";

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
  /** Half the 95% interval, in points. */
  const spread = $derived(row?.ci ? Math.abs(row.ci[1] - row.ci[0]) * 50 : null);
  /** Five bars for a tight interval (±0.5 points or less), one for a loose one (over ±3.5). */
  const precision = $derived(
    spread === null ? 0 : spread <= 0.5 ? 5 : spread <= 1 ? 4 : spread <= 2 ? 3 : spread <= 3.5 ? 2 : 1,
  );
  const count = (n: number) =>
    n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1_000 ? `${(n / 1_000).toFixed(1)}K` : String(n);
  const title = $derived(
    `${name}${stronk && !on ? " (Stronk's pick)" : ""}${
      bare ? "" : row ? `: ${Math.round(row.share * 100)}% of games (${row.played.toLocaleString("en-US")}). ${explain(row)}` : ": not played in these games"
    }`,
  );
  const label = $derived(
    `${name}${
      bare || !row
        ? ""
        : row.wpa === null
          ? row.confidence === "too_few_games"
            ? " few games"
            : ""
          : ` ${percent(row.wpa)}${spread === null ? "" : ` ± ${spread.toFixed(1)}`}`
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
  {title}
  disabled={!onpick}
  onclick={() => onpick?.()}
>
  <span class="icons">
    {#each icons as i, n (n)}<Icon src={i.src} name={i.name} size={size === "sm" ? "sm" : "md"} />{/each}
  </span>
  {#if !bare}
    <span class="num {clear?.tone ?? ''}" class:few={row?.confidence === "too_few_games"}>
      {#if !row || (row.wpa === null && row.confidence !== "too_few_games")}–{:else if row.wpa === null}few{:else}{clear ? (clear.tone === "positive" ? "▲" : "▼") : ""}{percent(row.wpa)}{/if}
    </span>
    <span class="bars" aria-hidden="true">
      {#each [1, 2, 3, 4, 5] as b (b)}<span class:filled={b <= precision}></span>{/each}
    </span>
    <span class="games">{row ? count(row.played) : ""}</span>
  {/if}
</button>

<style>
  .cell {
    position: relative;
    display: grid;
    grid-template-rows: auto 15px 6px 14px;
    align-content: start;
    justify-items: center;
    gap: 1px;
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
    border-radius: 50%;
  }
  .icons :global(.icon) {
    border-radius: 50%;
    filter: grayscale(1);
    opacity: 0.45;
    transition: opacity 0.1s;
  }
  .cell:not(:disabled):hover .icons :global(.icon) {
    opacity: 0.8;
  }
  .on .icons :global(.icon) {
    filter: none;
    opacity: 1;
    box-shadow: 0 0 0 2px var(--color-accent);
  }
  .on:not(:disabled):hover .icons :global(.icon) {
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
    font-style: italic;
    font-weight: 400;
  }
  .bars {
    display: flex;
    gap: 2px;
    align-items: center;
  }
  .bars span {
    width: 5px;
    height: 3px;
    border-radius: 1px;
    background: var(--color-track);
  }
  .bars span.filled {
    background: var(--color-muted);
  }
  .on .bars span.filled {
    background: var(--color-accent);
  }
  .games {
    color: var(--color-muted);
    font-size: 10px;
    font-variant-numeric: tabular-nums;
  }
  @media (prefers-reduced-motion: reduce) {
    .icons :global(.icon) {
      transition: none;
    }
  }
</style>
