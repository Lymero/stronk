<script lang="ts">
  import type { Choice, GameNames, Imported, Outcome, Page, Plan } from "../../backend/backend.ts";
  import Icon from "../../ui/Icon.svelte";
  import { elo, games, type Icons, icon, name, region, runePage } from "../../ui/labels.ts";
  import OptionList from "./OptionList.svelte";
  import type { Pick, Picks } from "../../state/picks.ts";
  import { allPopular, options as ranked } from "./options.ts";

  let {
    plan,
    names,
    icons,
    picks,
    imported,
    changed,
    onimport,
    onpick,
    onreset,
  }: {
    plan: Plan;
    names: GameNames | null;
    icons: Icons;
    picks: Picks;
    imported: Imported | null;
    /** The picks changed since that import. */
    changed: boolean;
    onimport: () => void;
    onpick: (pick: Pick) => void;
    /** Back to Stronk's choices everywhere. */
    onreset: () => void;
  } = $props();

  const percent = (v: number) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
  const why = (c: Choice<unknown>) =>
    c.label === "clearly_better" ? `Clearly better · ${percent(c.wpa)} win` : c.label === "picked" ? "Your pick" : "Popular";
  /** The evidence behind "Clearly better": the interval and how many games it rests on. */
  const evidence = (c: Choice<unknown>) => {
    if (c.label === "popular") return "The most played option";
    if (c.label === "picked") return "Your pick instead of Stronk's";
    const interval = c.ci ? ` (95% interval ${percent(c.ci[0])} to ${percent(c.ci[1])})` : "";
    return `Win impact ${percent(c.wpa)} against the most played option${interval}, from ${c.games.toLocaleString("en-US")} games`;
  };

  const source = $derived([`Patch ${plan.patch}`, games(plan.games), elo(plan.elo), region(plan.region)].join(" · "));
  const options = $derived(ranked(plan, picks));
  const picked = $derived(picks.runes !== undefined || picks.spells !== undefined || Object.keys(picks.items).length > 0);
  const shownPage = $derived(picks.runes ?? plan.runes?.value);
  /** The item each slot imports: the player's pick, else Stronk's. */
  const slotItem = (slot: number) => picks.items[slot] ?? plan.items.find((i) => i.slot === slot)?.value;
  /** Other slots importing the same item, so a duplicate the player picks is visible. */
  const alsoIn = (slot: number) => (id: number) => {
    const others = plan.items.filter((i) => i.slot !== slot && slotItem(i.slot) === id).map((i) => `item ${i.slot}`);
    return others.length ? `Also in ${others.join(" and ")}` : "";
  };
  const popularOnly = $derived(allPopular(plan));

  const page = (p: Page) => {
    const [primary, secondary] = runePage(names, p);
    return `${primary?.runes[0] ?? ""} · ${primary?.title ?? ""} + ${secondary?.title ?? ""}`;
  };
  const pageDetail = (p: Page) => {
    const [primary, secondary] = runePage(names, p);
    return [...(primary?.runes.slice(1) ?? []), ...(secondary?.runes ?? [])].join(" · ");
  };
  const spells = (pair: [number, number]) => pair.map((id) => name(names, "spells", id)).join(" · ");
  const item = (id: number) => name(names, "items", id);
  const shown = (kind: "rune_styles" | "runes" | "spells" | "items", id: number) => ({
    src: icon(icons, kind, id),
    name: name(names, kind, id),
  });
  /** A page's keystone and secondary tree. */
  const pageIcons = (p: Page) => [
    ...(p.perks[0] !== undefined ? [shown("runes", p.perks[0])] : []),
    shown("rune_styles", p.sub_style),
  ];
  const spellIcons = (pair: [number, number]) => pair.map((id) => shown("spells", id));
  const itemIcons = (id: number) => [shown("items", id)];
  /** The icons of a page summary's lines: each tree's, then each rune's. */
  const lineIcons = (p: Page) => [
    { tree: shown("rune_styles", p.primary_style), runes: p.perks.slice(0, 4).map((id) => shown("runes", id)) },
    { tree: shown("rune_styles", p.sub_style), runes: p.perks.slice(4, 6).map((id) => shown("runes", id)) },
    { tree: null, runes: p.perks.slice(6).map((id) => shown("runes", id)) },
  ];
  const itemSlot = (slot: number) => options.items.find((s) => s.slot === slot);

  const parts = $derived(
    imported
      ? ([
          ["Rune page", imported.runes],
          ["Item set", imported.item_set],
          ["Spells", imported.spells],
        ] as [string, Outcome][])
      : [],
  );
  const done = $derived(parts.filter(([, o]) => o.status === "imported").map(([part]) => part));
  const skipped = $derived(
    parts.flatMap(([part, o]) => (o.status === "skipped" ? [{ part, reason: o.reason }] : [])),
  );
</script>

