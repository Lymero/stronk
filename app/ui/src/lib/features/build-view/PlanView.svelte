<script lang="ts">
  // The build Stronk would import, one line per slot (ADR-056): the option the import writes,
  // a verdict only when it clearly beats the most played one or is the player's own pick, and
  // the slot's options behind a click.
  import type { GameNames, Imported, Outcome, Page, Plan } from "../../backend/backend.ts";
  import Facts from "../../ui/Facts.svelte";
  import Icon from "../../ui/Icon.svelte";
  import { elo, games, type Icons, icon, name, region, runePage } from "../../ui/labels.ts";
  import OptionList from "./OptionList.svelte";
  import type { Pick, Picks } from "../../state/picks.ts";
  import {
    allPopular,
    explain,
    figure,
    mostPlayed,
    options as ranked,
    runeRows,
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

  /** Slots opened by the player to see their options; all closed at first. */
  let open = $state<Record<string, boolean>>({});
  const toggle = (key: string) => (open = { ...open, [key]: !open[key] });

  const source = $derived([`Patch ${plan.patch}`, games(plan.games), elo(plan.elo), region(plan.region)]);
  const how = $derived(
    (allPopular(plan)
      ? "No option beats the most played one clearly yet, so Stronk imports the most played build."
      : "Stronk imports the most played options, except where another one is clearly better.") +
      " Open a slot and click any option to import it instead.",
  );
  const options = $derived(ranked(plan, picks));
  /** The rune rows of the page the import writes. */
  const byRune = $derived(plan.runes ? runeRows(plan, picks.runes ?? plan.runes.value) : []);

  const page = (p: Page) => {
    const [primary, secondary] = runePage(names, p);
    return `${primary?.runes[0] ?? ""} (${primary?.title ?? ""} + ${secondary?.title ?? ""})`;
  };
  const pageDetail = (p: Page) => {
    const [primary, secondary] = runePage(names, p);
    return [...(primary?.runes.slice(1) ?? []), ...(secondary?.runes ?? [])].join(", ");
  };
  const spells = (pair: [number, number]) => pair.map((id) => name(names, "spells", id)).join(" + ");
  const runes = (ids: number[]) => ids.map((id) => name(names, "runes", id)).join(" + ");
  const runeIcons = (ids: number[]) => ids.map((id) => shown("runes", id));
  const SHARD_ROWS = ["Offense shard", "Flex shard", "Defense shard"];
  /** A rune row's name: "Precision row 1", "Inspiration, secondary", "Flex shard". */
  const rowTitle = (r: { kind: string; style: number | null; row: number | null }) =>
    r.kind === "shard"
      ? (SHARD_ROWS[(r.row ?? 1) - 1] ?? "Shard")
      : `${name(names, "rune_styles", r.style ?? 0)} ${r.kind === "secondary" ? "secondary" : `row ${r.row ?? ""}`}`;
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

{#snippet summary(
  key: string,
  title: string,
  value: { icons: { src: string | null; name: string }[]; name: string; detail: string },
  said: { text: string; tone: string; title: string } | null,
  count: number,
)}
  <button
    type="button"
    class="summary"
    aria-expanded={count > 1 ? !!open[key] : undefined}
    aria-controls="slot-{key}"
    disabled={count < 2}
    onclick={() => toggle(key)}
  >
    <span class="slot-name" aria-hidden="true">{title}</span>
    <span class="icons" aria-hidden="true">
      {#each value.icons as i, n (n)}<Icon src={i.src} name={i.name} />{/each}
    </span>
    <span class="value">
      <span class="caption">{title}</span>
      <span class="name">{value.name}</span>
      {#if value.detail}<span class="detail">{value.detail}</span>{/if}
    </span>
    {#if said}<span class="said {said.tone}" title={said.title}>{said.text}</span>{/if}
    {#if count > 1}
      <span class="count">{count} {count === 1 ? "option" : "options"}</span>
      <span class="chevron" aria-hidden="true"></span>
    {/if}
  </button>
{/snippet}

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

  <ul class="build">
    {#if plan.runes}
      {@const value = picks.runes ?? plan.runes.value}
      <li class:open={open.runes}>
        {@render summary(
          "runes",
          "Runes",
          { icons: pageIcons(value), name: page(value), detail: pageDetail(value) },
          note(options.runes, page),
          options.runes.rows.length,
        )}
        {#if open.runes}
          <div class="choices" id="slot-runes">
            <OptionList
              slot={options.runes}
              label={page}
              detail={pageDetail}
              icons={pageIcons}
              onpick={(p) => onpick({ runes: p })}
            />
            {#if byRune.length}
              <section class="by-rune" aria-label="Rune by rune">
                <h4>Rune by rune</h4>
                <p class="hint">
                  Each row of the page above against the other choices in that row. For reading: the import
                  writes a whole page.
                </p>
                {#each byRune as r (r.key)}
                  <div class="rune-row">
                    <h5>{rowTitle(r)}</h5>
                    <OptionList slot={r.slot} label={runes} icons={runeIcons} />
                  </div>
                {/each}
              </section>
            {/if}
          </div>
        {/if}
      </li>
    {/if}

    {#if plan.spells}
      {@const value = picks.spells ?? plan.spells.value}
      <li class:open={open.spells}>
        {@render summary(
          "spells",
          "Spells",
          { icons: spellIcons(value), name: spells(value), detail: "" },
          note(options.spells, spells),
          options.spells.rows.length,
        )}
        {#if open.spells}
          <div class="choices" id="slot-spells">
            <OptionList
              slot={options.spells}
              label={spells}
              icons={spellIcons}
              onpick={(pair) => onpick({ spells: pair })}
            />
          </div>
        {/if}
      </li>
    {/if}

    {#each plan.items as choice (choice.slot)}
      {@const key = `item-${choice.slot}`}
      {@const alts = options.items.find((s) => s.slot === choice.slot) ?? { rows: [], more: 0 }}
      {@const value = slotItem(choice.slot) ?? choice.value}
      <li class:open={open[key]}>
        {@render summary(
          key,
          `Item ${choice.slot}`,
          { icons: itemIcons(value), name: item(value), detail: alsoIn(choice.slot)(value) },
          note(alts, item),
          alts.rows.length,
        )}
        {#if open[key]}
          <div class="choices" id="slot-{key}">
            <OptionList
              slot={alts}
              label={item}
              detail={alsoIn(choice.slot)}
              icons={itemIcons}
              onpick={(id) => onpick({ slot: choice.slot, item: id })}
            />
          </div>
        {/if}
      </li>
    {/each}
  </ul>
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
  .build {
    margin: 0;
    padding: 0;
    overflow: hidden;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    list-style: none;
  }
  .build > li + li {
    border-top: 1px solid var(--color-border);
  }
  .summary {
    display: flex;
    gap: var(--space-3);
    align-items: center;
    width: 100%;
    min-height: 56px;
    padding: var(--space-2) var(--space-4);
    border: none;
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .summary:disabled {
    cursor: default;
  }
  .summary:not(:disabled):hover {
    background: var(--color-bg);
  }
  .summary:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -2px;
  }
  .slot-name {
    flex: 0 0 56px;
    color: var(--color-muted);
    font-size: var(--text-sm);
  }
  .icons {
    display: flex;
    flex: 0 0 auto;
    gap: var(--space-1);
  }
  .value {
    display: grid;
    flex: 1 1 auto;
    min-width: 0;
  }
  .name {
    font-weight: 600;
  }
  /* The slot's name for screen readers and narrow windows; wide ones show it in a column. */
  .caption {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    color: var(--color-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .detail {
    overflow: hidden;
    color: var(--color-muted);
    font-size: var(--text-sm);
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .said {
    flex: 0 0 auto;
    white-space: nowrap;
    font-size: var(--text-sm);
    font-weight: 600;
    text-align: right;
  }
  .said.muted {
    color: var(--color-muted);
    font-weight: 400;
    font-variant-numeric: tabular-nums;
  }
  .said.positive {
    color: var(--color-positive);
  }
  .said.negative {
    color: var(--color-negative);
  }
  .said.picked {
    color: var(--color-accent);
  }
  .count {
    flex: 0 0 auto;
    color: var(--color-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .chevron {
    flex: 0 0 auto;
    width: 8px;
    height: 8px;
    border-right: 2px solid var(--color-muted);
    border-bottom: 2px solid var(--color-muted);
    margin: 0 2px 4px;
    transform: rotate(45deg);
    transition: transform 0.15s;
  }
  .open .chevron {
    margin: 4px 2px 0;
    transform: rotate(-135deg);
  }
  @media (prefers-reduced-motion: reduce) {
    .chevron {
      transition: none;
    }
  }
  .choices {
    padding: 0 var(--space-3) var(--space-3);
  }
  .by-rune {
    display: grid;
    gap: var(--space-2);
    margin-top: var(--space-3);
    padding-top: var(--space-3);
    border-top: 1px dashed var(--color-border);
  }
  .by-rune h4 {
    margin: 0 var(--space-3);
    font-size: var(--text-md);
  }
  .by-rune .hint {
    margin: 0 var(--space-3);
    color: var(--color-muted);
    font-size: var(--text-sm);
  }
  .rune-row h5 {
    margin: var(--space-2) var(--space-3) var(--space-1);
    color: var(--color-muted);
    font-size: var(--text-xs);
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
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
  @media (max-width: 480px) {
    .summary {
      gap: var(--space-2);
      padding: var(--space-2) var(--space-3);
    }
    .summary {
      flex-wrap: wrap;
    }
    .slot-name,
    .count {
      display: none;
    }
    .value {
      flex: 1 1 0;
    }
    /* The number goes under the name, so the name keeps the width. */
    .said {
      order: 1;
      flex-basis: 100%;
      padding-left: calc(var(--icon-md) + var(--space-2));
      text-align: left;
      white-space: normal;
    }
    .caption {
      position: static;
      width: auto;
      height: auto;
      clip-path: none;
    }
    .choices {
      padding: 0 var(--space-1) var(--space-2);
    }
  }
</style>
