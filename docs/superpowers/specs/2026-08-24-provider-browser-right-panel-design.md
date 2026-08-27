# Persistent Provider Browser Panel Design

**Date:** 2026-08-24  
**Status:** Approved in conversation; pending written-spec review

## Summary

Move the provider catalog from a centered overlay into a persistent panel in the unused right side of the System Configuration page. Keep the existing connection configuration modal for providers where credentials, endpoint details, or model selection must be reviewed before connection.

Use a reusable `ProviderBrowser` component so provider loading, filtering, model discovery, refresh, and card behavior are shared by the settings page and the existing modal.

## Goals

- Use the settings page's available right-side space for the provider catalog.
- Keep the provider catalog visible across all settings namespace tabs.
- Preserve the existing provider model-discovery and application behavior.
- Allow immediate application of a model from an expanded provider list.
- Retain the connection configuration dialog for provider-specific credentials and endpoint details.
- Keep the settings header action useful by scrolling to and focusing provider search.
- Provide a stacked, naturally scrolling layout on narrow screens.

## Non-Goals

- Redesign the provider catalog's visual styling or provider-card content.
- Change provider API routes, provider model-discovery semantics, or persistence behavior.
- Add new provider metadata, categories, filtering modes, or model-management features.
- Replace the existing configuration dialog with an inline settings form.
- Refactor unrelated settings fields or namespace behavior.

## Component Architecture

### ProviderBrowser

Create `frontend/src/lib/components/modals/ProviderBrowser.svelte` as a reusable Svelte component responsible for:

- Loading the provider catalog with `getProviders()`.
- Auto-loading models with the existing concurrency limit.
- Filtering providers by name, description, ID, model ID, and category.
- Rendering the Popular and Other sections.
- Refreshing one provider or all providers.
- Expanding a provider's model list and invoking a per-model application callback.
- Rendering loading, catalog-error, provider-error, empty-search, fallback, and no-model states.
- Exposing a provider-selection callback for opening connection configuration.

The component must not update application configuration directly.

### ProviderModal

Refactor `frontend/src/lib/components/modals/ProviderModal.svelte` into a modal shell and configuration form:

- Render `ProviderBrowser` when no provider is selected.
- Render the existing connection form when a provider is selected.
- Translate the browser's provider-selection callback into `startConnect(provider)`.
- Preserve existing close behavior, focus management, connection testing, API-key handling, model suggestions, and connection submission.
- Continue applying expanded-list model actions through the existing modal flow.

The existing modal dimensions and accessibility behavior remain unchanged.

### SettingsView

Update `frontend/src/lib/components/views/SettingsView.svelte` to:

- Replace the modal-opening header action with a scroll-and-focus action.
- Keep the provider panel mounted while switching settings namespace tabs.
- Render the provider panel beside the active namespace card on wide screens.
- Render the provider panel below the active namespace card below the `xl` breakpoint.
- Supply callbacks that apply a selected model to the active provider-capable namespace.
- Map the Server auth tokens tab to the existing `general` provider target.

The panel must not be destroyed when the active namespace changes.

## Layout

### Wide screens

At `xl` and wider, use a two-column grid:

- Left column: the active namespace settings card.
- Right column: the provider catalog card.
- Target an approximately 55/45 left-to-right split, with a minimum provider-column width near 28rem.
- Make the provider card viewport-aware and sticky within the scrolling settings content.
- Keep the provider panel header, search input, result count, and refresh action fixed while only the Popular and Other result sections scroll internally.

The provider panel must fill the previously unused right-side area without overlaying the settings card or causing the page-level container to gain an extra nested scrollbar.

### Narrow screens

Below `xl`:

- Stack the active settings card first and the provider panel second.
- Remove the viewport-fixed provider-panel height.
- Let the page's normal vertical scrolling contain the provider catalog.
- Preserve the current provider-card information density and allow action rows to wrap when space is constrained.

