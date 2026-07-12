import { configDefaults, defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // La API no monta CORS: en dev todo va por el proxy /api → :8000. El prefijo
    // además evita la colisión de paths SPA/API (p.ej. /fleet existe en ambos).
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        ws: true, // upgrade del WS live (/api/ws → :8000/ws)
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
    fs: {
      // @takab/sdk entra como symlink file: y Vite resuelve por realpath.
      allow: [".", "../shared/sdk-ts"],
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./vitest.setup.ts",
    // e2e/ es de Playwright (M-7): sus specs importan @playwright/test y corren
    // contra el stack real de `make soc-local`, no bajo jsdom.
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
