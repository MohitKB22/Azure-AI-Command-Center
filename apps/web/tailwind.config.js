/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Dark-first command center palette with Azure blue/cyan accents.
        canvas: '#0b1220',
        surface: '#111a2b',
        elevated: '#16213a',
        border: '#22304d',
        azure: {
          50: '#e8f2ff',
          100: '#cde3ff',
          200: '#9cc7ff',
          300: '#63a6ff',
          400: '#3b8dfb',
          500: '#1a73e8',
          600: '#0f5bc4',
          700: '#0b4699',
          800: '#0a3773',
          900: '#092a57',
        },
        cyanx: '#22d3ee',
        ok: '#22c55e',
        warn: '#f59e0b',
        danger: '#ef4444',
      },
      fontFamily: {
        sans: ['"Segoe UI"', 'Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      boxShadow: {
        panel: '0 1px 0 0 rgba(255,255,255,0.04) inset, 0 8px 24px -12px rgba(0,0,0,0.6)',
      },
    },
  },
  plugins: [],
}
