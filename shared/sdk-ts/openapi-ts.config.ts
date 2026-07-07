import { defineConfig } from '@hey-api/openapi-ts';

// Genera el cliente fetch tipado a partir del contrato volcado por
// api/scripts/export_openapi.py. La salida vive en src/gen/ y es 100% generada
// (la revisa el drift gate de CI); lo escrito a mano cuelga de src/ (ws.ts, index.ts).
export default defineConfig({
  input: './openapi.json',
  output: {
    path: './src/gen',
    format: false,
    lint: false,
  },
  plugins: ['@hey-api/client-fetch'],
});
