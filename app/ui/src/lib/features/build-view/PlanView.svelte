<script lang="ts">
  // The build Stronk would import as a board of panels (ADR-059): the rune page built by clicking
  // runes, the spells and each item slot as rows of options, every option with its numbers and
  // the lit ones what the import writes. Nothing to open or scroll through. It opens with what
  // Stronk changes from the most played build (ADR-060).
  import type { GameNames, Imported, Outcome, Page, Plan } from "../../backend/backend.ts";
  import Facts from "../../ui/Facts.svelte";
  import Icon from "../../ui/Icon.svelte";
  import { elo, games, type Icons, icon, name, region, runePage } from "../../ui/labels.ts";
  import ChoicePanel from "./ChoicePanel.svelte";
  import RunesPanel from "./RunesPanel.svelte";
  import type { Pick, Picks } from "../../state/picks.ts";
  import {
    allPopular,
    changes,
    compared,
    explain,
    figure,
    mostPlayed,
    options as ranked,
    selected,
    type Slot,
    verdict,
    wins,
  } from "./options.ts";

  let {
    plan,
    names,
    icons,
    picks,
    imported,
    changed,
    onpick,
  }: {
    plan: Plan;
    names: GameNames | null;
    icons: Icons;
    picks: Picks;
    imported: Imported | null;
    /** The picks changed since that import. */
    changed: boolean;
    onpick: (pick: Pick) => void;
  } = $props();

  const source = $derived([`Patch ${plan.patch}`, games(plan.games), elo(plan.elo), region(plan.region)]);
  const how = $derived(
    (allPopular(plan)
      ? "No option beats the most played one clearly yet, so Stronk imports the most played build."
      : "Stronk imports the most played options, except where another one is clearly better.") +
      " Open a slot and click any option to import it instead.",
  );
  const options = $derived(ranked(plan, picks));
  const stronkChanges = $derived(changes(options));
  /** A change's part, option and the option it beats, in words. */
  const what = (part: "runes" | "spells" | number) =>
    part === "runes" ? "Runes" : part === "spells" ? "Summoner spells" : `Item ${part}`;
  const valueOf = (part: "runes" | "spells" | number, value: unknown) =>
    part === "runes" ? page(value as Page) : part === "spells" ? spells(value as [number, number]) : item(value as number);
  /** The page the import writes: the player's, else Stronk's. */
  const shownPage = $derived(picks.runes ?? plan.runes?.value ?? null);
  /** The client's layout of that page's trees, without which pages are picked whole. */
  const laidOut = $derived(!!names && !!shownPage && !!names.rune_trees[String(shownPage.primary_style)]);

  const page = (p: Page) => {
    const [primary, secondary] = runePage(names, p);
    return `${primary?.runes[0] ?? ""} (${primary?.title ?? ""} + ${secondary?.title ?? ""})`;
  };
  const spells = (pair: [number, number]) => pair.map((id) => name(names, "spells", id)).join(" + ");
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

  /** The item each slot imports: the player's pick, else Stronk's. */
  const slotItem = (slot: number) => picks.items[slot] ?? plan.items.find((i) => i.slot === slot)?.value;
  /** Other slots importing the same item, so a duplicate the player picks is visible. */
  const alsoIn = (slot: number) => (id: number) => {
    const others = plan.items.filter((i) => i.slot !== slot && slotItem(i.slot) === id).map((i) => `item ${i.slot}`);
    return others.length ? `Also in ${others.join(" and ")}` : "";
  };

  /** What a slot's header says: what its numbers are compared with, a clear result against it,
   * and "Your pick" when the import writes the player's choice (ADR-060). */
  function note<T>(
    slot: Slot<T>,
    label: (value: T) => string,
  ): { text: string; tone: string; title: string } | null {
    const row = selected(slot);
    if (!row) return null;
    const clear = verdict(row);
    const base = mostPlayed(slot);
    const against = base && compared(slot) ? label(base.value) : null;
    if (row.chosen && clear && base !== row && against)
      return { text: `${clear.text} vs ${against}`, tone: clear.tone, title: explain(row) };
    if (row.chosen)
      return against ? { text: `Compared with ${against}`, tone: "muted", title: explain(row) } : null;
    const number = figure(row);
    const text = number && against ? `Your pick: ${number} vs ${against}` : "Your pick";
    return { text, tone: "picked", title: explain(row) };
  }

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

