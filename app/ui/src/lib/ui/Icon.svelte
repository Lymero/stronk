<script lang="ts">
  // A champion, rune, spell or item icon from the client (`icons.get`); until it loads, or when
  // the client has none, a plain square with the name's first letter. Decorative: the name is
  // always written next to it.
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
</script>

{#if src}
  <img class="icon {size}" class:round {src} alt="" aria-hidden="true" draggable="false" />
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
