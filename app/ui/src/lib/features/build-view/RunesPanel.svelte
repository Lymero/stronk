<script lang="ts">
  // The rune page built by clicking (ADR-063), in the item lists' language: three columns, as the
  // client sets its trees side by side, the primary tree (keystones and three rows), the secondary
  // tree's three rows and the shard rows, each row a short list, one rune per line with its name,
  // games and number; the lines outlined in amber are what the import writes. Each tree is chosen
  // by name from the others under its title. The rules are the client's (ADR-059): one
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
  /** A primary tree's rows: the keystones, then rows 1 to 3. */
  const rowName = (r: number) => (r === 0 ? "Keystone" : `Row ${r}`);

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
        <button type="button" aria-label={tree(style)} title={tree(style)} onclick={() => pick(style)}>
          <Icon src={icon(icons, "rune_styles", style)} name={tree(style)} size="sm" round />
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
      <span class="row-name">{rowName(r)}</span>
      <div class="row" class:keystones={r === 0}>
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
    <p class="hint">Two from different rows; each number is for the pair it makes.</p>
    {#each secondary as runes, r (r)}
      <span class="row-name">{rowName(r + 1)}</span>
      <div class="row">
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
      <span class="row-name">{SHARD_ROWS[r] ?? ""}</span>
      <div class="row">
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
  /* Three columns, as the client sets its trees side by side. */
  .runes {
    display: grid;
    grid-template-columns: minmax(0, 1.12fr) minmax(0, 1.12fr) minmax(0, 0.9fr);
    gap: var(--space-4);
    align-items: start;
  }
  .tree {
    display: grid;
    gap: 2px;
  }
  .bar {
    display: flex;
    flex-wrap: nowrap;
    gap: var(--space-1) var(--space-2);
    align-items: center;
    margin-bottom: var(--space-1);
  }
  h4 {
    margin: 0;
    font-size: var(--text-md);
    white-space: nowrap;
  }
  .tag {
    color: var(--color-muted);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  /* The other trees, by name: one click changes tree. */
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
  .switch :global(.icon) {
    width: 16px;
    height: 16px;
    font-size: 9px;
  }
  .switch button:hover {
    border-color: var(--color-accent);
    opacity: 1;
  }
  .switch button:focus-visible {
    outline: 2px solid var(--color-accent);
  }
  .row-name {
    margin-top: 6px;
    color: var(--color-muted);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }
  .row {
    display: grid;
    gap: 2px;
  }
  .keystones {
    padding-bottom: var(--space-1);
  }
  .hint {
    margin: 0;
    color: var(--color-muted);
    font-size: var(--text-xs);
  }
  @media (max-width: 900px) {
    .runes {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
