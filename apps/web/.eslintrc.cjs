module.exports = {
  root: true,
  env: { browser: true, es2020: true, node: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', 'node_modules', '.eslintrc.cjs', 'playwright.config.ts', 'e2e'],
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  plugins: ['react-refresh'],
  rules: {
    'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    '@typescript-eslint/no-explicit-any': 'off',
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    'no-empty': ['error', { allowEmptyCatch: true }],
  },
  globals: {
    JSX: 'readonly',
  },
  overrides: [
    {
      // ui.tsx is the single import surface for shared primitives, so it also
      // exports `toneForStatus` and `useToast` alongside components. That costs
      // fast-refresh granularity in dev for this one file, which is a trade we
      // accept in exchange for one import path across every page.
      files: ['src/components/ui.tsx'],
      rules: { 'react-refresh/only-export-components': 'off' },
    },
    {
      files: ['src/**/*.test.{ts,tsx}', 'src/test/**'],
      env: { node: true },
    },
  ],
}