<section class="plan" aria-label="Build">
  <p class="meta">
    <Facts facts={source} />
    <span class="how" title={how} aria-label={how}>How Stronk picks</span>
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

  <div class="take" aria-label="What Stronk changes">
    {#if stronkChanges.length === 0}
      <p class="headline">The most played build. No option is clearly better yet.</p>
    {:else}
      <p class="headline">
        Stronk changes {stronkChanges.length === 1 ? "1 thing" : `${stronkChanges.length} things`} from the most played build
      </p>
      <ul>
        {#each stronkChanges as c (c.part)}
          <li title={explain(c.row)}>
            <span class="part">{what(c.part)}</span>
            <strong>{valueOf(c.part, c.row.value)}</strong>
            {#if c.base && c.base !== c.row}<span class="base">over {valueOf(c.part, c.base.value)}</span>{/if}
            <span class="gain">
              {wins(c.row.wpa ?? 0)} wins per 100 games
            </span>
          </li>
        {/each}
      </ul>
    {/if}
    <p class="legend">
      <svg class="key ring" viewBox="0 0 12 12" aria-hidden="true"><circle cx="6" cy="6" r="4.5" class="track" /><circle cx="6" cy="6" r="4.5" class="arc" pathLength="100" stroke-dasharray="35 100" /></svg>ring: share of games
      <span class="key num" aria-hidden="true">+2.1</span>wins per 100 games compared with the most played option of its row, which reads 0
      <span class="key clear" aria-hidden="true">▲</span>colour only when clearly better or worse
    </p>
  </div>

  <div class="board">
    <div class="column">
      {#if shownPage && laidOut && names}
        <section aria-label="Runes">
          <h3>Runes</h3>
          <RunesPanel
            {plan}
            page={shownPage}
            stronk={plan.runes?.value ?? null}
            {names}
            {icons}
            onpage={(p) => onpick({ runes: p })}
          />
        </section>
      {:else if plan.runes}
        <ChoicePanel
          title="Runes"
          note={note(options.runes, page)}
          slot={options.runes}
          label={page}
          icons={pageIcons}
          onpick={(p) => onpick({ runes: p })}
        />
      {/if}
      {#if plan.spells}
        <ChoicePanel
          title="Summoner spells"
          note={note(options.spells, spells)}
          slot={options.spells}
          label={spells}
          icons={spellIcons}
          onpick={(pair) => onpick({ spells: pair })}
        />
      {/if}
    </div>

    <section class="column" aria-label="Items">
      <h3>Items</h3>
      {#each plan.items as choice (choice.slot)}
        {@const alts = options.items.find((s) => s.slot === choice.slot) ?? { rows: [], more: 0 }}
        {@const also = alsoIn(choice.slot)(slotItem(choice.slot) ?? choice.value)}
        <ChoicePanel
          title={`Item ${choice.slot}${also ? `, ${also.toLowerCase()}` : ""}`}
          note={note(alts, item)}
          slot={alts}
          label={item}
          icons={itemIcons}
          onpick={(id) => onpick({ slot: choice.slot, item: id })}
        />
      {/each}
    </section>
  </div>
</section>

<style>
  .plan {
    display: grid;
    gap: var(--space-3);
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-3);
    align-items: baseline;
    margin: 0;
    color: var(--color-muted);
    font-size: var(--text-sm);
  }
  .how {
    border-bottom: 1px dotted var(--color-muted);
    cursor: help;
  }
  .take {
    display: grid;
    gap: var(--space-1);
    padding: var(--space-3) var(--space-4);
    border-left: 3px solid var(--color-accent);
    border-radius: var(--radius);
    background: var(--color-surface);
  }
  .take p,
  .take ul {
    margin: 0;
  }
  .headline {
    font-weight: 600;
  }
  .take ul {
    display: grid;
    gap: 2px;
    padding: 0;
    list-style: none;
  }
  .take li {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-2);
    align-items: baseline;
  }
  .part,
  .base {
    color: var(--color-muted);
    font-size: var(--text-sm);
  }
  .gain {
    color: var(--color-positive);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-2);
    align-items: center;
    margin-top: var(--space-1) !important;
    color: var(--color-muted);
    font-size: var(--text-xs);
  }
  .key {
    display: inline-block;
    margin-left: var(--space-2);
  }
  .key:first-child {
    margin-left: 0;
  }
  .key.ring {
    width: 12px;
    height: 12px;
    transform: rotate(-90deg);
  }
  .key.ring circle {
    fill: none;
    stroke-width: 2;
  }
  .key.ring .track {
    stroke: var(--color-track);
  }
  .key.ring .arc {
    stroke: var(--color-muted);
  }
  .key.num {
    color: var(--color-text);
    font-weight: 600;
  }
  .key.clear {
    color: var(--color-positive);
  }
  .board {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: var(--space-4);
    align-items: start;
  }
  .column {
    display: grid;
    gap: var(--space-3);
    min-width: 0;
  }
  .column > section {
    display: grid;
    gap: var(--space-2);
  }
  h3 {
    margin: 0;
    font-size: var(--text-lg);
  }
  .result {
    margin: 0;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius);
    background: var(--color-positive-bg);
  }
  .result.stale {
    background: var(--color-warning-bg);
  }
  .result strong {
    display: block;
    color: var(--color-warning);
  }
  .skipped {
    margin: 0;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius);
    background: var(--color-warning-bg);
    color: var(--color-warning);
  }
  @media (max-width: 900px) {
    .board {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
