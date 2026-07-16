# Reconciliación de design tokens — web ↔ móvil (T-2.01 · 2026-07-15)

> Mandato de la spec móvil (`design/app/ESPECIFICACION-APP-MOVIL.md` §9.2): extraer los tokens
> del diseño móvil, reconciliarlos contra los de la consola y documentar el resultado — sin
> unificar en silencio. Este documento ES esa reconciliación.

## 1. Veredicto: IDENTIDAD — cero conflictos de valor

Verificado el 2026-07-15 con `diff` directo entre las dos fuentes que existían:

| Fuente | Rol |
|---|---|
| `web/src/styles/colors_and_type.css` (`:root`, 96 variables `--tk-*`) | tokens vivos de la consola en producción |
| `takab-docs/design/app/colors_and_type.css` | tokens del design canvas móvil |

Resultado: **los 96 valores eran idénticos byte a byte**. La única diferencia era un comentario
(línea 116, el ejemplo del "data hero": la copia del canvas ya decía `(PGA 0.150g)` tras la
corrección de honestidad del canvas en `977f861`; la copia web aún decía el ejemplo viejo con
magnitud — comentario, no valor). **No hubo ningún conflicto que arbitrar: el mapeo es 1:1 y el
valor unificado es el que ya estaba en producción.** La consola NO cambió de apariencia.

## 2. Fuente única resultante

```
shared/design-tokens/
├── tokens.json          ← FUENTE DE VERDAD (mapa plano --tk-* → valor, 96 vars)
├── css/tokens.css       ← GENERADO (npm run gen) — :root para la consola
├── src/index.ts         ← cssVariables + tokens (vista TS para React Native)
│                          + contratos semánticos + toNumber()
└── scripts/gen-css.mjs  ← generador determinista + drift gate (npm run check)
```

Consumo por dependencia `file:` (mismo patrón que `@takab/sdk`, TS crudo sin build):

- **Web:** `main.tsx` importa `@takab/design-tokens/css/tokens.css` ANTES de los estilos
  locales. `web/src/styles/colors_and_type.css` conserva **solo** lo dependiente de assets de
  la app (la `@font-face` de Geist local y los `@import` de Google Fonts) y las clases de tipo
  semánticas (`.tk-h1`…`.tk-link`), que consumen las variables del paquete.
- **Móvil (T-2.02+):** `import { tokens, INCIDENT_SEVERITY } from "@takab/design-tokens"`.

## 3. Qué queda fuera del paquete (deliberado)

- **Fuentes:** `@font-face`/`@import` dependen de rutas de assets por app (Geist vive en
  `web/src/styles/fonts/`; en móvil se empaqueta con expo-font). El paquete solo publica los
  **font stacks** (`--tk-font-*`).
- **Clases CSS** (`.tk-*` de tipografía, `.soc-*` de componentes): son el *rendering* web de los
  tokens; React Native usa la vista TS.
- **`takab-docs/design/app/colors_and_type.css`:** queda como **artefacto de diseño congelado**
  del canvas (los mockups lo cargan standalone). No lo consume ninguna app. Un token nuevo
  aterriza PRIMERO en `tokens.json`; el canvas se sincroniza al tocar los mockups.

## 4. Contratos semánticos compartidos (spec §9.3/§9.4)

El mapeo etiqueta→tono dejó de vivir en componentes web y ahora es dato del paquete, para que
web y móvil resuelvan idéntico:

| Export | Contrato | Consumidor web actual |
|---|---|---|
| `INCIDENT_SEVERITY` | `incidents.severity` → `{kind, label}` (critical→crit/CRÍTICO, warning→warn/ADVERTENCIA, watch→warn/VIGILANCIA, info→ok/NORMAL) | `SevTag.tsx` |
| `UNKNOWN_SEVERITY_KIND` | desconocida ⇒ `warn` y texto crudo — jamás degradar a NORMAL | `SevTag.tsx` |
| `DERIVED_STATE_PILL` | `gateways.derived_state` → tono (OPERATIVO→ok, DEGRADADO→warn, SIN ENLACE→crit) | `SiteCard.tsx` |
| `UNKNOWN_DERIVED_STATE_KIND` | desconocido ⇒ `warn`, nunca ok | `SiteCard.tsx` |
| `KIND_COLOR` | tono → token de color del semáforo | móvil (T-2.05+) |

## 5. Guardias contra el drift

- **`npm run check`** en el paquete: el CSS committeado debe regenerarse idéntico de
  `tokens.json` (lo corre la suite de web en `web/src/designTokens.test.ts`).
- **Tests de paridad** (`web/src/designTokens.test.ts`, 19 tests): css ≡ json; **anclas de
  identidad visual** con los valores pre-migración literales (#FF5252, #FFC107, #00E676,
  #00BFFF, #1A3E62, …) — si un ancla cambia, es un cambio visual deliberado que debe pasar
  por decisión explícita; contratos semánticos congelados.
- Tests existentes de `SevTag`/`SiteCard` verifican que el refactor no movió clases ni labels.

## 6. Evidencia de "sin cambio visual" (T-2.01, 2026-07-15)

- Suite completa de web: **576/576 en verde** (antes 557; +19 de paridad).
- ESLint limpio; `vite build` OK; las variables están presentes en el bundle
  (`--tk-status-critical: #FF5252` en `dist/assets/index-*.css`).
- El paquete no introduce dependencias nuevas de runtime (cero deps).
