<script lang="ts">
  // A choice beside the import, each option a segment: the elo bracket builds come from (ADR-078)
  // and the games they count (ADR-088). One click asks the plan again, and the app remembers it.
  let {
    name,
    label,
    about,
    options,
    value,
    onchange,
  }: {
    /** The radios' group name. */
    name: string;
    /** What the choice is, for assistive technology. */
    label: string;
    /** What the options mean, on hover. */
    about: string;
    options: { id: string; label: string }[];
    value: string;
    onchange: (id: string) => void;
  } = $props();
</script>

<div class="switch" role="radiogroup" aria-label={label} title={about}>
  {#each options as option (option.id)}
    <label class:on={option.id === value}>
      <input type="radio" {name} value={option.id} checked={option.id === value} onchange={() => onchange(option.id)} />
      {option.label}
    </label>
  {/each}
</div>

<style>
  .switch {
    display: inline-flex;
    padding: 2px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-bg);
  }
  label {
    padding: var(--space-1) var(--space-3);
    border-radius: var(--radius-sm);
    color: var(--color-muted);
    font-size: var(--text-sm);
    font-weight: 600;
    cursor: pointer;
  }
  label:hover {
    color: var(--color-text);
  }
  label.on {
    background: var(--color-surface);
    box-shadow: var(--shadow);
    color: var(--color-text);
  }
  label:has(input:focus-visible) {
    outline: 2px solid var(--color-accent);
    outline-offset: 1px;
  }
  /* The radio is the label: the dot would only take room. */
  input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }
</style>
