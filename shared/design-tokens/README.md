# @takab/design-tokens

Única fuente de verdad del design system TAKAB (T-2.01, spec móvil §9).

- **`tokens.json`** — fuente de verdad: mapa plano `--tk-*` → valor.
- **`css/tokens.css`** — GENERADO (`npm run gen`), `:root` con las CSS custom
  properties para la consola web. `npm run check` = drift gate (lo corre la
  suite de web).
- **`src/index.ts`** — `cssVariables` (mapa exacto), `tokens` (vista
  estructurada para React Native), `toNumber()` y los **contratos semánticos**
  etiqueta→tono (`INCIDENT_SEVERITY`, `DERIVED_STATE_PILL`, `KIND_COLOR`;
  regla: desconocido ⇒ ámbar, jamás degradar a ok).

Consumo por dependencia `file:` (igual que `@takab/sdk`, TS crudo sin build):

- Web: `import "@takab/design-tokens/css/tokens.css"` (primero, en `main.tsx`)
  y los contratos desde `@takab/design-tokens`.
- Móvil (T-2.02+): `import { tokens, INCIDENT_SEVERITY } from "@takab/design-tokens"`.

Las `@font-face` y los `@import` de Google Fonts **no** viven aquí: dependen de
rutas de assets de cada app (Geist es local en `web/src/styles/fonts/`).

Para cambiar un token: editar `tokens.json` → `npm run gen` → commit de ambos.
La reconciliación web↔móvil (identidad de valores, 2026-07-15) está documentada
en `takab-docs/design/DESIGN-TOKENS-RECONCILIATION.md`.
