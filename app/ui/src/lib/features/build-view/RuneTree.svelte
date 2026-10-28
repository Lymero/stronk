<script lang="ts">
  // The rune page as the client lays it out (ADR-058): the primary tree's keystones and rows, the
  // secondary tree's rows, and the stat shards, every rune with its number under it. The page's
  // choices are lit, the rest dimmed; a keystone with a published page can be clicked to pick
  // that page. Numbers come from `build.plan`: keystones from the pages, rows from `rune_rows`.
  import type { GameNames, Page, Row } from "../../backend/backend.ts";
  import Icon from "../../ui/Icon.svelte";
  import { type Icons, icon, name } from "../../ui/labels.ts";
  import { explain, figure, percent, type RuneRowSlot, verdict } from "./options.ts";

  let {
    page,
    keystones,
    rows,
    names,
    icons,
    onpick,
  }: {
    /** The page the import writes. */
    page: Page;
    /** Each keystone's published page and its numbers. */
    keystones: { page: Page; row: Row<Page> }[];
    /** The page's rune rows with their numbers (`runeRows`). */
    rows: RuneRowSlot[];
    names: GameNames;
    icons: Icons;
    onpick: (page: Page) => void;
  } = $props();

  const primary = $derived(names.rune_trees[String(page.primary_style)] ?? []);
  const secondary = $derived((names.rune_trees[String(page.sub_style)] ?? []).slice(1));
  const chosen = $derived(new Set(page.perks.slice(0, 6)));
  const shardsChosen = $derived(page.perks.slice(6));

  /** A row's numbers by rune: primary rows by row number, shard rows by row number. */
  const stats = $derived.by(() => {
    const found = new Map<string, Row<number[]>>();
    for (const r of rows) for (const x of r.slot.rows) if (x.value.length === 1) found.set(`${r.kind}-${r.row}-${x.value[0]}`, x);
    return found;
  });
  const pair = $derived(rows.find((r) => r.kind === "secondary"));
  const pairChosen = $derived(pair?.slot.rows.find((x) => x.selected));
  const keystoneOf = (id: number) => keystones.find((k) => k.page.perks[0] === id);

  const runeName = (id: number) => name(names, "runes", id);
  /** Under a rune: its number, "few" with too few games, nothing when nobody took it. */
  const under = (row: Row<unknown> | undefined) => {
    if (!row) return { text: "", spread: "", tone: "" };
    if (row.wpa === null) return { text: "few", spread: "", tone: "few" };
    const clear = verdict(row);
    const spread = row.ci ? `± ${(Math.abs(row.ci[1] - row.ci[0]) * 50).toFixed(1)}` : "";
    return { text: `${clear ? (clear.tone === "positive" ? "▲ " : "▼ ") : ""}${percent(row.wpa)}`, spread, tone: clear?.tone ?? "" };
  };
  const title = (id: number, row: Row<unknown> | undefined) =>
    `${runeName(id)}: ${row ? `${Math.round(row.share * 100)}% of games (${row.played}). ${explain(row)}` : "not played in these games"}`;
</script>

