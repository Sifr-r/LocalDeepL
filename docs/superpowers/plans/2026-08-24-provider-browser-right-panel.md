# Persistent Provider Browser Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the provider catalog into a persistent right-side settings panel while preserving the existing provider connection modal and immediate model application behavior.

**Architecture:** Extract the catalog, model discovery, filtering, and provider-card markup from `ProviderModal.svelte` into a reusable `ProviderBrowser.svelte`. A shared `applyProviderPreset` action handles persistence and toasts for both the modal and settings panel, while `providerModalStore` accepts an optional preselected provider so a settings-panel Connect action opens directly into the existing connection form.

**Tech Stack:** Svelte 5, TypeScript, Tailwind CSS 4, Vitest, Testing Library-style DOM queries through `mount`, vitest-axe, Fetch API helpers.

---

## File Structure

- Create `frontend/src/lib/components/modals/providerActions.ts` — shared provider application, persistence, and toast logic.
- Create `frontend/src/lib/components/modals/providerActions.test.ts` — success, namespace, and persistence-failure tests for the shared action.
- Create `frontend/src/lib/components/modals/ProviderBrowser.svelte` — reusable catalog, search, refresh, and provider-card UI.
- Create `frontend/src/lib/components/modals/ProviderBrowser.test.ts` — direct browser behavior and callback tests.
- Create `frontend/src/lib/components/views/SettingsView.provider-panel.test.ts` — persistent panel, target switching, focus, and immediate-apply tests.
- Modify `frontend/src/lib/stores/providerModalStore.ts` — store a preselected provider for direct connection-form opening.
- Create `frontend/src/lib/stores/providerModalStore.test.ts` — selection-preservation tests.
- Modify `frontend/src/lib/components/modals/ProviderModal.svelte` — modal shell and connection form backed by `ProviderBrowser`.
- Modify `frontend/src/lib/components/modals/ProviderModal.test.ts` — regression coverage through the extracted browser and preselection path.
- Modify `frontend/src/lib/components/views/SettingsView.svelte` — persistent responsive provider panel and scroll/focus header action.
- Modify `frontend/src/__tests__/a11y.test.ts` — mock provider discovery and include the new panel in existing axe coverage.
- Do not modify backend routes, runtime configuration schemas, or unrelated settings components.

## Assumptions

- The panel mounts once for the lifetime of `SettingsView`, outside the active-tab conditional, and receives a reactive target namespace.
- The auth tab maps to `general`; OCR, translation, and transcription map directly to their provider target type.
- Existing Tailwind breakpoints and design tokens remain unchanged.
- No commits are created unless the user explicitly requests them.

### Task 1: Add the shared provider application action

**Files:**
- Create: `frontend/src/lib/components/modals/providerActions.ts`
- Create: `frontend/src/lib/components/modals/providerActions.test.ts`

- [ ] **Step 1: Write failing action tests**

Mock `appStore` with an in-memory `configStore`, update spies, and `toastStore`; mock `setActiveProvider`. Add the following exact behavior tests:

```ts
const provider = {
  id: 'openai',
  name: 'OpenAI',
  category: 'popular',
  description: '',
  recommended_base_url: 'https://api.openai.com/v1',
  default_model: 'gpt-4o',
  requires_key: true,
  notes: ''
};

it('applies an OCR provider and reports success only after persistence', async () => {
  vi.mocked(setActiveProvider).mockResolvedValue({
    api_base: provider.recommended_base_url,
    model: provider.default_model
  });

  const result = await applyProviderPreset(provider, 'ocr', {
    modelOverride: 'gpt-4o-mini',
    apiKeyOverride: 'sk-test'
  });

  const cfg = get(configStore);
  expect(result).toBe(true);
  expect(setActiveProvider).toHaveBeenCalledWith({
    provider_id: 'openai',
    api_base: 'https://api.openai.com/v1',
    model: 'gpt-4o-mini'
  });
  expect(updateOcrNamespace).toHaveBeenCalledWith({
    ocr_api_base: 'https://api.openai.com/v1',
    ocr_model: 'gpt-4o-mini',
    ocr_provider: 'openai',
    ocr_api_key: 'sk-test'
  });
  expect(cfg.ocr_api_key).toBe('sk-test');
  expect(pushToast).toHaveBeenCalledWith(
    'success',
    'Connected provider: OpenAI (ocr)'
  );
});

it('returns false and shows an error when persistence fails', async () => {
  vi.mocked(setActiveProvider).mockRejectedValue(new Error('server unavailable'));

  const result = await applyProviderPreset(provider, 'translation', {
    modelOverride: 'translated-model'
  });

  expect(result).toBe(false);
  expect(updateTranslationNamespace).not.toHaveBeenCalled();
  expect(pushToast).toHaveBeenCalledWith(
    'error',
    'Failed to apply provider: server unavailable'
  );
});
```

