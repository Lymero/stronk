<script lang="ts" module>
  let next = 0;
</script>

<script lang="ts">
  // One option as its icon and its estimate (ADR-060): a ring around the icon filled by its share
  // of games and its wins per 100 games (coloured only when clearly better or worse). Its games,
  // its 95% interval and what they mean are in a tooltip on hover or focus, fixed to the window
  // so no panel clips it. Lit when the import writes it; clicking it picks it.
  import type { Row } from "../../backend/backend.ts";
  import Icon from "../../ui/Icon.svelte";
  import { details, spread, verdict, wins } from "./options.ts";

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
  const read = $derived(row ? details(row) : null);
  /** Whose choice it is: Stronk's, the player's (imported instead of Stronk's), or neither. */
  const pick = $derived(stronk ? (on ? "Stronk's pick, imported" : "Stronk's pick") : on ? "Your pick" : "");

  const tipId = `cell-tip-${next++}`;
  const TIP_WIDTH = 240;
  let button: HTMLButtonElement | undefined = $state();
  let tip: { x: number; y: number; above: boolean } | null = $state(null);
  /** Shows the tooltip under the cell, or above it near the window's bottom, inside the window. */
  function show() {
    if (!button) return;
    const r = button.getBoundingClientRect();
    const above = r.bottom + 160 > window.innerHeight && r.top > 160;
    const x = Math.min(Math.max(8, r.left + r.width / 2 - TIP_WIDTH / 2), window.innerWidth - TIP_WIDTH - 8);
    tip = { x, y: above ? window.innerHeight - r.top + 6 : r.bottom + 6, above };
  }
  const hide = () => (tip = null);
  // Fixed to the window, the tooltip would stay behind on scroll: it closes instead.
  $effect(() => {
    if (!tip) return;
    window.addEventListener("scroll", hide, { capture: true, passive: true });
    return () => window.removeEventListener("scroll", hide, { capture: true });
  });
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
  aria-describedby={tip ? tipId : undefined}
  disabled={!onpick}
  bind:this={button}
  onclick={() => onpick?.()}
  onpointerenter={show}
  onpointerleave={hide}
  onfocus={show}
  onblur={hide}
  onkeydown={(e) => e.key === "Escape" && hide()}
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
    <span class="num {tone}" class:few={row?.wpa == null}>
      {#if row?.wpa != null}{clear ? (clear.tone === "positive" ? "▲" : "▼") : ""}{wins(row.wpa)}{:else if row?.confidence === "too_few_games"}few games{/if}
    </span>
  {/if}
  {#if tip}
    <span
      class="tip"
      id={tipId}
      role="tooltip"
      style:left={`${tip.x}px`}
      style:top={tip.above ? null : `${tip.y}px`}
      style:bottom={tip.above ? `${tip.y}px` : null}
      style:width={`${TIP_WIDTH}px`}
    >
      <span class="tip-head">
        <strong>{name}</strong>
        {#if pick}<span class="tip-pick">{pick}</span>{/if}
      </span>
      {#if bare}
        <span class="tip-muted">Measured with the other secondary rune, as a pair: see under the tree.</span>
      {:else if !read}
        <span class="tip-muted">Not played in these games.</span>
      {:else}
        {#if read.value}
          <span class="tip-value {read.verdict.tone}">{read.value}</span>
          <span class="tip-muted">{read.against}</span>
        {/if}
        {#if read.range}<span>{read.range}</span>{/if}
        <span class="tip-verdict {read.verdict.tone}">{read.verdict.text}</span>
        <span class="tip-muted">{read.games}</span>
      {/if}
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
  .tip {
    position: fixed;
    z-index: 10;
    display: grid;
    gap: 2px;
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    box-shadow: var(--shadow);
    color: var(--color-text);
    font-size: var(--text-sm);
    font-weight: 400;
    line-height: 1.35;
    text-align: left;
    white-space: normal;
    pointer-events: none;
  }
  .tip-head {
    display: grid;
    margin-bottom: 2px;
  }
  .tip-pick {
    color: var(--color-accent);
    font-size: var(--text-xs);
    font-weight: 600;
  }
  .tip-value {
    font-size: var(--text-md);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .tip-verdict {
    margin-top: 2px;
    font-weight: 600;
  }
  .tip-muted,
  .tip-verdict.muted {
    color: var(--color-muted);
  }
  .tip-verdict.muted {
    font-weight: 400;
  }
  .positive {
    color: var(--color-positive);
  }
  .negative {
    color: var(--color-negative);
  }
  @media (prefers-reduced-motion: reduce) {
    .ring :global(.icon) {
      transition: none;
    }
  }
</style>
