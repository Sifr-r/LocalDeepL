<script lang="ts">
  /**
   * Test fixture: lightweight stand-in for the chrome (always-mounted)
   * components — ``TabRibbon``, ``ToastContainer``, ``ProviderModal``,
   * ``ExportModal``. Renders a single ``<div>`` tagged with
   * ``data-chrome={name}`` so a test can assert which chrome elements
   * are mounted without exercising the real components' full behaviour
   * (which pulls in stores, services, and a websocket connection).
   */
  export let name: string = 'unknown';
</script>

<div data-chrome={name} class="mock-chrome"></div>
