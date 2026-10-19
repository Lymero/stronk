<script lang="ts" generics="T">
  import { games } from "../../ui/labels.ts";
  import type { Confidence, Row, Slot } from "./options.ts";

  let {
    slot,
    label,
    detail,
  }: {
    slot: Slot<T>;
    label: (value: T) => string;
    /** A second, quieter line for an option (the rest of a rune page). */
    detail?: (value: T) => string;
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

  const percent = (v: number) => `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(1)}%`;
  const share = (v: number) => `${Math.round(v * 100)}%`;
  const impactTitle = (r: Row<T>) => {
    const against = r.versus === "most_played" ? "against the most played option" : "against the alternatives";
    const interval = r.ci ? `, 95% interval ${percent(r.ci[0])} to ${percent(r.ci[1])}` : "";
    return `Win probability added ${against}${interval}`;
  };
</script>

<ol class="options">
  {#each slot.rows as row (row.key)}
    <li class:chosen={row.chosen}>
      <div class="line">
        <span class="name">{label(row.value)}</span>
        {#if row.chosen}<span class="pick">Stronk's pick</span>{/if}
        <span class="confidence {row.confidence}" title={CONFIDENCE[row.confidence].title}>
          {CONFIDENCE[row.confidence].text}{#if row.fragile}<span title="A modest hidden factor could overturn this">{" · fragile"}</span>{/if}
        </span>
      </div>
      {#if detail}<p class="detail">{detail(row.value)}</p>{/if}
      <div class="line stats">
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
      </div>
    </li>
  {/each}
</ol>
{#if slot.more > 0}
  <p class="more">{slot.more} more {slot.more === 1 ? "option" : "options"}, each played less</p>
{/if}

<style>
  .options {
    display: grid;
    gap: var(--space-1);
    margin: 0;
    padding: 0;
    list-style: none;
  }
  li {
    padding: var(--space-2) var(--space-3);
    border: 1px solid transparent;
    border-radius: var(--radius);
  }
  li.chosen {
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
  .pick {
    padding: 0 var(--space-2);
    border-radius: var(--radius);
    background: var(--color-accent);
    color: var(--color-surface);
    font-size: var(--text-xs);
    font-weight: 600;
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
  li.chosen .bar span {
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
    margin: var(--space-1) var(--space-3) 0;
    color: var(--color-muted);
    font-size: var(--text-sm);
  }
</style>