Also add a translation assertion proving `translation_provider` and `translation_model` are written together. Reset all spies and writable stores in `beforeEach`.

- [ ] **Step 2: Run the focused test and verify failure**

Run from `frontend/`:

```powershell
npm test -- src/lib/components/modals/providerActions.test.ts
```

Expected: FAIL because `applyProviderPreset` does not exist.

- [ ] **Step 3: Implement `applyProviderPreset`**

Create the helper with this public contract:

```ts
export interface ApplyProviderPresetOptions {
  modelOverride?: string;
  apiKeyOverride?: string;
  apiBaseOverride?: string;
}

export async function applyProviderPreset(
  provider: ProviderPreset,
  target: ProviderTargetNamespace,
  options: ApplyProviderPresetOptions = {}
): Promise<boolean>;
```

Implementation requirements:

1. Resolve `base = apiBaseOverride ?? provider.api_base ?? provider.recommended_base_url`.
2. Resolve `model = modelOverride ?? provider.default_model ?? provider.models?.[0] ?? ''`.
3. Optimistically update only the matching `configStore` namespace fields, exactly matching current modal behavior.
4. Call `setActiveProvider` with `provider_id`, `api_base`, and `model`.
5. Persist the matching namespace through `updateOcrNamespace`, `updateTranslationNamespace`, or `updateTranscriptionNamespace`; do not call a namespace endpoint for `general`.
6. Push the current success message `Connected provider: <name> (<target>)` and return `true` only after all required persistence succeeds.
7. On failure, push `error` with `Failed to apply provider: <message>` and return `false`.
8. Do not log API keys or include them in toast text.

- [ ] **Step 4: Run the focused test and verify success**

Run:

```powershell
npm test -- src/lib/components/modals/providerActions.test.ts
```

Expected: all provider action tests pass.

### Task 2: Add preselected-provider modal state

**Files:**
- Modify: `frontend/src/lib/stores/providerModalStore.ts`
- Create: `frontend/src/lib/stores/providerModalStore.test.ts`

- [ ] **Step 1: Write the failing store test**

```ts
import { get } from 'svelte/store';
import {
  closeProviderModal,
  isProviderModalOpen,
  openProviderModal,
  providerToConnect
} from './providerModalStore';

it('opens the modal for a preselected provider', () => {
  const provider = { id: 'lmstudio', name: 'LM Studio' } as ProviderPreset;

  openProviderModal('ocr', provider);

  expect(get(isProviderModalOpen)).toBe(true);
  expect(get(providerToConnect)?.id).toBe('lmstudio');
});

it('clears the preselected provider on close', () => {
  openProviderModal('general', { id: 'custom', name: 'Custom' } as ProviderPreset);
  closeProviderModal();

  expect(get(isProviderModalOpen)).toBe(false);
  expect(get(providerToConnect)).toBeNull();
});
```

- [ ] **Step 2: Run the store test and verify failure**

Run:

```powershell
npm test -- src/lib/stores/providerModalStore.test.ts
```

Expected: FAIL because `providerToConnect` and the second `openProviderModal` argument do not exist.

- [ ] **Step 3: Implement the preselection store**

Import `ProviderPreset` and add:

```ts
export const providerToConnect = writable<ProviderPreset | null>(null);

export function openProviderModal(
  targetNamespace: ProviderTargetNamespace = 'general',
  provider: ProviderPreset | null = null
): void {
  providerTargetNamespace.set(targetNamespace);
  providerToConnect.set(provider);
  isProviderModalOpen.set(true);
}

export function closeProviderModal(): void {
  providerToConnect.set(null);
  isProviderModalOpen.set(false);
}
```

- [ ] **Step 4: Run the store test and verify success**

Run:

```powershell
npm test -- src/lib/stores/providerModalStore.test.ts
```

Expected: both tests pass.

### Task 3: Extract the reusable ProviderBrowser

**Files:**
- Create: `frontend/src/lib/components/modals/ProviderBrowser.svelte`
- Create: `frontend/src/lib/components/modals/ProviderBrowser.test.ts`

- [ ] **Step 1: Create failing browser tests**

Mock only `getProviders` and `getProviderModels`. Mount the browser with callback spies and add tests for these exact contracts:

