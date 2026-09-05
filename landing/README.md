# Landing pública de TAKAB Ailert — takabailert.com

Workspace **Astro estático** autocontenido (sin dependencia de `shared/design-tokens`:
la identidad de la landing es propia — dirección v3 «Comando cinematográfico»,
ver `PRODUCT.md` y el contrato de dirección en
`src/layouts/Base.astro`). Node 22 (`.nvmrc`).

## Comandos

| Comando                                       | Qué hace                                                                                                                        |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `npm run dev`                                 | Servidor de desarrollo                                                                                                          |
| `npm run build`                               | Build a `dist/` (páginas `.html`, assets hasheados en `_astro/`)                                                                |
| `npm run preview`                             | Sirve `dist/` (es el staging: no hay otro)                                                                                      |
| `npm run lint` / `format:check` / `typecheck` | Los tres gates de calidad (espejados en `make lint` y CI)                                                                       |
| `npm run test`                                | Build + suite de contenido sobre `dist/` (cadenas obligatorias/prohibidas, orígenes, presupuestos) — el gate determinista de CI |
| `npm run e2e`                                 | Playwright: capturas 360/768/1280/1920 + axe + teclado + reduced-motion (evidencia en `tests/e2e/evidencia/`)                   |
| `npm run audit`                               | Lighthouse CI local con budgets (LCP<2 s 4G emulado, CLS<0.1) — NO corre en CI (flake)                                          |

> Si `audit` dice «Chrome installation not found»: no hay Chrome del sistema; apúntalo al de
> Playwright — `CHROME_PATH=$(find ~/.cache/ms-playwright -path '*chromium*/chrome-linux64/chrome' | sort | tail -1) npm run audit`.
> Referencia medida V3 end-to-end (2026-09-05, 3 corridas locales): LCP máximo 1.28 s · CLS 0 · TBT máximo 24 ms · Perf 100 · A11y 100.

Desde la raíz del repo: `make landing-preview` · `landing-e2e` · `landing-audit` ·
`landing-deploy` (este último con guardas; runbook en `deploy/landing/README.md`).

## Perímetro del contenido (no negociable)

Cada afirmación lleva su fuente en un comentario (`<!-- fuente: … -->`) contra
`takab-docs/CONSULTA-LEGAL-TAKAB.md` y `takab-docs/ENTREGA-Y-ACEPTACION-TAKAB.md`.
La suite (`tests/contenido.test.mjs`) hace bloqueantes las reglas: deslinde SASMEX y
declaración del dominio remitente presentes (el sitio es evidencia del caso SES),
**cero cifras medidas** (decisión 2026-08-25), cero normas, cero badges de tiendas,
cero orígenes externos.

## Fuentes (woff2)

Subsets auto-hosteados y COMMITEADOS en `src/assets/fonts/` (≈32 KB los cuatro).
Regenerar solo si cambian las familias: `bash scripts/build-fonts.sh` (usa `uvx`
para fonttools; descarga de github.com/google/fonts en build-time, jamás en runtime).

## Tarjeta OG

`public/og-v3.png` se genera con `npm run build && node scripts/make-og.mjs`
(captura `og.html` con el Chromium de Playwright) y se commitea. Si cambia el
diseño de la tarjeta, súbele la versión al nombre (`og-v4.png`) y actualiza
`Base.astro`: el fichero no es immutable pero los rastreadores cachean agresivo.
`public/og-v2.png` se conserva únicamente para continuidad de caché y rollback de
la versión anterior; ninguna página v3 lo referencia.

## Consola pública

La landing usa una representación editorial responsive de los campos de la sala
de operaciones. La captura histórica `consola-livewall.png` no se sirve: contenía
un sitio de desarrollo, estados degradados y cifras medidas fuera de contexto.
Sólo se recapturará cuando exista una flota sana y el encuadre pueda publicarse sin
contradecir el perímetro comercial.

## Favicon

`public/favicon.png` y `public/apple-touch-icon.png` son derivados optimizados del
isotipo negativo entregado en `img/Logos Finales/isotipo_negativo.png`. Se generan
con Sharp a 64 px y 180 px, respectivamente; no contienen redibujo ni alteración de
marca.

## Contacto

`src/config.ts`: `CONTACTO_EMAIL` (contacto@takabailert.com) y `WHATSAPP_URL`
(vacío = el botón no se renderiza; poner la URL `https://wa.me/52…` cuando
Mauricio confirme el número).
