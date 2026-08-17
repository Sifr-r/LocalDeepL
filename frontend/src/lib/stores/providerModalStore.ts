import { writable } from 'svelte/store';

export type ProviderTargetNamespace = 'ocr' | 'translation' | 'transcription' | 'general';

export const isProviderModalOpen = writable<boolean>(false);
export const providerTargetNamespace = writable<ProviderTargetNamespace>('general');

export function openProviderModal(targetNamespace: ProviderTargetNamespace = 'general') {
  providerTargetNamespace.set(targetNamespace);
  isProviderModalOpen.set(true);
}

export function closeProviderModal() {
  isProviderModalOpen.set(false);
}