```ts
it('loads providers and invokes the select callback with the chosen provider', async () => {
  state.providers = [makeProvider({ id: 'a', name: 'Provider A' })];
  state.modelsResponses.set('a', { models: ['m1'], error: null });
  const onSelect = vi.fn();

  mount(ProviderBrowser, { target, props: { onSelect } });
  await flushProviderState();

  document.querySelector<HTMLButtonElement>(
    '[data-testid="provider-card"][data-provider-id="a"] button'
  )?.click();
  await tick();

  expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'a' }));
});

it('filters providers and invokes onUseModel for a model action', async () => {
  state.providers = [makeProvider({ id: 'anthropic', name: 'Anthropic', category: 'popular' })];
  state.modelsResponses.set('anthropic', { models: ['claude-a', 'claude-b'], error: null });
  const onUseModel = vi.fn();

  mount(ProviderBrowser, { target, props: { onUseModel } });
  await flushProviderState();

  const input = document.querySelector<HTMLInputElement>('[data-testid="provider-search-input"]')!;
  input.value = 'claude';
  input.dispatchEvent(new Event('input'));
  await tick();

  expect(document.querySelectorAll('[data-testid="provider-card"]')).toHaveLength(1);
  document.querySelector<HTMLButtonElement>('[data-testid="provider-models-toggle"]')?.click();
  await tick();
  document.querySelector<HTMLButtonElement>('[data-testid="provider-models-list"] button')?.click();

  expect(onUseModel).toHaveBeenCalledWith(
    expect.objectContaining({ id: 'anthropic' }),
    'claude-a'
  );
});
```

Retain and parameterize the existing modal tests' coverage for fan-out, successful model count, provider error, placeholder URL, and per-provider refresh. Add an assertion that `fillContainer={true}` applies the internal scroll layout.

- [ ] **Step 2: Run browser tests and verify failure**

Run:

```powershell
npm test -- src/lib/components/modals/ProviderBrowser.test.ts
```

Expected: FAIL because `ProviderBrowser.svelte` does not exist.

- [ ] **Step 3: Move the provider-list behavior into the new component**

Move from `ProviderModal.svelte` into `ProviderBrowser.svelte`:

- `ModelState`, `ProviderModelEntry`, `MAX_CONCURRENT_FETCHES`, and `PLACEHOLDER_URL_NEEDLES`.
- `providers`, `loading`, `error`, `searchQuery`, `modelState`, `fetchingIds`, and `expandedIds`.
- `loadCatalog`, `runWithLimit`, `isPlaceholderUrl`, `loadModelsForProvider`, `autoLoadAllModels`, `toggleExpanded`, and `refreshOne`.
- `filteredProviders`, `popularProviders`, and `otherProviders`.
- The search input, provider count/refresh controls, loading/error/empty states, and all Popular/Other card markup.

Expose this exact component interface:

```ts
export let onSelect: (provider: ProviderPreset) => void = () => {};
export let onUseModel: (provider: ProviderPreset, model: string) => void = () => {};
export let fillContainer: boolean = false;
```

Mount behavior:

```ts
import { onMount } from 'svelte';

onMount(() => {
  void loadCatalog();
});
```

Selection behavior:

```ts
function selectProvider(provider: ProviderPreset): void {
  if (!modelState[provider.id] || modelState[provider.id].state === 'idle') {
    void loadModelsForProvider(provider);
  }
  onSelect(provider);
}
```

Use `selectProvider(provider)` for both the provider summary button and the Connect button, but retain `stopPropagation()` in `refreshOne`.

Use these layout classes:

```svelte
<div
  class={fillContainer
    ? 'flex min-h-0 flex-1 flex-col gap-4 p-4'
    : 'space-y-4 p-4'}
  data-testid="provider-browser"
>
  <!-- search and controls -->
  <div
    class={fillContainer
      ? 'min-h-0 flex-1 overflow-y-auto space-y-5 pr-1'
      : 'max-h-[60vh] overflow-y-auto space-y-5 pr-1'}
    data-testid="provider-results"
  >
    <!-- existing loading/error/empty/sections -->
  </div>
</div>
```

Preserve all current data-test IDs, provider model behavior, and visible copy.

- [ ] **Step 4: Run browser tests and verify success**

Run:

```powershell
npm test -- src/lib/components/modals/ProviderBrowser.test.ts
```

Expected: all `ProviderBrowser` tests pass.

- [ ] **Step 5: Run formatting and type checks**

Run:

