<script lang="ts">
  import type { Build } from "../../backend/backend.ts";
  import Flag from "../../ui/Flag.svelte";

  let { build }: { build: Build } = $props();

  const percent = (v: number) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
</script>

<section class="build" aria-label="Build">
  <p class="meta">Patch {build.patch} · {build.games} {build.games === 1 ? "game" : "games"}</p>

  <h3>Runes</h3>
  {#each build.runes as rune, i (i)}
    <div class="row">
      <span class="mono">{rune.page.perks.join(" · ")}</span>
      {#if rune.wpa !== null && rune.wpa !== undefined}<span class="wpa">{percent(rune.wpa)}</span>{/if}
      {#each rune.flags as flag (flag)}<Flag {flag} />{/each}
    </div>
  {/each}

  <h3>Items</h3>
  {#each build.items as item, i (i)}
    <div class="row">
      <span class="slot">Slot {item.slot}</span>
      <span class="mono">{item.item}</span>
      {#if item.wpa !== null && item.wpa !== undefined}<span class="wpa">{percent(item.wpa)}</span>{/if}
      {#each item.flags as flag (flag)}<Flag {flag} />{/each}
    </div>
  {/each}
</section>

<style>
  .build {
    padding: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-surface);
  }
  h3 {
    margin: var(--space-4) 0 var(--space-2);
    font-size: var(--text-md);
  }
  .row {
    display: flex;
    gap: var(--space-3);
    align-items: center;
    padding: var(--space-1) 0;
  }
  .meta,
  .slot {
    color: var(--color-muted);
  }
  .meta {
    margin: 0;
  }
  .mono {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
  }
  .wpa {
    color: var(--color-accent);
  }
</style>
