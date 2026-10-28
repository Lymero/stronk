<script lang="ts">
  // The rune page built by clicking, laid out as the client does (ADR-058, ADR-059): the
  // primary tree with its keystones and rows, the secondary tree's rows, the shard rows. Every
  // rune shows its numbers; the lit ones are what the import writes. The tree icons at the top of
  // each panel switch trees.
  import type { GameNames, Page, Plan } from "../../backend/backend.ts";
  import Icon from "../../ui/Icon.svelte";
  import { games, type Icons, icon, name } from "../../ui/labels.ts";
  import Cell from "./Cell.svelte";
  import { explain, figure, verdict } from "./options.ts";
  import {
    runeStats,
    withPrimaryRune,
    withPrimaryTree,
    withSecondaryRune,
    withSecondaryTree,
    withShard,
  } from "./runes.ts";

  let {
    plan,
    page,
    stronk,
    names,
    icons,
    onpage,
  }: {
    plan: Plan;
    /** The page the import writes. */
    page: Page;
    /** Stronk's page, marked where the player changed it. */
    stronk: Page | null;
    names: GameNames;
    icons: Icons;
    onpage: (page: Page) => void;
  } = $props();

  const trees = $derived(names.rune_trees);
  const styles = $derived(Object.keys(trees).map(Number));
  const primary = $derived(trees[String(page.primary_style)] ?? []);
  const secondary = $derived((trees[String(page.sub_style)] ?? []).slice(1));
  const stats = $derived(runeStats(plan));
  const pair = $derived(stats.pair(page.sub_style, page.perks.slice(4, 6)));
  const on = (id: number, from: number, to: number) => page.perks.slice(from, to).includes(id);
  const ours = (id: number, from: number, to: number) => !!stronk && stronk.perks.slice(from, to).includes(id);
  const rune = (id: number) => [{ src: icon(icons, "runes", id), name: name(names, "runes", id) }];
  const tree = (id: number) => name(names, "rune_styles", id);
  /** The secondary rune picked last, which the next pick from a new row keeps. */
  let lastSecondary = $state<number | null>(null);
  const pickSecondary = (id: number) => {
    onpage(withSecondaryRune(trees, page, id, lastSecondary));
    lastSecondary = id;
  };
</script>

{#snippet switcher(current: number, others: number[], pickTree: (style: number) => void, tag: string)}
  <header class="tree-head">
    <Icon src={icon(icons, "rune_styles", current)} name={tree(current)} size="sm" round />
    <h4>{tree(current)}</h4>
    <span class="tag">{tag}</span>
    <span class="switch" role="group" aria-label={`${tag} tree`}>
      {#each others as style (style)}
        <button type="button" aria-label={tree(style)} title={tree(style)} onclick={() => pickTree(style)}>
          <Icon src={icon(icons, "rune_styles", style)} name={tree(style)} size="sm" round />
        </button>
      {/each}
    </span>
  </header>
{/snippet}

<div class="runes" aria-label="Rune page">
  <section class="panel primary" aria-label={`${tree(page.primary_style)}, primary`}>
    {@render switcher(
      page.primary_style,
      styles.filter((s) => s !== page.primary_style),
      (s) => onpage(withPrimaryTree(plan, trees, page, s)),
      "Primary",
    )}
    {#each primary as runes, r (r)}
      <div class="row" class:keystones={r === 0}>
        {#each runes as id (id)}
          <Cell
            icons={rune(id)}
            name={name(names, "runes", id)}
            row={r === 0 ? stats.keystone(id) : stats.primary(page.primary_style, r, id)}
            on={on(id, r, r + 1)}
            stronk={ours(id, r, r + 1)}
            onpick={() => onpage(withPrimaryRune(page, r, id))}
          />
        {/each}
      </div>
    {/each}
  </section>

  <div class="side">
    <section class="panel" aria-label={`${tree(page.sub_style)}, secondary`}>
      {@render switcher(
        page.sub_style,
        styles.filter((s) => s !== page.sub_style && s !== page.primary_style),
        (s) => onpage(withSecondaryTree(plan, trees, page, s)),
        "Secondary",
      )}
      {#each secondary as runes, r (r)}
        <div class="row">
          {#each runes as id (id)}
            <Cell
              icons={rune(id)}
              name={name(names, "runes", id)}
              row={undefined}
              bare
              on={on(id, 4, 6)}
              stronk={ours(id, 4, 6)}
              onpick={() => pickSecondary(id)}
            />
          {/each}
        </div>
      {/each}
      <p class="pair" title={pair ? explain(pair) : "This pair isn't played in these games"}>
        These two together:
        <strong class={pair ? (verdict(pair)?.tone ?? "") : ""}>
          {pair ? (figure(pair) ?? "few games") : "not played"}
        </strong>
        {#if pair}<span class="games">{games(pair.played)}</span>{/if}
      </p>
    </section>

    <section class="panel" aria-label="Shards">
      <header class="tree-head"><h4>Shards</h4></header>
      {#each names.shard_rows as shards, r (r)}
        <div class="row">
          {#each shards as id (id)}
            <Cell
              icons={rune(id)}
              name={name(names, "runes", id)}
              row={stats.shard(r, id)}
              size="sm"
              on={page.perks[6 + r] === id}
              stronk={stronk?.perks[6 + r] === id}
              onpick={() => onpage(withShard(page, r, id))}
            />
          {/each}
        </div>
      {/each}
    </section>
  </div>
</div>

<style>
  .runes {
    display: grid;
    grid-template-columns: auto auto;
    gap: var(--space-3);
    align-items: start;
  }
  .side {
    display: grid;
    gap: var(--space-3);
  }
  .panel {
    display: grid;
    gap: var(--space-1);
    justify-items: center;
    padding: 0 var(--space-2) var(--space-2);
    overflow: hidden;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
  }
  .tree-head {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    align-self: stretch;
    justify-self: stretch;
    margin: 0 calc(-1 * var(--space-2)) var(--space-1);
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--color-border);
    background: var(--color-bg);
  }
  .primary .tree-head {
    background: var(--color-accent-bg);
  }
  h4 {
    margin: 0;
    font-size: var(--text-md);
  }
  .tag {
    color: var(--color-muted);
    font-size: var(--text-xs);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .switch {
    display: flex;
    gap: 2px;
    margin-left: auto;
  }
  .switch button {
    display: grid;
    padding: 2px;
    border: 1px solid transparent;
    border-radius: 50%;
    background: none;
    cursor: pointer;
    opacity: 0.55;
  }
  .switch button:hover {
    border-color: var(--color-border);
    opacity: 1;
  }
  .switch button:focus-visible {
    outline: 2px solid var(--color-accent);
    opacity: 1;
  }
  .row {
    display: flex;
    gap: 2px;
    justify-content: center;
  }
  .keystones {
    align-self: stretch;
    justify-content: center;
    padding-bottom: var(--space-1);
    border-bottom: 1px solid var(--color-border);
  }
  .pair {
    margin: var(--space-1) 0 0;
    color: var(--color-muted);
    font-size: var(--text-xs);
    text-align: center;
  }
  .pair strong {
    color: var(--color-text);
    font-variant-numeric: tabular-nums;
  }
  .pair strong.positive {
    color: var(--color-positive);
  }
  .pair strong.negative {
    color: var(--color-negative);
  }
  .pair .games {
    display: block;
  }
  @media (max-width: 560px) {
    .runes {
      grid-template-columns: 1fr;
    }
  }
</style>
