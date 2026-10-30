<script lang="ts" generics="T">
  // One slot's options as a ranked list (ADR-062): each with its name, its wins per 100 games
  // against the baseline (the most played option, 0), its share of games as a bar, and the games
  // it was played in. Coloured
  // only when clearly better or worse; nothing when short of games. Clicking a row picks it. The
  // rarely played ones are behind "Show N more".
  import Icon from "../../ui/Icon.svelte";
  import { games } from "../../ui/labels.ts";
  import { compared, figure, type Shown, type Slot, verdict, wins } from "./options.ts";

  let {
    slot,
    label,
    icons,
    onpick,
    elsewhere = () => null,
  }: {
    slot: Slot<T>;
    label: (value: T) => string;
    icons: (value: T) => { src: string | null; name: string }[];
    onpick: (value: T) => void;
    /** Where else the build already has this option ("in item 5"), so a slot passes over it. */
    elsewhere?: (value: T) => string | null;
  } = $props();

  const MIN_SHARE = 0.02;
  let all = $state(false);
  const main = $derived(slot.rows.filter((r) => r.shown || r.share >= MIN_SHARE));
  const rows = $derived(all ? slot.rows : main);
  const hidden = $derived(slot.rows.length - main.length);
  const scaled = $derived(compared(slot));

  /** What the number column says: the difference with the baseline, 0 for it, or why none. */
  function number(row: Shown<T>): { text: string; tone: string } {
    if (row.confidence === "most_played") return { text: row.wpa === null || !scaled ? "" : "0", tone: "" };
    if (row.confidence === "almost_always") return { text: "almost always", tone: "note" };
    if (row.confidence === "too_few_to_compare") return { text: "too few to compare", tone: "note" };
    if (figure(row) === null || row.wpa === null) return { text: "", tone: "" };
    const clear = verdict(row);
    return { text: `${clear ? (clear.tone === "positive" ? "▲ " : "▼ ") : ""}${wins(row.wpa)}`, tone: clear?.tone ?? "" };
  }
</script>

<div class="table" role="radiogroup" aria-label="Options">
  {#each rows as row (row.key)}
    {@const n = number(row)}
    <button
      type="button"
      role="radio"
      class="row"
      class:on={row.selected}
      aria-checked={row.selected}
      aria-label={`${label(row.value)}${n.text ? `, ${n.text}` : ""}, ${Math.round(row.share * 100)}% of games, ${games(row.played)}`}
      onclick={() => onpick(row.value)}
    >
      <span class="mark" aria-hidden="true"></span>
      <span class="icons">{#each icons(row.value) as i, k (k)}<Icon src={i.src} name={i.name} size="md" round />{/each}</span>
      <span class="name">
        <span class="label">{label(row.value)}</span>
        {#if row.confidence === "most_played" && scaled}<span class="tag">baseline</span>{/if}
        {#if row.chosen && !row.selected}<span class="tag stronk">Stronk's pick</span>{/if}
        {#if elsewhere(row.value)}<span class="tag">{elsewhere(row.value)}</span>{/if}
      </span>
      <span class="num {n.tone}">{n.text}</span>
      <span class="share">
        <span class="bar"><span style:width={`${Math.max(2, row.share * 100)}%`}></span></span>
        <span class="pct">{Math.round(row.share * 100)}%</span>
      </span>
      <span class="games">{games(row.played)}</span>
    </button>
  {/each}
  {#if hidden > 0}
    <button type="button" class="more" aria-expanded={all} onclick={() => (all = !all)}>
      {all ? "Show fewer" : `Show ${hidden} more, rarely played`}
    </button>
  {/if}
</div>

<style>
  .table {
    display: grid;
    gap: 2px;
  }
  .row {
    display: grid;
    grid-template-columns: 6px auto minmax(0, 1fr) 120px 140px 96px;
    gap: var(--space-3);
    align-items: center;
    padding: var(--space-2) var(--space-3) var(--space-2) 0;
    border: 1px solid transparent;
    border-radius: var(--radius);
    background: none;
    color: var(--color-text);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .row:hover {
    background: var(--color-raised);
  }
  .row.on {
    border-color: var(--color-accent);
    background: var(--color-accent-bg);
  }
  .row:focus-visible {
    outline: 2px solid var(--color-accent);
  }
  .mark {
    align-self: stretch;
    border-radius: 0 3px 3px 0;
  }
  .on .mark {
    background: var(--color-accent);
  }
  .icons {
    display: flex;
    gap: 3px;
  }
  .icons :global(.icon) {
    filter: grayscale(0.6);
    opacity: 0.75;
  }
  .on .icons :global(.icon),
  .row:hover .icons :global(.icon) {
    filter: none;
    opacity: 1;
  }
  /* The name gives way before its tags do. */
  .name {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    min-width: 0;
    font-weight: 500;
  }
  .label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .tag {
    flex: none;
    padding: 1px 6px;
    border: 1px solid var(--color-border);
    border-radius: 999px;
    color: var(--color-muted);
    font-size: var(--text-xs);
    font-weight: 600;
  }
  .tag.stronk {
    border-color: var(--color-accent);
    color: var(--color-accent);
  }
  .num {
    color: var(--color-muted);
    font-size: var(--text-md);
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    text-align: right;
  }
  .on .num {
    color: var(--color-text);
  }
  .num.positive {
    color: var(--color-positive);
  }
  .num.negative {
    color: var(--color-negative);
  }
  .num.note {
    font-size: var(--text-xs);
    font-weight: 400;
  }
  .share {
    display: grid;
    grid-template-columns: 1fr 36px;
    gap: var(--space-2);
    align-items: center;
  }
  .bar {
    height: 6px;
    overflow: hidden;
    border-radius: 3px;
    background: var(--color-track);
  }
  .bar span {
    display: block;
    height: 100%;
    border-radius: 3px;
    background: var(--color-muted);
  }
  .on .bar span {
    background: var(--color-accent);
  }
  .pct {
    color: var(--color-muted);
    font-size: var(--text-sm);
    font-variant-numeric: tabular-nums;
    text-align: right;
  }
  .games {
    color: var(--color-muted);
    font-size: var(--text-sm);
    font-variant-numeric: tabular-nums;
    text-align: right;
    white-space: nowrap;
  }
  .more {
    justify-self: start;
    margin-top: var(--space-2);
    padding: var(--space-1) var(--space-3);
    border: 1px dashed var(--color-border);
    border-radius: 999px;
    background: none;
    color: var(--color-accent);
    font: inherit;
    font-size: var(--text-sm);
    cursor: pointer;
  }
  .more:focus-visible {
    outline: 2px solid var(--color-accent);
  }
  @media (max-width: 640px) {
    .row {
      grid-template-columns: 6px auto minmax(0, 1fr) auto;
      row-gap: 0;
    }
    .mark {
      grid-row: span 2;
    }
    .icons {
      grid-row: span 2;
    }
    /* The games under the name, so the name keeps its width. */
    .games {
      grid-row: 2;
      grid-column: 3;
      font-size: var(--text-xs);
      text-align: left;
    }
    .share {
      display: none;
    }
  }
</style>
