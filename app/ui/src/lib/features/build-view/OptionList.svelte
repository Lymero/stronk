<script lang="ts" generics="T">
  // A slot's options as a list to pick from (ADR-049, ADR-051): the short list first, the rest on
  // request. One marker for what the import writes (the highlighted row); a number only when the
  // difference with the most played option is clear (ADR-056).
  import Icon from "../../ui/Icon.svelte";
  import { games } from "../../ui/labels.ts";
  import { percent, type Shown, type Slot, share, verdict } from "./options.ts";

  let {
    slot,
    label,
    detail,
    icons,
    onpick,
  }: {
    slot: Slot<T>;
    label: (value: T) => string;
    /** The option's icons, before its name (an item's, a spell pair's, a page's keystone and
     * secondary tree). */
    icons?: (value: T) => { src: string | null; name: string }[];
    /** A second, quieter line for an option (the rest of a rune page); none when empty. */
    detail?: (value: T) => string;
    /** The player clicked an option: import it instead of Stronk's choice. */
    onpick: (value: T) => void;
  } = $props();

  /** Every option, after the player asked for them; the short list otherwise. */
  let all = $state(false);
  const rows = $derived(all ? slot.rows : slot.rows.filter((r) => r.shown));

  const title = (r: Shown<T>) => {
    if (r.confidence === "too_few_games") return "Too few comparable games for its numbers to mean much";
    if (r.wpa === null || !verdict(r)) return "Not distinguishable from the most played option with the games so far";
    const interval = r.ci ? `, 95% interval ${percent(r.ci[0])} to ${percent(r.ci[1])}` : "";
    const word = r.confidence === "clearly_better" ? "more" : "less";
    return `Wins ${word} often than the most played option: ${percent(r.wpa)} win probability${interval}`;
  };
</script>

<ol class="options">
  {#each rows as row (row.key)}
    {@const more = detail?.(row.value)}
    {@const clear = verdict(row)}
    <li>
      <button
        type="button"
        class="option"
        class:selected={row.selected}
        class:few={row.confidence === "too_few_games"}
        aria-pressed={row.selected}
        title={title(row)}
        onclick={() => onpick(row.value)}
      >
        <span class="mark" aria-hidden="true"></span>
        <span class="body">
          <span class="line">
            {#each icons?.(row.value) ?? [] as i, n (n)}<Icon src={i.src} name={i.name} size="sm" />{/each}
            <span class="name">{label(row.value)}</span>
            {#if row.chosen && !row.selected}<span class="hint">Stronk's pick</span>{/if}
            {#if clear}<span class="verdict {clear.tone}">{clear.text}</span>{/if}
          </span>
          {#if more}<span class="detail">{more}</span>{/if}
          <span class="line stats">
            <span class="bar" aria-hidden="true"><span style:width={share(row.share)}></span></span>
            <span>{share(row.share)} · {games(row.played)}</span>
            {#if row.confidence === "too_few_games"}<span>· few games</span>{/if}
            {#if row.fragile}<span title="A modest hidden factor could overturn this">· fragile</span>{/if}
          </span>
        </span>
      </button>
    </li>
  {/each}
</ol>
{#if slot.more > 0}
  <button type="button" class="more" aria-expanded={all} onclick={() => (all = !all)}>
    {all ? "Show fewer" : `Show ${slot.more} more`}
  </button>
{/if}

<style>
  .options {
    display: grid;
    gap: 2px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .option {
    display: flex;
    gap: var(--space-3);
    align-items: flex-start;
    width: 100%;
    padding: var(--space-2) var(--space-3);
    border: 1px solid transparent;
    border-radius: var(--radius);
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .option:hover {
    background: var(--color-bg);
  }
  .option:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: 1px;
  }
  .option.selected {
    border-color: var(--color-accent);
    background: var(--color-accent-bg);
  }
  .option.few .name {
    color: var(--color-muted);
    font-weight: 500;
  }
  .mark {
    flex: 0 0 auto;
    width: 14px;
    height: 14px;
    margin-top: 3px;
    border: 2px solid var(--color-border);
    border-radius: 50%;
  }
  .selected .mark {
    border: 4px solid var(--color-accent);
    background: var(--color-surface);
  }
  .body {
    display: grid;
    flex: 1 1 auto;
    gap: 2px;
    min-width: 0;
  }
  .line {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    min-width: 0;
  }
  .name {
    flex: 0 1 auto;
    min-width: 0;
    font-weight: 600;
  }
  .hint {
    color: var(--color-accent);
    font-size: var(--text-xs);
    font-weight: 600;
    white-space: nowrap;
  }
  .verdict {
    margin-left: auto;
    font-size: var(--text-sm);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .verdict.positive {
    color: var(--color-positive);
  }
  .verdict.negative {
    color: var(--color-negative);
  }
  .detail {
    color: var(--color-muted);
    font-size: var(--text-sm);
  }
  .stats {
    color: var(--color-muted);
    font-size: var(--text-xs);
    font-variant-numeric: tabular-nums;
  }
  .bar {
    flex: 0 0 56px;
    height: 4px;
    overflow: hidden;
    border-radius: 2px;
    background: var(--color-track);
  }
  .bar span {
    display: block;
    height: 100%;
    background: var(--color-muted);
  }
  .selected .bar span {
    background: var(--color-accent);
  }
  .more {
    justify-self: start;
    margin: var(--space-1) 0 0 calc(var(--space-3) + 14px + var(--space-3));
    padding: 0;
    border: none;
    background: none;
    color: var(--color-accent);
    font: inherit;
    font-size: var(--text-sm);
    cursor: pointer;
  }
  .more:hover {
    text-decoration: underline;
  }
  .more:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: 1px;
  }
</style>
