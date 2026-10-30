<script lang="ts">
  // The rune page built by clicking, drawn as the client draws it (ADR-063): the primary tree
  // (keystones, then three rows), the secondary tree and the shards side by side, each row of round
  // icons, the picked ones lit and ringed in amber. Under each row, the picked rune's name, its
  // number and its share of games, so the page reads without knowing the icons; the others' numbers sit under their icons.
  // The other trees are one click away beside each tree's name. The rules are the client's (ADR-059): one
  // rune per primary row, two secondary runes from different rows, one shard per row.
  import type { GameNames, Page, Plan } from "../../backend/backend.ts";
  import Icon from "../../ui/Icon.svelte";
  import { type Icons, icon, name } from "../../ui/labels.ts";
  import Rune from "./Rune.svelte";
  import { reading } from "./options.ts";
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
  /** Under a row: its picked rune's name and what it shows. */
  const pickOf = (runes: number[], picked: number[]) => runes.find((id) => picked.includes(id));
</script>

{#snippet bar(current: number, others: number[], pick: (style: number) => void, tag: string)}
  <header class="bar">
    <Icon src={icon(icons, "rune_styles", current)} name={tree(current)} size="md" round />
    <span class="title">
      <h4>{tree(current)}</h4>
      <span class="tag">{tag}</span>
    </span>
    <span class="switch" role="group" aria-label={`${tag} tree`}>
      {#each others as style (style)}
        <button type="button" aria-label={tree(style)} title={tree(style)} onclick={() => pick(style)}>
          <Icon src={icon(icons, "rune_styles", style)} name={tree(style)} size="sm" round />
        </button>
      {/each}
    </span>
  </header>
{/snippet}

{#snippet picked(id: number | undefined, row: ReturnType<typeof stats.keystone>)}
  {@const read = reading(row)}
  <p class="pick">
    {#if id !== undefined}
      <strong>{rune(id)}</strong>
      {#if read.number}<span class="num {read.tone}">{read.number}</span>{:else if read.note}<span class="note">{read.note}</span>{/if}
      <!-- Its share of games: 97% says nearly everyone takes it; 54%, a real choice. -->
      {#if row}<span class="note">{Math.round(row.share * 100)}%</span>{/if}
    {/if}
  </p>
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
      {@const statsOf = (id: number) => (r === 0 ? stats.keystone(id) : stats.primary(page.primary_style, r, id))}
      {@const chosen = pickOf(runes, [page.perks[r] ?? -1])}
      <div class="row" class:keystones={r === 0}>
        {#each runes as id (id)}
          <Rune
            icon={runeIcon(id)}
            name={rune(id)}
            row={statsOf(id)}
            size={r === 0 ? "lg" : "md"}
            on={on(id, r, r + 1)}
            stronk={ours(id, r, r + 1)}
            onpick={() => onpage(withPrimaryRune(page, r, id))}
          />
        {/each}
      </div>
      {@render picked(chosen, chosen === undefined ? undefined : statsOf(chosen))}
    {/each}
  </section>

  <section class="tree" aria-label={`${tree(page.sub_style)}, secondary`}>
    {@render bar(
      page.sub_style,
      styles.filter((s) => s !== page.sub_style && s !== page.primary_style),
      (s) => onpage(withSecondaryTree(plan, trees, page, s)),
      "Secondary",
    )}
    {#each secondary as runes, r (r)}
      {@const chosen = pickOf(runes, page.perks.slice(4, 6))}
      <div class="row">
        {#each runes as id (id)}
          <Rune
            icon={runeIcon(id)}
            name={rune(id)}
            row={pairWith(id)}
            on={on(id, 4, 6)}
            stronk={ours(id, 4, 6)}
            onpick={() => pickSecondary(id)}
          />
        {/each}
      </div>
      {@render picked(chosen, chosen === undefined ? undefined : pairWith(chosen))}
    {/each}
    <p class="hint">Two from different rows; their number is for the pair.</p>
  </section>

  <section class="tree" aria-label="Shards">
    <header class="bar"><span class="title"><h4>Shards</h4></span></header>
    {#each names.shard_rows as shards, r (r)}
      {@const chosen = pickOf(shards, [page.perks[6 + r] ?? -1])}
      <div class="row shards">
        <span class="row-name">{SHARD_ROWS[r] ?? ""}</span>
        {#each shards as id (id)}
          <Rune
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
      {@render picked(chosen, chosen === undefined ? undefined : stats.shard(r, chosen))}
    {/each}
  </section>
</div>

<style>
  /* The trees side by side, as in the client. */
  .runes {
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr) minmax(0, 0.95fr);
    gap: var(--space-4);
    align-items: start;
  }
  .tree {
    display: grid;
    gap: 2px;
    justify-items: center;
    padding: var(--space-3);
    border-radius: var(--radius-lg);
    background: var(--color-raised);
  }
  .bar {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    justify-self: stretch;
    margin-bottom: var(--space-2);
  }
  .title {
    display: grid;
  }
  h4 {
    margin: 0;
    font-size: var(--text-md);
    line-height: 1.2;
    white-space: nowrap;
  }
  .tag {
    color: var(--color-muted);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .switch {
    display: flex;
    gap: 2px;
    margin-left: auto;
  }
  .switch button {
    display: grid;
    padding: 1px;
    border: 1px solid transparent;
    border-radius: 50%;
    background: none;
    cursor: pointer;
    opacity: 0.6;
  }
  .switch button:hover {
    border-color: var(--color-accent);
    opacity: 1;
  }
  .switch button:focus-visible {
    outline: 2px solid var(--color-accent);
  }
  .row {
    display: flex;
    gap: var(--space-3);
    justify-content: center;
  }
  .keystones {
    gap: var(--space-2);
  }
  .shards {
    align-items: center;
    gap: var(--space-3);
  }
  .row-name {
    width: 52px;
    color: var(--color-muted);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-align: right;
    text-transform: uppercase;
  }
  /* The picked rune of the row, by name. */
  .pick {
    display: flex;
    gap: var(--space-2);
    justify-content: center;
    min-height: 18px;
    margin: 0 0 var(--space-2);
    font-size: var(--text-sm);
    white-space: nowrap;
  }
  .pick .num {
    font-variant-numeric: tabular-nums;
    font-weight: 700;
  }
  .pick .num.positive {
    color: var(--color-positive);
  }
  .pick .num.negative {
    color: var(--color-negative);
  }
  .pick .note {
    color: var(--color-muted);
    font-size: var(--text-xs);
  }
  .hint {
    margin: var(--space-1) 0 0;
    color: var(--color-muted);
    font-size: var(--text-xs);
    text-align: center;
  }
  @media (max-width: 900px) {
    .runes {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
