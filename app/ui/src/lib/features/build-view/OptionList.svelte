<script lang="ts" generics="T">
  import Icon from "../../ui/Icon.svelte";
  import { games } from "../../ui/labels.ts";
  import type { Confidence } from "../../backend/backend.ts";
  import { percent, type Shown, type Slot, share } from "./options.ts";

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

  const CONFIDENCE: Record<Confidence, { text: string; title: string }> = {
    clearly_better: {
      text: "Clearly better",
      title: "Wins more often than the most played option, and the difference holds once false discoveries are controlled",
    },
    clearly_worse: {
      text: "Clearly worse",
      title: "Wins less often than the most played option, and the difference holds once false discoveries are controlled",
    },
    most_played: { text: "Most played", title: "The option the others are compared with" },
    no_clear_difference: {
      text: "No clear difference",
      title: "Not distinguishable from the most played option with the games so far",
    },
    too_few_games: { text: "Too few games", title: "Too few comparable games for its numbers to mean much" },
    not_estimated: { text: "Not estimated", title: "No win impact is published for this yet" },
  };

  /** Every option, after the player asked for them; the short list otherwise. */
  let all = $state(false);
  const rows = $derived(all ? slot.rows : slot.rows.filter((r) => r.shown));

  const impactTitle = (r: Shown<T>) => {
    const against = r.versus === "most_played" ? "against the most played option" : "against the alternatives";
    const interval = r.ci ? `, 95% interval ${percent(r.ci[0])} to ${percent(r.ci[1])}` : "";
    return `Win probability added ${against}${interval}`;
  };
</script>

<ol class="options">
  {#each rows as row (row.key)}
    {@const more = detail?.(row.value)}
    <li>
      <button
        type="button"
        class="option"
        class:selected={row.selected}
        aria-pressed={row.selected}
        title={row.selected ? "What the import writes" : "Import this instead"}
        onclick={() => onpick(row.value)}
      >
        <span class="line">
          {#each icons?.(row.value) ?? [] as i, n (n)}<Icon src={i.src} name={i.name} />{/each}
          <span class="name">{label(row.value)}</span>
          {#if row.chosen}<span class="pick">Stronk's pick</span>{/if}
          {#if row.selected && !row.chosen}<span class="pick yours">Your pick</span>{/if}
          <span class="confidence {row.confidence}" title={CONFIDENCE[row.confidence].title}>
            {CONFIDENCE[row.confidence].text}{#if row.fragile}<span title="A modest hidden factor could overturn this">{" · fragile"}</span>{/if}
          </span>
        </span>
        {#if more}<span class="detail">{more}</span>{/if}
        <span class="line stats">
          <span class="bar" aria-hidden="true"><span style:width={share(row.share)}></span></span>
          <span>{share(row.share)} · {games(row.played)}</span>
          {#if row.wpa !== null}
            <span
              class="impact"
              class:positive={row.confidence === "clearly_better"}
              class:negative={row.confidence === "clearly_worse"}
              title={impactTitle(row)}>{percent(row.wpa)} win</span
            >
          {/if}
        </span>
      </button>
    </li>
  {/each}
</ol>
{#if slot.more > 0}
  <button type="button" class="more" aria-expanded={all} onclick={() => (all = !all)}>
    {all ? "Fewer options" : `${slot.more} more ${slot.more === 1 ? "option" : "options"}, each played less`}
  </button>
{/if}

<style>
  .options {
    display: grid;
    gap: var(--space-1);
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .option {
    display: block;
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
    border-color: var(--color-border);
  }
  .option:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: 1px;
  }
  .option.selected {
    border-color: var(--color-accent);
    background: var(--color-accent-bg);
  }
  .line {
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }
  .name {
    font-weight: 600;
  }
  .pick.yours {
    background: var(--color-positive);
  }
  .pick {
    padding: 0 var(--space-2);
    border-radius: var(--radius);
    background: var(--color-accent);
    color: var(--color-surface);
    font-size: var(--text-xs);
    font-weight: 600;
    white-space: nowrap;
  }
  .confidence {
    margin-left: auto;
    color: var(--color-muted);
    font-size: var(--text-sm);
    white-space: nowrap;
  }
  .confidence.clearly_better {
    color: var(--color-positive);
    font-weight: 600;
  }
  .confidence.clearly_worse {
    color: var(--color-negative);
    font-weight: 600;
  }
  .confidence.too_few_games {
    color: var(--color-warning);
  }
  .detail {
    display: block;
    margin: 0;
    color: var(--color-muted);
    font-size: var(--text-sm);
  }
  .stats {
    margin-top: var(--space-1);
    color: var(--color-muted);
    font-size: var(--text-sm);
  }
  .bar {
    flex: 0 0 72px;
    height: 6px;
    overflow: hidden;
    border-radius: var(--radius);
    background: var(--color-track);
  }
  .bar span {
    display: block;
    height: 100%;
    background: var(--color-muted);
  }
  .option.selected .bar span {
    background: var(--color-accent);
  }
  .impact {
    margin-left: auto;
    font-variant-numeric: tabular-nums;
  }
  .impact.positive {
    color: var(--color-positive);
  }
  .impact.negative {
    color: var(--color-negative);
  }
  .more {
    margin: var(--space-1) var(--space-2) 0;
    padding: 0 var(--space-1);
    border: none;
    background: none;
    color: var(--color-accent);
    font: inherit;
    font-size: var(--text-sm);
    text-align: left;
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
