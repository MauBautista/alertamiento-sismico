import { configDefaults, defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // B-6 (T-1.58): maplibre y el runtime de React van en chunks propios y
        // cacheables — el código de la app queda en ~275 kB. maplibre-gl pesa
        // ~1 MB él solo (tamaño intrínseco de la librería, ya aislado): el
        // límite del warning se sube SOLO para cubrir ese chunk conocido.
        manualChunks: {
          maplibre: ["maplibre-gl"],
          "vendor-react": ["react", "react-dom", "react-router"],
        },
      },
    },
    chunkSizeWarningLimit: 1100,
  },
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
      // @takab/sdk y @takab/design-tokens entran como symlink file: y Vite
      // resuelve por realpath.
      allow: [".", "../shared/sdk-ts", "../shared/design-tokens"],
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