{#snippet label(c: Choice<unknown>)}
  <span class="label" class:better={c.label === "clearly_better"} class:picked={c.label === "picked"} title={evidence(c)}
    >{why(c)}</span
  >
{/snippet}

<section class="plan" aria-label="Build">
  <header>
    <div>
      <h2>Recommended build</h2>
      <p class="meta">{source}</p>
    </div>
    <div class="actions">
      {#if picked}<button type="button" class="quiet" onclick={onreset}>Use Stronk's picks</button>{/if}
      <button type="button" class="primary" onclick={onimport}>Import</button>
    </div>
  </header>

  <p class="note">
    {#if popularOnly}
      No option beats the most played one clearly yet, so Stronk imports the most played build. The
      alternatives below show what else is played and how far the numbers go.
    {:else}
      Stronk imports the most played options, except where another one is clearly better.
    {/if}
    Click any option to import it instead.
  </p>

  {#if imported}
    {#each skipped as s (s.part)}
      <p class="skipped" role="alert">{s.part} not imported: {s.reason}</p>
    {/each}
    <p class="result" class:stale={changed} role="status">
      {done.length ? `Imported: ${done.join(", ")}.` : "Nothing imported."}
      {#if imported.item_set_backup}<span title={imported.item_set_backup}>Your item sets were backed up first.</span>{/if}
      {#if changed}<strong>Your picks changed since: import again to use them.</strong>{/if}
    </p>
  {/if}

  <div class="cards">
    {#if plan.runes}
      <article class="card wide">
        <header>
          <h3>Runes</h3>
          {@render label(picks.runes ? { value: null, label: "picked" } : plan.runes)}
        </header>
        <div class="page">
          {#each runePage(names, shownPage ?? plan.runes.value) as line, n (line.title)}
            {@const lineIcon = lineIcons(shownPage ?? plan.runes.value)[n]}
            <div class="tree-line">
              <span class="icons" aria-hidden="true">
                {#if lineIcon?.tree}<Icon src={lineIcon.tree.src} name={lineIcon.tree.name} />{/if}
                {#each lineIcon?.runes ?? [] as r, k (k)}<Icon src={r.src} name={r.name} size={k === 0 && n === 0 ? "md" : "sm"} />{/each}
              </span>
              <p><span class="tree">{line.title}</span> {line.runes.join(" · ")}</p>
            </div>
          {/each}
        </div>
        {#if options.runes.rows.length}
          <h4>Pages played</h4>
          <OptionList
            slot={options.runes}
            label={page}
            detail={pageDetail}
            icons={pageIcons}
            onpick={(p) => onpick({ runes: p })}
          />
        {/if}
      </article>
    {/if}

    {#if plan.spells}
      <article class="card">
        <header>
          <h3>Spells</h3>
          {@render label(picks.spells ? { value: null, label: "picked" } : plan.spells)}
        </header>
        {#if options.spells.rows.length}
          <OptionList
            slot={options.spells}
            label={spells}
            icons={spellIcons}
            onpick={(pair) => onpick({ spells: pair })}
          />
        {:else}
          <p class="value">
            {#each spellIcons(plan.spells.value) as i, n (n)}<Icon src={i.src} name={i.name} />{/each}
            {spells(plan.spells.value)}
          </p>
        {/if}
      </article>
    {/if}

    {#each plan.items as choice (choice.slot)}
        {@const alts = itemSlot(choice.slot)}
        <article class="card">
          <header>
            <h3>Item {choice.slot}</h3>
            {@render label(picks.items[choice.slot] !== undefined ? { value: null, label: "picked" } : choice)}
          </header>
          {#if alts?.rows.length}
            <OptionList
              slot={alts}
              label={item}
              detail={alsoIn(choice.slot)}
              icons={itemIcons}
              onpick={(id) => onpick({ slot: choice.slot, item: id })}
            />
          {:else}
            <p class="value"><Icon src={icon(icons, "items", choice.value)} name={item(choice.value)} /> {item(choice.value)}</p>
          {/if}
        </article>
      {/each}
  </div>
</section>

<style>
  .plan {
    display: grid;
    gap: var(--space-4);
  }
  .plan > header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }
  h2 {
    margin: 0;
    font-size: var(--text-lg);
  }
  h3,
  h4 {
    margin: 0;
    font-size: var(--text-md);
  }
  h4 {
    color: var(--color-muted);
    font-size: var(--text-sm);
    font-weight: 600;
  }
  .card h4 + :global(.options) {
    margin-top: var(--space-1);
  }
  .meta {
    margin: var(--space-1) 0 0;
    color: var(--color-muted);
  }
  .note {
    margin: 0;
    color: var(--color-muted);
    font-size: var(--text-sm);
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: var(--space-3);
  }
  .card {
    display: grid;
    align-content: start;
    gap: var(--space-2);
    padding: var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
  }
  .card > header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    padding: 0 var(--space-1);
  }
  .card.wide {
    grid-column: 1 / -1;
  }
  .page {
    display: grid;
    gap: var(--space-2);
    padding: 0 var(--space-1);
  }
  .tree-line {
    display: flex;
    gap: var(--space-3);
    align-items: center;
  }
  .icons {
    display: flex;
    flex: 0 0 auto;
    gap: var(--space-1);
    align-items: center;
    min-width: calc(var(--icon-md) * 2 + var(--icon-sm) * 3 + var(--space-1) * 4);
  }
  .page p,
  .value {
    margin: 0;
  }
  .value {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    padding: 0 var(--space-1);
  }
  .tree {
    color: var(--color-muted);
  }
  .result {
    margin: 0;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius);
    background: var(--color-positive-bg);
  }
  .skipped {
    margin: 0;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius);
    background: var(--color-warning-bg);
    color: var(--color-warning);
  }
  .label {
    padding: 0 var(--space-2);
    border-radius: var(--radius);
    background: var(--color-bg);
    color: var(--color-muted);
    font-size: var(--text-sm);
    white-space: nowrap;
  }
  .label.better {
    background: var(--color-positive-bg);
    color: var(--color-positive);
  }
  .label.picked {
    background: var(--color-accent-bg);
    color: var(--color-accent);
  }
  .result.stale {
    background: var(--color-warning-bg);
  }
  .result strong {
    display: block;
    color: var(--color-warning);
  }
  .actions {
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }
  .quiet {
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    cursor: pointer;
  }
  .primary {
    padding: var(--space-2) var(--space-6);
    border: 1px solid var(--color-accent);
    border-radius: var(--radius);
    background: var(--color-accent);
    color: var(--color-surface);
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }
</style>
