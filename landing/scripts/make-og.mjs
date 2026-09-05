// Genera public/og-v3.png (1200×630) capturando la plantilla og.html del build
// con el Chromium de Playwright. Se corre a mano cuando cambia la tarjeta:
//   npm run build && node scripts/make-og.mjs
// El PNG se COMMITEA (public/) — el build de producción no lo regenera.
import { chromium } from "@playwright/test";
import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

const preview = spawn(
  "npm",
  ["run", "preview", "--", "--host", "127.0.0.1", "--port", "4322"],
  {
    stdio: "ignore",
  },
);
try {
  let listo = false;
  for (let i = 0; i < 40 && !listo; i++) {
    await delay(500);
    listo = await fetch("http://127.0.0.1:4322/og.html")
      .then((r) => r.ok)
      .catch(() => false);
  }
  if (!listo) throw new Error("el preview no levantó en 4322");

  const browser = await chromium.launch();
  const page = await browser.newPage({
    viewport: { width: 1200, height: 630 },
  });
  await page.goto("http://127.0.0.1:4322/og.html");
  await page.waitForFunction(() => document.fonts.status === "loaded");
  await page.waitForFunction(() =>
    Array.from(document.images).every((imagen) => imagen.complete),
  );
  await page.screenshot({ path: "public/og-v3.png" });
  await browser.close();
  console.log("public/og-v3.png generado (1200×630)");
} finally {
  preview.kill();
}
