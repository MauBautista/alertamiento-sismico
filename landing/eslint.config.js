// Lint de los scripts TS/JS del workspace. Los .astro los cubre prettier
// (prettier-plugin-astro) + `astro check`; no se añade eslint-plugin-astro
// para mantener la superficie de dependencias mínima.
import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "dist/",
      ".astro/",
      "node_modules/",
      "test-results/",
      "playwright-report/",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.mjs", "**/*.js"],
    languageOptions: {
      globals: {
        console: "readonly",
        process: "readonly",
        Buffer: "readonly",
        fetch: "readonly",
        URL: "readonly",
        // make-og.mjs evalúa callbacks DENTRO del navegador (waitForFunction):
        document: "readonly",
        window: "readonly",
      },
    },
    rules: {
      "@typescript-eslint/no-require-imports": "off",
    },
  },
);
