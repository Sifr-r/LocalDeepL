<script lang="ts">
  import MockChrome from './MockChrome.svelte';
</script>

<!--
  F3.3 mock: the auth-required banner is conditional on the
  ``$authRequired`` store flag. The App.svelte mounting test
  defaults the flag to false, so the banner does not render in
  that scenario. A dedicated AuthRequiredBanner.test.ts would
  exercise the ``{#if $authRequired}`` branch by writing to the
  store; that test belongs in a follow-up.
-->
<MockChrome name="auth-banner" />
