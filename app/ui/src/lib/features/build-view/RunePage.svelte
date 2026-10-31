<script lang="ts">
  // The rune page (ADR-064): the client's tree on the left, icons only, the picks lit and ringed
  // in amber (Stronk's pick marked by a dot when the player took another), the shards in their
  // three rows; the row in focus beside it as a list read like the item lists: each rune's name,
  // its number against the row's most played rune, its share and its games. Clicking a rune in
  // the tree picks it and brings its row into focus; picking from the list does the same. The
  // secondary runes are measured as a pair: clicking one brings the whole secondary tree into
  // focus, its pairs listed with both runes, and picking a pair sets both.
  import type { GameNames, Page, Plan } from "../../backend/backend.ts";
  import Icon from "../../ui/Icon.svelte";
  import { type Icons, icon, name } from "../../ui/labels.ts";
  import OptionTable from "./OptionTable.svelte";
  import { type RuneRow, runePairs, runeRows } from "./runeRows.ts";
  import { withPrimaryTree, withSecondaryTree } from "./runes.ts";

  let {
    plan,
    page,
    stronk,
    names,
    icons,
    onpage,
  }: {
    plan: Plan;
    page: Page;
    stronk: Page | null;
    names: GameNames;
    icons: Icons;
    onpage: (page: Page) => void;
  } = $props();

  let last = $state<number | null>(null);
  let focus = $state("primary-0");
  const rows = $derived(runeRows(plan, names, page, stronk, last));
  const pairs = $derived(runePairs(plan, names, page, stronk));
  /** The row in focus; the secondary tree is one focus, as its runes are one pair. */
  const focused = $derived(focus === "secondary" ? null : (rows.find((r) => r.key === focus) ?? rows[0]));
  const trees = $derived(names.rune_trees);
  const styles = $derived(Object.keys(trees).map(Number));
  const rune = (id: number) => name(names, "runes", id);
  const tree = (id: number) => name(names, "rune_styles", id);

  function pick(row: RuneRow, id: number): void {
    // A rune already on the page only brings its row into focus: the page stays as it is.
    if (row.picked !== id) {
      onpage(row.next(id));
      if (row.group === "secondary") last = id;
    }
    focus = row.group === "secondary" ? "secondary" : row.key;
  }
  function pickPair(pair: number[]): void {
    if (!pairs.slot.rows.some((r) => r.selected && r.value.join() === pair.join())) {
      onpage(pairs.next(pair));
      last = null;
    }
  }
  const both = (pair: number[]) => pair.map(rune).join(" + ");
  /** What the list is headed by: the tree, or the shard row. Players know which row it is; screen
   * readers get it from `title`. */
  const heading = (row: RuneRow) =>
    row.group === "primary"
      ? row.key === "primary-0"
        ? `${tree(page.primary_style)} keystones`
        : tree(page.primary_style)
      : `${row.label} shard`;
  const title = (row: RuneRow) =>
    row.group === "primary"
      ? `${tree(page.primary_style)}, ${row.label.toLowerCase()}`
      : `${row.label} shard`;
</script>