```powershell
npx prettier --check src/lib/components/modals/ProviderBrowser.svelte src/lib/components/modals/ProviderBrowser.test.ts
npm run check
```

Expected: formatting reports no changes and `svelte-check` reports zero errors. Fix only issues caused by this new component.

### Task 4: Refactor ProviderModal around ProviderBrowser

**Files:**
- Modify: `frontend/src/lib/components/modals/ProviderModal.svelte`
- Modify: `frontend/src/lib/components/modals/ProviderModal.test.ts`

- [ ] **Step 1: Add failing modal regression cases**

Update the store mock to include `providerToConnect` and add these cases:

```ts
it('opens the connection form for a preselected provider without loading the list', async () => {
  state.providers = [];
  providerToConnect.set(makeProvider({ id: 'lmstudio' }));

  mountModal();
  isProviderModalOpen.set(true);
  await tick();
  await tick();

  expect(getProviders).not.toHaveBeenCalled();
  expect(document.querySelector('[data-testid="provider-connect-panel"]')).not.toBeNull();
});

it('Connect from the browser opens the existing configuration form', async () => {
  state.providers = [makeProvider({ id: 'openai', name: 'OpenAI', category: 'popular' })];
  state.modelsResponses.set('openai', { models: ['gpt-4o'], error: null });

  mountModal();
  await openModal();
  document.querySelector<HTMLButtonElement>(
    '[data-testid="provider-card"][data-provider-id="openai"] button:last-of-type'
  )?.click();
  await tick();

  expect(document.querySelector('#provider-api-key-input')).not.toBeNull();
  expect(document.querySelector('#provider-model-input')).not.toBeNull();
});
```

Also update the custom-credentials test's mocked `appStore` with `updateOcrNamespace`, `updateTranslationNamespace`, and `updateTranscriptionNamespace` spies.

- [ ] **Step 2: Run the modal tests and verify failure**

Run:

```powershell
npm test -- src/lib/components/modals/ProviderModal.test.ts
```

Expected: FAIL because the preselected store field and extracted component are not wired in.

- [ ] **Step 3: Reduce ProviderModal to shell, selection, and connection form**

Keep in `ProviderModal.svelte`:

- Modal open state and `closeModal`.
- `selectedProvider` and all selected-provider form state.
- `startConnect`, `backToList`, `runConnectionTest`, and `submitConnectForm`.
- `selectedProviderKnownModels` fallback.
- The existing selected-provider banner, form fields, validation feedback, and actions.

Remove from the modal:

- `getProviders`, `getProviderModels`, and all provider catalog/model-discovery state and functions.
- The old Popular/Other list markup.
- The old local `applyPreset` implementation.

Import and use:

```ts
import ProviderBrowser from './ProviderBrowser.svelte';
import { applyProviderPreset } from './providerActions';
import {
  closeProviderModal,
  isProviderModalOpen,
  providerTargetNamespace,
  providerToConnect
} from '../../stores/providerModalStore';
```

Replace the catalog branch with:

```svelte
{:else if $isProviderModalOpen}
  <ProviderBrowser
    onSelect={startConnect}
    onUseModel={applyWithModel}
  />
{/if}
```

Replace the open trigger with:

```ts
$: if ($isProviderModalOpen && !lastOpen) {
  lastOpen = true;
  selectedProvider = null;
  testResult = null;
  showApiKey = false;

  const requested = $providerToConnect;
  providerToConnect.set(null);
  if (requested) {
    startConnect(requested);
  }
} else if (!$isProviderModalOpen && lastOpen) {
  lastOpen = false;
}
```

Implement model application and form submission with the shared action and return value:

```ts
async function applyWithModel(provider: ProviderPreset, model: string): Promise<void> {
  if (await applyProviderPreset(provider, $providerTargetNamespace, {
    modelOverride: model
  })) {
    closeModal();
  }
}

async function submitConnectForm(): Promise<void> {
  if (!selectedProvider) return;
  isSaving = true;
  try {
    const applied = await applyProviderPreset(selectedProvider, $providerTargetNamespace, {
      modelOverride: customModel,
      apiKeyOverride: customApiKey || undefined,
      apiBaseOverride: customApiBase || undefined
    });
    if (applied) closeModal();
  } finally {
    isSaving = false;
  }
}
```

- [ ] **Step 4: Run focused tests and verify success**

Run:

```powershell
npm test -- src/lib/components/modals/ProviderModal.test.ts src/lib/components/modals/ProviderBrowser.test.ts
```

