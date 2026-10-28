<script lang="ts">
  // The build Stronk would import as a board of panels (ADR-059): the rune page built by clicking
  // runes, the spells and each item slot as rows of options, every option with its numbers and
  // the lit ones what the import writes. Nothing to open or scroll through.
  import type { GameNames, Imported, Outcome, Page, Plan } from "../../backend/backend.ts";
  import Facts from "../../ui/Facts.svelte";
  import Icon from "../../ui/Icon.svelte";
  import { elo, games, type Icons, icon, name, region, runePage } from "../../ui/labels.ts";
  import ChoicePanel from "./ChoicePanel.svelte";
  import RunesPanel from "./RunesPanel.svelte";
  import type { Pick, Picks } from "../../state/picks.ts";
  import {
    allPopular,
    explain,
    figure,
    mostPlayed,
    options as ranked,
    selected,
    type Slot,
    verdict,
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

  /** What a closed slot says after its value: a clear result against the most played option,
   * else the option's number with its uncertainty; "Your pick" first when it isn't Stronk's. */
  function note<T>(
    slot: Slot<T>,
    label: (value: T) => string,
  ): { text: string; tone: string; title: string } | null {
    const row = selected(slot);
    if (!row) return null;
    const clear = verdict(row);
    const base = mostPlayed(slot);
    const number =
      clear && base && base !== row ? `${clear.text} vs ${label(base.value)}` : (figure(row) ?? "");
    const tone = clear && base !== row ? clear.tone : "muted";
    const text = row.chosen ? number : number ? `Your pick: ${number}` : "Your pick";
    if (!text) return null;
    return { text, tone: row.chosen ? tone : "picked", title: explain(row) };
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
