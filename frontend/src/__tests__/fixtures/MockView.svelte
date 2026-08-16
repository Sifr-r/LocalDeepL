<script lang="ts">
  /**
   * Test fixture: lightweight stand-in for the real top-level view
   * components. Renders a single ``<section>`` whose ``data-view``
   * attribute identifies the view, so a test can mount ``App.svelte``
   * with the real components stubbed and still count how many views are
   * in the DOM at any time.
   *
   * Empty body intentionally mirrors the visible footprint of the real
   * views (a ``<section>`` wrapper) so any CSS keyed on the real element
   * type keeps working in tests.
   */
  export let name: string = 'unknown';
</script>

<section data-view={name} class="mock-view"></section>
