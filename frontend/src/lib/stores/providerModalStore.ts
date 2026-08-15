import { writable } from 'svelte/store';

export const isProviderModalOpen = writable<boolean>(false);
export const providerTargetNamespace = writable<'ocr' | 'translation' | 'transcription' | 'general'>('general');

export function openProviderModal(targetNamespace: 'ocr' | 'translation' | 'transcription' | 'general' = 'general') {
  providerTargetNamespace.set(targetNamespace);
  isProviderModalOpen.set(true);
}

export function closeProviderModal() {
  isProviderModalOpen.set(false);
}
