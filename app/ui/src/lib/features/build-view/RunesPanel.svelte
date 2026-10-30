<script lang="ts">
  // The rune page built by clicking (ADR-063), in the item lists' language: the primary tree's
  // keystones and rows, the secondary tree's rows, the shard rows, each row a line of rune cards
  // with their names and numbers; the cards outlined in amber are what the import writes. Each
  // tree is chosen by name from the others above it. The rules are the client's (ADR-059): one
  // rune per primary row, two secondary runes from different rows, one shard per row.
  import type { GameNames, Page, Plan } from "../../backend/backend.ts";
  import Icon from "../../ui/Icon.svelte";
  import { type Icons, icon, name } from "../../ui/labels.ts";
  import RuneCard from "./RuneCard.svelte";
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

  /** The client's shard rows, in order. */
  const SHARD_ROWS = ["Offense", "Flex", "Defense"];

  const trees = $derived(names.rune_trees);
  const styles = $derived(Object.keys(trees).map(Number));
  const primary = $derived(trees[String(page.primary_style)] ?? []);
  const secondary = $derived((trees[String(page.sub_style)] ?? []).slice(1));
  const stats = $derived(runeStats(plan));
  /** The secondary rune picked last, which the next pick from a new row keeps. */
  let lastSecondary = $state<number | null>(null);
  /** A secondary rune's numbers: those of the pair clicking it makes (ADR-060), measured as a pair. */
  const pairWith = (id: number) =>
    stats.pair(page.sub_style, withSecondaryRune(trees, page, id, lastSecondary).perks.slice(4, 6));
  const pickSecondary = (id: number) => {
    onpage(withSecondaryRune(trees, page, id, lastSecondary));
    lastSecondary = id;
  };
  const on = (id: number, from: number, to: number) => page.perks.slice(from, to).includes(id);
  const ours = (id: number, from: number, to: number) => !!stronk && stronk.perks.slice(from, to).includes(id);
  const rune = (id: number) => name(names, "runes", id);
  const runeIcon = (id: number) => icon(icons, "runes", id);
  const tree = (id: number) => name(names, "rune_styles", id);
</script>

{#snippet bar(current: number, others: number[], pick: (style: number) => void, tag: string)}
  <header class="bar">
    <Icon src={icon(icons, "rune_styles", current)} name={tree(current)} size="sm" round />
    <h4>{tree(current)}</h4>
    <span class="tag">{tag}</span>
    <span class="switch" role="group" aria-label={`${tag} tree`}>
      {#each others as style (style)}
        <button type="button" aria-label={tree(style)} onclick={() => pick(style)}>
          <Icon src={icon(icons, "rune_styles", style)} name={tree(style)} size="sm" round />
          {tree(style)}
        </button>
      {/each}
    </span>
  </header>
{/snippet}

<div class="runes" aria-label="Rune page">
  <section class="tree" aria-label={`${tree(page.primary_style)}, primary`}>
    {@render bar(
      page.primary_style,
      styles.filter((s) => s !== page.primary_style),
      (s) => onpage(withPrimaryTree(plan, trees, page, s)),
      "Primary",
    )}
    {#each primary as runes, r (r)}
      <div class="row" class:keystones={r === 0} style:--columns={runes.length}>
        {#each runes as id (id)}
          <RuneCard
            icon={runeIcon(id)}
            name={rune(id)}
            row={r === 0 ? stats.keystone(id) : stats.primary(page.primary_style, r, id)}
            on={on(id, r, r + 1)}
            stronk={ours(id, r, r + 1)}
            onpick={() => onpage(withPrimaryRune(page, r, id))}
          />
        {/each}
      </div>
    {/each}
  </section>

  <section class="tree" aria-label={`${tree(page.sub_style)}, secondary`}>
    {@render bar(
      page.sub_style,
      styles.filter((s) => s !== page.sub_style && s !== page.primary_style),
      (s) => onpage(withSecondaryTree(plan, trees, page, s)),
      "Secondary",
    )}
    <p class="hint">Two runes from different rows. Measured in pairs: each number is for the pair you get by clicking it.</p>
    {#each secondary as runes, r (r)}
      <div class="row" style:--columns={runes.length}>
        {#each runes as id (id)}
          <RuneCard
            icon={runeIcon(id)}
            name={rune(id)}
            row={pairWith(id)}
            on={on(id, 4, 6)}
            stronk={ours(id, 4, 6)}
            onpick={() => pickSecondary(id)}
          />
        {/each}
      </div>
    {/each}
  </section>

  <section class="tree" aria-label="Shards">
    <header class="bar"><h4>Shards</h4></header>
    {#each names.shard_rows as shards, r (r)}
      <div class="row shards" style:--columns={shards.length}>
        <span class="row-name">{SHARD_ROWS[r] ?? ""}</span>
        {#each shards as id (id)}
          <RuneCard
            icon={runeIcon(id)}
            name={rune(id)}
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

<style>
  .runes {
    display: grid;
    gap: var(--space-3);
  }
  .tree {
    display: grid;
    gap: 4px;
  }
  .bar {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: center;
  }
  h4 {
    margin: 0;
    font-size: var(--text-md);
  }
  .tag {
    color: var(--color-muted);
    font-size: var(--text-xs);
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }
  /* The other trees, by name: one click changes tree. */
  .switch {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    margin-left: auto;
  }
  .switch button {
    display: flex;
    gap: var(--space-1);
    align-items: center;
    padding: 2px var(--space-2) 2px 2px;
    border: 1px solid var(--color-border);
    border-radius: 999px;
    background: none;
    color: var(--color-muted);
    font: inherit;
    font-size: var(--text-xs);
    font-weight: 600;
    cursor: pointer;
  }
  .switch button:hover {
    border-color: var(--color-accent);
    color: var(--color-text);
  }
  .switch button:focus-visible {
    outline: 2px solid var(--color-accent);
  }
  .row {
    display: grid;
    grid-template-columns: repeat(var(--columns), minmax(0, 1fr));
    gap: 4px 6px;
  }
  .keystones {
    padding-bottom: 6px;
    border-bottom: 1px solid var(--color-border);
  }
  .shards {
    grid-template-columns: 64px repeat(var(--columns), minmax(0, 1fr));
    align-items: center;
  }
  .row-name {
    color: var(--color-muted);
    font-size: var(--text-xs);
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .hint {
    margin: 0;
    color: var(--color-muted);
    font-size: var(--text-xs);
  }
  @media (max-width: 640px) {
    .row {
      grid-template-columns: minmax(0, 1fr);
    }
    .shards {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
