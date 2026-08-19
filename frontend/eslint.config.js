import js from '@eslint/js';
import svelte from 'eslint-plugin-svelte';
import globals from 'globals';
import ts from 'typescript-eslint';

export default ts.config(
  js.configs.recommended,
  ...ts.configs.recommended,
  ...svelte.configs['flat/recommended'],
  {
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node
      }
    }
  },
  {
    files: ['**/*.svelte'],
    languageOptions: {
      parserOptions: {
        parser: ts.parser
      }
    },
    rules: {
      'no-useless-assignment': 'off'
    }
  },
  {
    // Underscore-prefixed bindings (e.g. ``_obj``, ``_url``) are
    // conventional placeholders for intentionally-unused parameters
    // — the polyfills in ``src/__tests__/setup.ts`` and event stubs
    // across the components rely on this pattern. Letting the linter
    // accept them keeps the rule useful for the genuine cases without
    // producing noise on deliberate no-op implementations.
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_'
        }
      ]
    }
  },
  {
    ignores: ['build/', '.svelte-kit/', 'dist/']
  }
);
