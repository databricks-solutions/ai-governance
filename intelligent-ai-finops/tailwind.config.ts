import type { Config } from 'tailwindcss';

// Tokens live in src/tokens.css as CSS custom properties (the single source of
// truth, copied verbatim from BUILD-SPEC §3). Tailwind maps to those vars so the
// two can never drift. Colour discipline (§3): `lava` is ONLY ever cost or a
// routing decision; primary actions use `ink`.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: 'var(--paper)',
        'paper-2': 'var(--paper-2)',
        card: 'var(--card)',
        'card-2': 'var(--card-2)',
        line: 'var(--line)',
        'line-hi': 'var(--line-hi)',
        ink: 'var(--ink)',
        'ink-2': 'var(--ink-2)',
        'ink-3': 'var(--ink-3)',
        lava: 'var(--lava)',
        'lava-wash': 'var(--lava-wash)',
        'lava-line': 'var(--lava-line)',
        plum: 'var(--plum)',
        'plum-wash': 'var(--plum-wash)',
        amber: 'var(--amber)',
        'amber-wash': 'var(--amber-wash)',
        moss: 'var(--moss)',
        'moss-wash': 'var(--moss-wash)',
        'dbx-blue': 'var(--dbx-blue)',
        'dbx-blue-wash': 'var(--dbx-blue-wash)',
      },
      borderRadius: {
        xl: 'var(--r-xl)',
        lg: 'var(--r-lg)',
        DEFAULT: 'var(--r)',
        pill: '999px',
      },
      boxShadow: {
        lift: 'var(--lift)',
        'lift-hi': 'var(--lift-hi)',
        'lift-float': 'var(--lift-float)',
        'lift-3d': 'var(--lift-3d)',
        'lift-3d-hi': 'var(--lift-3d-hi)',
        'lift-winner': 'var(--lift-winner)',
      },
      fontFamily: {
        display: 'var(--f-display)',
        body: 'var(--f-body)',
        data: 'var(--f-data)',
      },
      transitionTimingFunction: {
        soft: 'cubic-bezier(.2,.7,.3,1)',
      },
    },
  },
  plugins: [],
} satisfies Config;
