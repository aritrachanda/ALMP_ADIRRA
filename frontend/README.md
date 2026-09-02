# ADIRRA frontend (Vue 3 + Quasar + TypeScript + Vite)

The target and only UI for ADIRRA. See the repo root [README.md](../README.md) for full setup
instructions (Postgres governance database, Python backend, etc.) and
[AGENTS.md](../AGENTS.md) for dev commands and gotchas.

## Quick reference

```bash
npm install
npm run dev          # Vite dev server, http://localhost:9000 — requires the FastAPI backend running
npm run test         # vitest run
npx vue-tsc --noEmit # type-check
npm run lint         # eslint . --ext .ts,.vue
npm run build        # lint + vue-tsc + vite build — the full CI gate
```

Conventions (component/store patterns, styling tokens, test layout) are documented in
[.github/instructions/frontend.instructions.md](../.github/instructions/frontend.instructions.md).