{#snippet head(current: number, others: number[], choose: (style: number) => void, tag: string)}
  <header class="head">
    <Icon src={icon(icons, "rune_styles", current)} name={tree(current)} size="sm" round />
    <div class="name"><h4>{tree(current)}</h4><span class="tag">{tag}</span></div>
    <span class="switch" role="group" aria-label={`${tag} tree`}>
      {#each others as style (style)}
        <button type="button" aria-label={tree(style)} title={tree(style)} onclick={() => choose(style)}>
          <Icon src={icon(icons, "rune_styles", style)} name={tree(style)} size="sm" round />
        </button>
      {/each}
    </span>
  </header>
{/snippet}

{#snippet line(row: RuneRow, size: string)}
  <div class="line" class:focus={focus === row.key}>
    {#each row.ids as id (id)}
      <button
        type="button"
        class="rune {size}"
        class:on={row.picked === id}
        class:stronk={row.picked !== id && row.stronk(id)}
        aria-pressed={row.picked === id}
        aria-label={rune(id)}
        title={rune(id)}
        onclick={() => pick(row, id)}
      >
        <Icon src={icon(icons, "runes", id)} name={rune(id)} size="md" round />
      </button>
    {/each}
  </div>
{/snippet}

<div class="runes" aria-label="Rune page">
  <div class="trees">
    <section class="tree" aria-label={`${tree(page.primary_style)}, primary`}>
      {@render head(page.primary_style, styles.filter((s) => s !== page.primary_style), (s) => onpage(withPrimaryTree(plan, trees, page, s)), "Primary")}
      {#each rows.filter((r) => r.group === "primary") as row (row.key)}{@render line(row, row.key === "primary-0" ? "lg" : "md")}{/each}
    </section>
    <section class="tree" class:focus={focus === "secondary"} aria-label={`${tree(page.sub_style)}, secondary`}>
      {@render head(page.sub_style, styles.filter((s) => s !== page.sub_style && s !== page.primary_style), (s) => onpage(withSecondaryTree(plan, trees, page, s)), "Secondary")}
      {#each rows.filter((r) => r.group === "secondary") as row (row.key)}{@render line(row, "md")}{/each}
    </section>
    <section class="tree shards" aria-label="Shards">
      <header class="head"><div class="name"><h4>Shards</h4></div></header>
      <div class="shard-rows">
        {#each rows.filter((r) => r.group === "shards") as row (row.key)}
          <div class="shard-row">
            <span class="shard-name">{row.label}</span>
            {@render line(row, "sm")}
          </div>
        {/each}
      </div>
    </section>
    <p class="hint how">Click a rune to pick it and see its row beside the tree.</p>
  </div>

  {#if focused?.slot}
    <section class="detail" aria-label={title(focused)}>
      <h4 class="title">{heading(focused)}</h4>
      <OptionTable
        slot={focused.slot}
        label={rune}
        icons={(id) => [{ src: icon(icons, "runes", id), name: rune(id) }]}
        onpick={(id) => pick(focused, id)}
      />
    </section>
  {:else}
    <section class="detail" aria-label={`${tree(page.sub_style)}, pairs`}>
      <h4 class="title">{tree(page.sub_style)} pairs</h4>
      <OptionTable
        slot={pairs.slot}
        label={both}
        icons={(pair) => pair.map((id) => ({ src: icon(icons, "runes", id), name: rune(id) }))}
        onpick={pickPair}
      />
    </section>
  {/if}
</div>

<style>
  .runes {
    display: grid;
    grid-template-columns: 404px minmax(0, 1fr);
    gap: var(--space-4);
    align-items: start;
  }
  .trees {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3) var(--space-2);
  }
  .tree {
    display: grid;
    gap: 4px;
    align-content: start;
    padding: var(--space-2);
    border-radius: var(--radius-lg);
    background: var(--color-raised);
  }
  .shards {
    grid-column: 1 / -1;
  }
  .shard-rows {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-2);
  }
  .shard-row {
    display: grid;
    justify-items: center;
  }
  .shard-name {
    color: var(--color-muted);
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .head {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    align-items: center;
    margin-bottom: var(--space-1);
  }
  .name {
    display: grid;
    font-size: var(--text-sm);
    line-height: 1.15;
  }
  .tag {
    color: var(--color-muted);
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .switch {
    display: flex;
    flex-basis: 100%;
    gap: 2px;
  }
  .switch button {
    display: grid;
    padding: 1px;
    border: 1px solid transparent;
    border-radius: 50%;
    background: none;
    cursor: pointer;
    opacity: 0.55;
  }
  .switch button:hover {
    border-color: var(--color-accent);
    opacity: 1;
  }
  .switch :global(.icon) {
    width: 16px;
    height: 16px;
    font-size: 9px;
  }
  /* Room around the icons, so a picked rune's ring stays inside the focused row's band. */
  .line {
    display: flex;
    gap: 8px;
    justify-content: center;
    padding: 5px 8px;
    border-radius: 999px;
  }
  .line.focus,
  .tree.focus {
    background: var(--color-accent-bg);
    box-shadow: inset 0 0 0 1px var(--color-accent);
  }
  .rune {
    position: relative;
    display: grid;
    padding: 0;
    border: none;
    border-radius: 50%;
    background: none;
    cursor: pointer;
  }
  .rune :global(.icon) {
    width: var(--size);
    height: var(--size);
    border-radius: 50%;
    filter: grayscale(1);
    opacity: 0.45;
  }
  .rune:hover :global(.icon) {
    filter: none;
    opacity: 0.85;
  }
  .rune.on :global(.icon) {
    filter: none;
    opacity: 1;
    box-shadow:
      0 0 0 2px var(--color-accent),
      0 0 6px var(--color-accent);
  }
  /* Stronk's pick when the player took another: a small amber dot. */
  .rune.stronk::after {
    position: absolute;
    top: -2px;
    right: -2px;
    width: 7px;
    height: 7px;
    border: 2px solid var(--color-raised);
    border-radius: 50%;
    background: var(--color-accent);
    content: "";
  }
  .rune:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
  }
  /* The item icons' size; keystones a little larger, as in the client. */
  .lg {
    --size: 36px;
  }
  .md {
    --size: var(--icon-md);
  }
  .sm {
    --size: 28px;
  }
  .detail {
    display: grid;
    gap: var(--space-2);
  }
  .name h4 {
    margin: 0;
    font-size: var(--text-sm);
  }
  .detail h4 {
    margin: 0;
    font-size: var(--text-md);
  }
  .detail h4::first-letter {
    text-transform: uppercase;
  }
  .how {
    grid-column: 1 / -1;
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