Expected: all browser and modal regression tests pass.

### Task 5: Embed the persistent panel in SettingsView

**Files:**
- Modify: `frontend/src/lib/components/views/SettingsView.svelte`
- Create: `frontend/src/lib/components/views/SettingsView.provider-panel.test.ts`
- Modify: `frontend/src/__tests__/a11y.test.ts`

- [ ] **Step 1: Write failing settings-panel tests**

Create the test with mocked discovery and persistence:

```ts
vi.mock('$lib/api/client', () => ({
  fetchApi: vi.fn().mockResolvedValue({})
}));

vi.mock('$lib/api/endpoints', () => ({
  getProviders: vi.fn().mockResolvedValue([
    {
      id: 'mock',
      name: 'Mock Provider',
      category: 'popular',
      description: 'Mock models',
      recommended_base_url: 'http://localhost:1234/v1',
      default_model: 'mock-model',
      requires_key: false,
      models: ['mock-model'],
      notes: ''
    }
  ]),
  getProviderModels: vi.fn().mockResolvedValue({
    models: ['mock-model'],
    error: null
  }),
  setActiveProvider: vi.fn().mockResolvedValue({
    api_base: 'http://localhost:1234/v1',
    model: 'mock-model'
  })
}));
```

Add these exact tests:

1. The `#provider-browser` panel is present on mount and remains present after clicking OCR, translation, transcription, and auth tabs.
2. Clicking `Browse provider presets` calls `scrollIntoView` on the panel and leaves the provider search input focused.
3. Clicking the auth tab, then a provider's left action button, sets `providerToConnect` to that provider and `isProviderModalOpen` to `true`.
4. Expanding a provider in OCR and clicking `Use` leaves the panel open, updates `configStore.ocr_model` to `mock-model`, calls `setActiveProvider` with the provider details, and pushes a success toast.
5. The layout wrapper includes responsive `grid-cols-1` and `xl:grid-cols-[minmax(0,3fr)_minmax(28rem,2fr)]` classes.

Use `vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => {})` in the focus test and reset the store/modal/timer state after each test.

- [ ] **Step 2: Run the settings tests and verify failure**

Run:

```powershell
npm test -- src/lib/components/views/SettingsView.provider-panel.test.ts
```

Expected: FAIL because the persistent panel and scroll/focus action are not present.

- [ ] **Step 3: Add imports and provider application wiring**

Update `SettingsView.svelte` imports:

```ts
import { openProviderModal } from '$lib/stores/providerModalStore';
import { applyProviderPreset } from '../modals/providerActions';
import ProviderBrowser from '../modals/ProviderBrowser.svelte';
import type { ProviderPreset } from '$lib/types/api';
import type { ProviderTargetNamespace } from '$lib/stores/providerModalStore';
```

Add the reactive target and handlers:

```ts
$: providerTarget = (activeNamespace === 'auth'
  ? 'general'
  : activeNamespace) as ProviderTargetNamespace;

function focusProviderBrowser(): void {
  requestAnimationFrame(() => {
    const panel = document.getElementById('provider-browser');
    const search = document.getElementById('provider-search-input');
    panel?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    search?.focus({ preventScroll: true });
  });
}

function openProviderConfiguration(provider: ProviderPreset): void {
  openProviderModal(providerTarget, provider);
}

function useProviderModel(provider: ProviderPreset, model: string): void {
  void applyProviderPreset(provider, providerTarget, { modelOverride: model });
}
```

Change the header button to:

```svelte
<Button variant="secondary" on:click={focusProviderBrowser}>
```

- [ ] **Step 4: Replace the single tab-content container with the two-column layout**

Keep the tabs unchanged. Replace the current `flex-1 overflow-y-auto pr-1` tab-content wrapper with this structure, moving the existing active-panel `if/else if` content into its left column:

```svelte
<div class="grid min-h-0 flex-1 grid-cols-1 gap-6 overflow-y-auto pr-1 xl:grid-cols-[minmax(0,3fr)_minmax(28rem,2fr)]">
  <div class="min-w-0">
    {#if activeNamespace === 'ocr'}
      <!-- existing OCR tabpanel; remove max-w-3xl from Card -->
    {:else if activeNamespace === 'translation'}
      <!-- existing translation tabpanel; remove max-w-3xl from Card -->
    {:else if activeNamespace === 'transcription'}
      <!-- existing transcription tabpanel; remove max-w-3xl from Card -->
    {:else}
      <!-- existing auth tabpanel; remove max-w-3xl from Card -->
    {/if}
  </div>

  <div id="provider-browser" class="min-w-0 scroll-mt-4">
    <Card
      padding="none"
      class="flex min-h-[32rem] flex-col overflow-hidden xl:sticky xl:top-4 xl:h-[calc(100vh-11rem)]"
    >
      <div class="p-4 border-b border-border">
        <h3 class="font-display text-sm font-semibold text-foreground">Provider catalog</h3>
        <p class="mt-1 text-xs text-foreground-muted">
          Browse providers, discover models, and connect an endpoint.
        </p>
      </div>
      <ProviderBrowser
        fillContainer={true}
        onSelect={openProviderConfiguration}
        onUseModel={useProviderModel}
      />
    </Card>
  </div>
</div>
```

