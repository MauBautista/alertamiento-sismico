// Smoke E2E de navegador (M-7). Corre LOCAL contra el stack real:
//
//   1. `make soc-local`   (DB sembrada + API con /dev/token + worker + web :5173)
//   2. `npm run e2e`      (desde web/; requiere `npx playwright install chromium`)
//
// Sin `webServer` a propósito: arrancar aquí un vite suelto ocultaría a la API,
// al worker y al gabinete — el smoke existe para ver el sistema completo. No hay
// job de CI (el stack es pesado en Actions); queda documentado como paso manual
// del cierre de fase. Mejora futura anotada: job `workflow_dispatch` no-bloqueante.
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: {
    baseURL: process.env.PW_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
  },
});
