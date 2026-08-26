// Captura la consola SOC REAL corriendo en local (make soc-local) con datos de
// demostración, para la sección «La consola» de la landing (PENDIENTES §3.6).
// Requiere el stack vivo en :5173/:8000/:9100. Uso:
//   node scripts/capturas-consola.mjs
// Deja los PNG en src/assets/img/ (astro:assets los procesa a webp en build).
import { chromium } from "@playwright/test";
import { setTimeout as delay } from "node:timers/promises";

const BASE = "http://127.0.0.1:5173";

// Estímulo: un sismo de demostración para que la consola tenga un incidente vivo.
await fetch("http://127.0.0.1:9100/quake", { method: "POST" }).catch(() => {
  console.warn("aviso: /quake no respondió (¿stack caído?); capturo en reposo");
});
await delay(12_000); // deja que el incidente fluya gabinete→nube→consola

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1600, height: 1000 },
  deviceScaleFactor: 1.5,
});

await page.goto(BASE + "/");
// Login de desarrollo (POST /dev/token · solo local): rol soc_operator.
await page.waitForSelector(".soc-dev-panel");
await page.click(".soc-dev-panel button[type=submit]");
await page.waitForURL("**/console", { timeout: 30_000 });

// El banner de consentimiento (con su sello «TEXTO PROVISIONAL») no debe
// salir en la captura pública: se acepta como haría el operador. Renderiza
// ASÍNCRONO tras la navegación — hay que esperarlo, no solo mirarlo.
const acepto = page.getByRole("button", { name: /acepto este aviso/i });
try {
  await acepto.waitFor({ state: "visible", timeout: 8_000 });
  await acepto.click();
  await acepto.waitFor({ state: "hidden", timeout: 8_000 });
} catch {
  console.warn("aviso: banner de consentimiento no apareció (¿ya aceptado?)");
}
await delay(6_000); // mapa (MapLibre) + WS + datos

await page.screenshot({ path: "src/assets/img/consola-livewall.png" });
console.log("✓ consola-livewall.png");

await page.goto(BASE + "/fleet");
await delay(4_000);
await page.screenshot({ path: "src/assets/img/consola-flota.png" });
console.log("✓ consola-flota.png");

await browser.close();
