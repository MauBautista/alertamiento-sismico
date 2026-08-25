// @ts-check
import { defineConfig } from "astro/config";

// `format: "file"` a propósito: URLs `.html` estables. El endpoint REST de S3
// con OAC no sirve `index.html` de subdirectorios, y así no hace falta ninguna
// CloudFront Function (decisión del plan §6: disponibilidad > URLs bonitas).
export default defineConfig({
  site: "https://takabailert.com",
  trailingSlash: "never",
  build: {
    format: "file",
    inlineStylesheets: "always",
  },
});