{#snippet cell(id: number, row: Row<unknown> | undefined, on: boolean, size: "sm" | "md", pick?: () => void, bare = false)}
  {@const n = under(row)}
  {#if pick}
    <button
      type="button"
      class="cell"
      class:on
      aria-pressed={on}
      aria-label={`${runeName(id)} ${n.text} ${n.spread}`.trim()}
      title={title(id, row)}
      onclick={pick}
    >
      <Icon src={icon(icons, "runes", id)} name={runeName(id)} {size} round />
      <span class="num {n.tone}">{n.text}</span>
      <span class="spread">{n.spread}</span>
    </button>
  {:else}
    <span
      class="cell"
      class:on
      class:bare
      role="img"
      aria-label={`${runeName(id)} ${n.text} ${n.spread}`.trim()}
      aria-current={on ? "true" : undefined}
      title={title(id, row)}
    >
      <Icon src={icon(icons, "runes", id)} name={runeName(id)} {size} round />
      {#if !bare}
        <span class="num {n.tone}">{n.text}</span>
        <span class="spread">{n.spread}</span>
      {/if}
    </span>
  {/if}
{/snippet}

<div class="trees" aria-label="Rune page">
  <section class="tree" aria-label={name(names, "rune_styles", page.primary_style)}>
    <h5>
      <Icon src={icon(icons, "rune_styles", page.primary_style)} name={name(names, "rune_styles", page.primary_style)} size="sm" round />
      {name(names, "rune_styles", page.primary_style)}
    </h5>
    {#each primary as runes, r (r)}
      <div class="row" class:keystones={r === 0}>
        {#each runes as id (id)}
          {#if r === 0}
            {@const k = keystoneOf(id)}
            {@render cell(id, k?.row, chosen.has(id), "md", k ? () => onpick(k.page) : undefined)}
          {:else}
            {@render cell(id, stats.get(`primary-${r}-${id}`), chosen.has(id), "md")}
          {/if}
        {/each}
      </div>
    {/each}
  </section>

  <div class="side">
    <section class="tree" aria-label={name(names, "rune_styles", page.sub_style)}>
      <h5>
        <Icon src={icon(icons, "rune_styles", page.sub_style)} name={name(names, "rune_styles", page.sub_style)} size="sm" round />
        {name(names, "rune_styles", page.sub_style)}
      </h5>
      {#each secondary as runes, r (r)}
        <div class="row">
          {#each runes as id (id)}{@render cell(id, undefined, chosen.has(id), "md", undefined, true)}{/each}
        </div>
      {/each}
      {#if pairChosen}
        <p class="pair" title={explain(pairChosen)}>
          The two together: <strong class={verdict(pairChosen)?.tone ?? ""}>{figure(pairChosen) ?? "few games"}</strong>
        </p>
      {/if}
    </section>

    <section class="tree shards" aria-label="Shards">
      {#each names.shard_rows as runes, r (r)}
        <div class="row">
          {#each runes as id (id)}{@render cell(id, stats.get(`shard-${r + 1}-${id}`), shardsChosen[r] === id, "sm")}{/each}
        </div>
      {/each}
    </section>
  </div>
</div>

<style>
  .trees {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-4);
    padding: var(--space-3);
    border-radius: var(--radius);
    background: var(--color-bg);
  }
  .side {
    display: grid;
    align-content: start;
    gap: var(--space-4);
  }
  .tree {
    display: grid;
    align-content: start;
    gap: var(--space-2);
    justify-items: center;
  }
  h5 {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    margin: 0 0 var(--space-1);
    font-size: var(--text-sm);
  }
  .row {
    display: flex;
    gap: var(--space-1);
    align-items: start;
    justify-content: center;
  }
  .keystones {
    padding-bottom: var(--space-2);
    border-bottom: 1px solid var(--color-border);
  }
  /* Every cell the same height, number or not, so rows line up. */
  .cell {
    display: grid;
    grid-template-rows: auto 16px 13px;
    align-content: start;
    justify-items: center;
    width: 60px;
    padding: var(--space-1) 0;
    border: 1px solid transparent;
    border-radius: var(--radius);
    background: none;
    color: inherit;
    font: inherit;
  }
  /* Secondary runes: numbers are for the pair, so no space under each. */
  .cell.bare {
    grid-template-rows: auto;
  }
  .cell :global(.icon) {
    filter: grayscale(1);
    opacity: 0.45;
  }
  .cell.on :global(.icon) {
    filter: none;
    opacity: 1;
    box-shadow: 0 0 0 2px var(--color-accent);
  }
  button.cell {
    cursor: pointer;
  }
  button.cell:hover {
    border-color: var(--color-border);
  }
  button.cell:hover :global(.icon) {
    opacity: 0.8;
  }
  button.cell:focus-visible {
    outline: 2px solid var(--color-accent);
  }
  .num {
    margin-top: 2px;
    color: var(--color-muted);
    font-size: var(--text-xs);
    font-variant-numeric: tabular-nums;
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
    font-style: italic;
  }
  .spread {
    color: var(--color-muted);
    font-size: 10px;
    font-variant-numeric: tabular-nums;
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
  .shards {
    padding-top: var(--space-3);
    border-top: 1px solid var(--color-border);
  }
  .shards .cell {
    width: 52px;
  }
  @media (max-width: 480px) {
    .trees {
      grid-template-columns: 1fr;
    }
  }
</style>
