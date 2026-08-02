/**
 * LocalDeepL Application Main Entry Point
 * 
 * Responsible for instantiating the root Svelte 5 component tree into the DOM shell,
 * initializing CSS imports, and establishing initial reactive app store subscriptions.
 * 
 * @module main
 */

import { mount } from 'svelte';
import './app.css';
import App from './App.svelte';

/**
 * Ensures the target DOM mount point element is present before attaching the application.
 */
const targetElement = document.getElementById('app');

if (!targetElement) {
  throw new Error(
    '[LocalDeepL Error] Fatal mounting failure: HTML template is missing target "#app" container element.'
  );
}

/**
 * Instantiates and mounts the main Svelte 5 root application instance.
 * Using Svelte 5 `mount(Component, options)` API.
 */
export const app = mount(App, {
  target: targetElement,
});

/**
 * Log initialization event for diagnostics during development.
 */
if (import.meta.env.DEV) {
  console.log('[LocalDeepL] Single Page Application successfully initialized and mounted to target container.');
}
