/// <reference types="vitest/config" />
import { defineConfig } from "vite";
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
  },
});