Important constraints:

- Place the panel outside the `{#if activeNamespace...}` chain so it is never destroyed during tab changes.
- The panel is second in DOM and stacks below settings below `xl`.
- Use a single `h3` for the provider catalog immediately after the settings `h2`; do not introduce a skipped heading level.
- Remove `max-w-3xl` only from the four active settings cards.
- Pass `fillContainer={true}` so the results region scrolls while search and controls stay visible.

- [ ] **Step 5: Run settings tests and verify success**

Run:

```powershell
npm test -- src/lib/components/views/SettingsView.provider-panel.test.ts
```

Expected: all persistent-panel tests pass.

- [ ] **Step 6: Extend accessibility test mocks and coverage**

In `frontend/src/__tests__/a11y.test.ts`, preserve all actual endpoint exports while overriding discovery:

```ts
vi.mock('$lib/api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('$lib/api/endpoints')>();
  return {
    ...actual,
    getProviders: vi.fn().mockResolvedValue([]),
    getProviderModels: vi.fn().mockResolvedValue({ models: [], error: null })
  };
});
```

Add a test that mounts SettingsView, confirms `#provider-browser` exists, and runs axe with the same known-heading allowlist used by the existing SettingsView test. The test must fail if a serious or critical violation appears.

- [ ] **Step 7: Run focused accessibility and type checks**

Run:

```powershell
npm test -- src/__tests__/a11y.test.ts
npm run check
```

Expected: all accessibility tests pass and `svelte-check` reports zero errors.

### Task 6: Full validation and visual verification

**Files:**
- Verify only; no additional source files expected.

- [ ] **Step 1: Format the changed frontend files**

Run from `frontend/`:

```powershell
npx prettier --check src/lib/components/modals/ProviderBrowser.svelte src/lib/components/modals/providerActions.ts src/lib/components/modals/providerActions.test.ts src/lib/components/modals/ProviderModal.svelte src/lib/components/modals/ProviderModal.test.ts src/lib/components/modals/ProviderBrowser.test.ts src/lib/stores/providerModalStore.ts src/lib/stores/providerModalStore.test.ts src/lib/components/views/SettingsView.svelte src/lib/components/views/SettingsView.provider-panel.test.ts src/__tests__/a11y.test.ts
```

Expected: `All matched files use Prettier code style!`. If formatting fails, run Prettier only on the listed files, inspect the diff, then rerun the check.

- [ ] **Step 2: Run the full frontend test suite**

Run:

```powershell
npm test
```

Expected: all Vitest suites pass with no failed tests.

- [ ] **Step 3: Run the production frontend build**

Run:

```powershell
npm run build
```

Expected: Vite completes successfully and writes the production assets under `src/omniscribe/static/` without a chunk-size or TypeScript error.

- [ ] **Step 4: Start the frontend and visually verify the wide layout**

Start the dev server in the background:

```powershell
npm run dev -- --host 127.0.0.1
```

Open the provided preview, navigate to Settings, and verify:

- The active settings card occupies the left column.
- The provider catalog uses the right column.
- Search, count, and refresh controls remain visible while provider cards scroll.
- Connect opens the existing configuration dialog.
- Use updates the active settings model and leaves the panel open.
- The server-auth tab uses the general provider target.
- No right-column panel overlaps the page or header.

- [ ] **Step 5: Visually verify the stacked layout**

Resize the preview to a narrow width below the `xl` breakpoint and verify:

- The active settings card appears first.
- The provider panel appears below it without a fixed viewport height.
- Provider cards and action buttons wrap without horizontal overflow.
- The header button still scrolls to and focuses the panel search.

- [ ] **Step 6: Stop the dev server and report evidence**

Stop the background dev server, then report the exact results of the focused tests, full test suite, type check, build, and visual checks. Do not commit or push changes.
