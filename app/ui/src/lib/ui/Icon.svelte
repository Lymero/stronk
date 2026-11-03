<script lang="ts">
  // A champion, rune, spell or item icon from the client (`icons.get`); until it loads, when
  // the client has none, or when the image fails (the web viewer's are addresses, ADR-086), a
  // plain square with the name's first letter. Decorative: the name is always written next to it.
  let {
    src,
    name,
    size = "md",
    round = false,
  }: {
    src: string | null | undefined;
    name: string;
    size?: "sm" | "md" | "lg";
    round?: boolean;
  } = $props();

  /** The address that failed to load, so a new one is tried again. */
  let failed = $state<string | null>(null);
</script>

{#if src && src !== failed}
  <img class="icon {size}" class:round {src} alt="" aria-hidden="true" draggable="false" onerror={() => (failed = src ?? null)} />
{:else}
  <span class="icon {size} stand-in" class:round aria-hidden="true">{name.charAt(0)}</span>
{/if}

<style>
  .icon {
    display: inline-grid;
    flex: 0 0 auto;
    place-items: center;
    width: var(--icon-md);
    height: var(--icon-md);
    border-radius: var(--radius);
    object-fit: cover;
    vertical-align: middle;
  }
  .sm {
    width: var(--icon-sm);
    height: var(--icon-sm);
    border-radius: var(--radius-sm);
    font-size: var(--text-xs);
  }
  .lg {
    width: var(--icon-lg);
    height: var(--icon-lg);
    font-size: var(--text-xl);
  }
  .round {
    border-radius: 50%;
  }
  .stand-in {
    background: var(--color-track);
    color: var(--color-muted);
    font-size: var(--text-sm);
    font-weight: 700;
  }
  .lg.stand-in {
    background: var(--color-accent-bg);
    color: var(--color-accent);
    font-size: var(--text-xl);
  }
</style>
