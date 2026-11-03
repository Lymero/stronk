<script lang="ts">
  // The web viewer's champion and role (ADR-086): where the app follows champion select, the
  // viewer lets the player choose. Champions by name with a search, each with its roles that
  // have a build, the one shown marked.
  import type { GameNames, Role } from "../../backend/backend.ts";
  import type { Viewable } from "../../state/app.svelte.ts";
  import Icon from "../../ui/Icon.svelte";
  import { type Icons, icon, role as roleName } from "../../ui/labels.ts";

  let {
    builds,
    names,
    icons,
    selected,
    onchoose,
  }: {
    builds: Viewable[];
    names: GameNames | null;
    icons: Icons;
    selected: { champion: string; role: Role } | null;
    onchoose: (champion: string, role: Role) => void;
  } = $props();

  const ROLES: Role[] = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"];
  let search = $state("");
  /** The role whose builds are listed: the one shown, else Top. */
  let chosenRole = $state<Role | null>(null);
  const shownRole = $derived(chosenRole ?? selected?.role ?? "TOP");

  /** The champion's name in the game data, else its key (`LeeSin`). */
  const nameOf = (b: Viewable) => (b.id > 0 ? names?.champions[String(b.id)] : undefined) ?? b.champion;
  /** Letters and digits only, so "lee sin", "LeeSin" and "Lee'Sin" find the same champion. */
  const plain = (s: string) => s.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
  /** The champions with a build in the role, by name, matching the search. */
  const shown = $derived(
    builds
      .filter((b) => b.role === shownRole)
      .map((b) => ({ key: b.champion, id: b.id, name: nameOf(b) }))
      .filter((c) => plain(c.name).includes(plain(search)) || plain(c.key).includes(plain(search)))
      .sort((a, b) => a.name.localeCompare(b.name)),
  );

  /** Another role lists its champions, and shows the current champion in it when it has a build there. */
  function pickRole(r: Role): void {
    chosenRole = r;
    if (selected && selected.role !== r && builds.some((b) => b.champion === selected.champion && b.role === r)) {
      onchoose(selected.champion, r);
    }
  }
</script>

<section class="picker" aria-label="Choose a champion">
  <div class="bar">
    <div class="roles" role="group" aria-label="Role">
      {#each ROLES as r (r)}
        <button type="button" aria-pressed={shownRole === r} onclick={() => pickRole(r)}>{roleName(r)}</button>
      {/each}
    </div>
    <label class="search">
      <span class="visually-hidden">Find a champion</span>
      <input type="search" placeholder="Find a champion" bind:value={search} autocomplete="off" spellcheck="false" />
    </label>
  </div>
  <ul class="champions">
    {#each shown as c (c.key)}
      <li>
        <button
          type="button"
          class:current={selected?.champion === c.key && selected.role === shownRole}
          aria-label={`${c.name} ${roleName(shownRole)}`}
          onclick={() => onchoose(c.key, shownRole)}
        >
          <Icon src={icon(icons, "champions", c.id)} name={c.name} size="md" round />
          <span class="name">{c.name}</span>
        </button>
      </li>
    {:else}
      <li class="none">{search ? `No champion matches “${search}” in ${roleName(shownRole)}.` : `No builds in ${roleName(shownRole)}.`}</li>
    {/each}
  </ul>
</section>

<style>
  .picker {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
  }
  .bar {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2) var(--space-3);
    align-items: center;
  }
  .roles {
    display: flex;
    gap: 2px;
    padding: 2px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
  }
  .roles button {
    padding: var(--space-1) var(--space-3);
    border: none;
    border-radius: var(--radius);
    background: none;
    color: var(--color-muted);
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }
  .roles button[aria-pressed="true"] {
    background: var(--color-accent-bg);
    color: var(--color-text);
  }
  .search {
    flex: 1 1 200px;
  }
  .search input {
    width: 100%;
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-bg);
    color: var(--color-text);
    font: inherit;
  }
  .champions {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 2px var(--space-2);
    max-height: 212px;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    list-style: none;
  }
  .champions button {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    width: 100%;
    padding: var(--space-1) var(--space-2);
    border: 1px solid transparent;
    border-radius: var(--radius);
    background: none;
    color: var(--color-text);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .champions button:hover {
    border-color: var(--color-border);
  }
  .champions button.current {
    border-color: var(--color-accent);
    background: var(--color-accent-bg);
  }
  .name {
    min-width: 0;
    overflow: hidden;
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .none {
    color: var(--color-muted);
  }
  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }
</style>
