<script lang="ts">
  // One option as its icon and its estimate (ADR-060): a ring around the icon filled by its share
  // of games, its 95% interval drawn against zero, and its wins per 100 games, coloured only when
  // clearly better or worse. Games and the full reading are in its title. Lit when the import
  // writes it; clicking it picks it.
  import type { Row } from "../../backend/backend.ts";
  import Icon from "../../ui/Icon.svelte";
  import { explain, spread, verdict, wins } from "./options.ts";

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

  /** The interval's scale: ±2.5 wins per 100 games across the glyph; wider intervals run off it. */
  const RANGE = 0.025;
  const W = 52;
  const x = (v: number) => W / 2 + (Math.max(-RANGE, Math.min(RANGE, v)) / RANGE) * (W / 2 - 2);

  const clear = $derived(row ? verdict(row) : null);
  const tone = $derived(clear?.tone ?? "");
  const half = $derived(row?.ci ? spread(row.ci) : null);
  const games = $derived(row ? `${Math.round(row.share * 100)}% of games (${row.played.toLocaleString("en-US")})` : "");
  const title = $derived(
    `${name}${stronk && !on ? " (Stronk's pick)" : ""}${
      bare ? "" : row ? `: ${games}. ${explain(row)}` : ": not played in these games"
    }`,
  );
  const label = $derived(
    `${name}${
      bare || !row
        ? ""
        : row.wpa === null
          ? row.confidence === "too_few_games"
            ? ", too few games"
            : ""
          : ` ${wins(row.wpa)}${half === null ? "" : ` ± ${half.toFixed(1)}`} wins per 100`
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
    {#each icons as i, n (n)}
      <span class="ring" style:--share={bare || !row ? 0 : row.share}>
        <Icon src={i.src} name={i.name} size={size === "sm" ? "sm" : "md"} />
      </span>
    {/each}
  </span>
  {#if !bare}
    <svg class="interval {tone}" viewBox={`0 0 ${W} 10`} width={W} height="10" aria-hidden="true">
      {#if row?.wpa != null}
        <line class="zero" x1={W / 2} x2={W / 2} y1="1" y2="9" />
        {#if row.ci}<line class="ci" x1={x(row.ci[0])} x2={x(row.ci[1])} y1="5" y2="5" />{/if}
        <circle cx={x(row.wpa)} cy="5" r="2.5" />
      {:else if row?.confidence === "too_few_games"}
        <line class="few" x1="2" x2={W - 2} y1="5" y2="5" />
      {/if}
    </svg>
    <span class="num {tone}">
      {#if row?.wpa != null}{clear ? (clear.tone === "positive" ? "▲" : "▼") : ""}{wins(row.wpa)}{/if}
    </span>
  {/if}
</button>

<style>
  .cell {
    position: relative;
    display: grid;
    grid-template-rows: auto 10px 14px;
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
    display: grid;
    padding: 4px;
    border-radius: 50%;
    background:
      radial-gradient(closest-side, var(--color-surface) calc(100% - 3px), transparent calc(100% - 3px)),
      conic-gradient(var(--ring, var(--color-muted)) calc(var(--share) * 1turn), var(--color-track) 0);
  }
  .bare .ring {
    background: none;
  }
  .on .ring {
    --ring: var(--color-accent);
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
  .interval {
    overflow: visible;
    color: var(--color-muted);
  }
  .interval .zero {
    stroke: var(--color-border);
    stroke-width: 1;
  }
  .interval .ci {
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
    opacity: 0.55;
  }
  .interval circle {
    fill: currentColor;
  }
  .interval .few {
    stroke: var(--color-border);
    stroke-width: 2;
    stroke-dasharray: 2 3;
  }
  .on .interval {
    color: var(--color-text);
  }
  .interval.positive {
    color: var(--color-positive);
  }
  .interval.negative {
    color: var(--color-negative);
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
  @media (prefers-reduced-motion: reduce) {
    .ring :global(.icon) {
      transition: none;
    }
  }
</style>
