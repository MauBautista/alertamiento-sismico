import { defineConfig } from "@playwright/test";

// E2E manual de la landing (`make landing-e2e`): capturas en los 4 breakpoints
// del brief + axe. No es gate de CI (patrón e2e.yml del repo: lo flaky no
// bloquea); la evidencia se archiva en tests/e2e/evidencia/.
export default defineConfig({
  testDir: "./e2e",
  outputDir: "../test-results",
  timeout: 60_000,
  use: {
    baseURL: "http://127.0.0.1:4321",
  },
  webServer: {
    command: "npm run build && npm run preview -- --host 127.0.0.1 --port 4321",
    url: "http://127.0.0.1:4321",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
