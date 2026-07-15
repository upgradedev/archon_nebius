import tseslint from 'typescript-eslint'

export default tseslint.config(
  {
    ignores: ['dist/**', 'node_modules/**', 'playwright-report/**', 'test-results/**'],
  },
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    rules: {
      // The API adapter intentionally normalises dynamic JSON from the backend.
      '@typescript-eslint/no-explicit-any': 'off',
    },
  },
)
