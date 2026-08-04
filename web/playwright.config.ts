// E2E de navegador. Corre LOCAL contra el stack real:
//
//   1. `make soc-local`   (DB sembrada + API con /dev/token + worker + web :5173)
//   2. `npm run e2e`      (desde web/; requiere `npx playwright install chromium`)
//
// Sin `webServer` a propósito: arrancar aquí un vite suelto ocultaría a la API,
// al worker y al gabinete — estos specs existen para ver el sistema completo.
// En CI hay un job `workflow_dispatch` NO bloqueante (`.github/workflows/e2e.yml`):
// levanta el stack a mano y publica el reporte, pero no puede tumbar un merge —
// un e2e contra stack completo es demasiado frágil para ser un gate.
//
// [T-2.56] MATRIZ DE VIEWPORTS. Hasta ahora había UN viewport (el que un único
// test se ponía a mano) y por eso T-2.55 encontró tres sobrepuestos chocando y
// una consola sin una sola @media: nadie miraba la consola por debajo de 1440.
//
// Los tres tamaños NO son arbitrarios; cada uno cruza un breakpoint distinto:
//
//   1280×800   → justo EN el corte `--tk-bp-md`; dos columnas, `body` sin
//                scroll y además `@media (max-height: 800px)` activo (el caso
//                apretado de verdad: laptop de 14"). Aquí es donde el mapa se
//                cae a su piso de 280 px si alguien vuelve a robarle alto.
//   1440×900   → laptop grande, entre `md` y `lg`.
//   1920×1080  → `--tk-bp-xl`, el OBJETIVO del producto. Si algo se ve bien
//                SOLO aquí, la degradación está mal hecha, no la pantalla.
//
// Los números salen de los tokens `--tk-bp-*`; `layoutInvariants.test.ts` cruza
// esos tokens contra los literales de las @media (una custom property no es
// válida en el prelude de una @media — ver la nota en soc.css).
import { defineConfig, devices } from "@playwright/test";

/** Alto 800 EXACTO: `@media (max-height: 800px)` es inclusiva y debe activarse. */
export const VIEWPORTS = {
  "laptop-1280x800": { width: 1280, height: 800 },
  "laptop-1440x900": { width: 1440, height: 900 },
  "videowall-1920x1080": { width: 1920, height: 1080 },
} as const;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  // Un mismo stack local sirviendo tres navegadores a la vez produce fallos de
  // carrera que no son del layout (el worker y la DB son únicos). En serie.
  workers: 1,
  fullyParallel: false,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: process.env.PW_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
  },
  projects: Object.entries(VIEWPORTS).map(([name, viewport]) => ({
    name,
    use: { ...devices["Desktop Chrome"], viewport },
  })),
});