## Interaction Design

### Header action

`Browse provider presets` remains visible in the settings header. When activated:

1. Scroll the persistent provider panel into view.
2. Move focus to its search input.
3. Preserve keyboard focus styling.

### Provider search

Search continues to match provider name, description, ID, model IDs, and category in real time. Clearing search restores the complete catalog.

### Provider model actions

- `Connect` invokes the provider-selection callback and opens the existing connection configuration dialog.
- `Use <model>` invokes the immediate application callback.
- Immediate application writes the selected model and provider details to the active namespace, persists the namespace through the existing update path, and displays a success toast.
- The per-model action must not require a second configuration dialog.

The current auth tab continues to target the general provider configuration because it has no provider-specific namespace.

## Data Flow

1. `ProviderBrowser` mounts and loads `providers` from the provider catalog API.
2. The browser fans out existing per-provider model discovery requests.
3. Search and refresh state update local browser state only.
4. Selecting Connect emits a provider-selection callback to the host.
5. The modal host converts that callback into selected-provider configuration state.
6. Selecting Use invokes the host's model-application callback with the provider and model.
7. The host updates the active namespace and sends the same namespace update currently used by the modal flow.
8. A success toast confirms application, and the panel remains open for further browsing.

## Error Handling

Preserve all existing fail-open behavior:

- Provider catalog failure renders an error but leaves the page usable.
- Model-discovery failure renders provider-level feedback and may retain fallback models.
- Refresh remains disabled while requests are active.
- Empty search shows a clear-search action.
- An unavailable provider never blocks other provider cards.
- Applying a model must report success only when persistence succeeds and report an error when it fails.

## Accessibility

- The settings header action remains keyboard operable and clearly labeled.
- The provider panel's search input is focusable and has a visible focus ring.
- Provider card action labels continue to identify the provider, for example `Refresh models for <provider>`.
- Modal focus management and Escape behavior remain unchanged.
- The settings tablist, tabpanel, and scroll-and-focus behavior must remain axe-clean.
- The provider panel must not create a heading-level or landmark-level accessibility regression.

## Testing Plan

### ProviderBrowser unit tests

Cover:

- Catalog loading and per-provider model fan-out.
- Search across supported fields.
- Popular and Other filtering.
- Successful model counts and provider-level errors.
- Placeholder URL providers skipping model discovery.
- Per-provider refresh.
- Expanded model list and per-model `Use` actions.
- Provider-selection callback for Connect.
- Active namespace prop changes without remount-driven refetching by mounting the provider browser once without keying it on `targetNamespace`.

### ProviderModal regression tests

Update existing tests to verify:

- Browser output appears when the modal is open.
- Selecting Connect still opens the existing connection form.
- Submitting custom credentials still updates the active namespace.
- The existing model-application flow remains functional.

### SettingsView tests

Cover:

- Provider panel presence on every settings tab.
- The auth tab's general-provider target.
- Header action scrolling and focusing provider search.
- Settings card and provider panel rendering without replacing tab content.

### Accessibility and static checks

- Extend existing SettingsView axe coverage to include the persistent panel.
- Confirm no new tablist, tabpanel, dialog, or focus regression.

### Frontend verification gate

Run from `frontend/`:

```text
npm run check
npm test
npm run build
```

Visually inspect the provider panel in a wide settings viewport and a narrow stacked viewport, including long provider lists and the internal scroll region.

## Acceptance Criteria

- The settings page shows a persistent provider panel on the right at `xl` widths.
- The provider panel stacks below settings on smaller screens.
- The panel is visible on OCR, translation, transcription, and server-auth tabs.
- The header action scrolls to and focuses provider search.
- Provider search, model loading, refresh, Connect, and Use behavior match the current modal experience.
- Connect still opens the existing configuration dialog.
- Use applies a model immediately to the active namespace and shows confirmation.
- Existing modal tests and the full frontend validation gate pass.
