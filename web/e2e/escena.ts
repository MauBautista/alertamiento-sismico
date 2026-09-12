// [T-7.04] CONTROL DEL ESCENARIO del stack local (`make soc-local`).
//
// «Nada se encima» sólo se puede afirmar CON la alerta en pantalla, no con la
// consola en reposo (PLAN-PROTOTIPO-FUNCIONAL §F0). Hasta esta ficha
// `layout.spec.ts` medía «los que estén» y declaraba que la alerta «puede no
// estar»: un test que tolera la ausencia del caso para el que existe no mide
// ese caso. Aquí la escena se FUERZA por la misma ruta que un sismo real:
//
//   alert  → POST :9100/sasmex (cierre del contacto seco del WR-1 simulado)
//            ⇒ evento → bridge → motor de incidentes ⇒ incidente
//            `trigger='sasmex'` crítico ⇒ escena `alert` (`scene.ts`: SASMEX
//            autoriza). Se espera al INCIDENTE, no al contacto: la consola sólo
//            ve incidentes.
//   normal → POST :9100/sasmex/clear + cierre de todo incidente no cerrado en la
//            DB local. No hay endpoint para cerrar incidentes (el cierre lo hace
//            el ciclo de vida del motor, a propósito), así que el estado de la
//            base de DEMOSTRACIÓN se fija con `psql`, la misma herramienta con la
//            que `make demo-db` la siembra. Jamás contra otra DSN que la del
//            arnés, y jamás contra un Pi real.
//
// Y ENTRE una alerta y la siguiente hay que RE-ARMAR el gabinete: la alerta
// SASMEX queda ENCLAVADA en el edge (semántica real del WR-1, gate #3) y con el
// enclave puesto un segundo cierre del contacto no publica evento — el motor de
// reglas ya está en alerta. Medido: el segundo `/sasmex` de una corrida no abría
// incidente en 90 s. Lo que un operador hace en el panel LAN —CERRAR ALERTA—
// aquí es `POST :8080/api/reset`, sin PIN porque el arnés corre en `dev_mode`.
//
// No hay skip: si el arnés no responde, el barrido no puede afirmar nada y el
// test FALLA diciendo qué faltó (TRASPASO-SESION: un fallback no puede ser `ok`).
//
// No es un spec: Playwright sólo recoge `*.spec.ts`.
import { execFileSync } from "node:child_process";

import { expect, type Page } from "@playwright/test";

/** Escenas que el arnés sabe forzar hoy. */
export type ForcedScene = "normal" | "alert";

/**
 * Escenas que la ficha pide y que NO existen todavía. Se declaran con su razón
 * para que el barrido las exija el día que lleguen, en vez de fingirlas: una
 * `review` inyectada a mano en el DOM mediría un marcado que nadie renderiza.
 */
export const PENDING_SCENES: Readonly<Record<string, string>> = {
  review:
    "la escena `review` llega en F3 (T-7.16): hoy no está en `features/scene/scene.ts` " +
    "ni hay estímulo del arnés que la produzca; se barrerá cuando exista, no antes",
};

const CONTROL_URL = process.env.PW_CONTROL_URL ?? "http://127.0.0.1:9100";
/** Panel LAN del gabinete SIMULADO (`demo/soc_local.py --dashboard-port`). */
const PANEL_URL = process.env.PW_PANEL_URL ?? "http://127.0.0.1:8080";
const DB_DSN = process.env.PW_DB_DSN ?? "postgresql://takab:takab_dev@127.0.0.1:5433/takab";
const API_URL = `${process.env.PW_BASE_URL ?? "http://localhost:5173"}/api`;
/** Tenant del login dev (`pages/LoginPage.tsx` → `DEV_TENANT_DEFAULT`). */
const DEV_TENANT = "d0000000-0000-0000-0000-000000000001";

interface IncidentRow {
  incident_id: string;
  trigger: string | null;
  severity: string;
  state: string;
}

async function devToken(): Promise<string> {
  const res = await fetch(`${API_URL}/dev/token`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ role: "takab_superadmin", tenant_id: DEV_TENANT }),
  });
  if (!res.ok) {
    throw new Error(`POST ${API_URL}/dev/token → ${res.status}: ¿corre \`make soc-local\`?`);
  }
  const body = (await res.json()) as { id_token: string };
  return body.id_token;
}

async function openIncidents(token: string): Promise<IncidentRow[]> {
  const res = await fetch(`${API_URL}/incidents?state=open`, {
    headers: { authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`GET ${API_URL}/incidents?state=open → ${res.status}`);
  const body = (await res.json()) as { items: IncidentRow[] };
  return body.items;
}

const LOOPBACK = /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/;

async function post(base: string, path: string, why: string): Promise<void> {
  if (!LOOPBACK.test(base)) {
    throw new Error(`${base} no es loopback: ${why} sólo se manda al gabinete SIMULADO`);
  }
  const url = `${base}${path}`;
  const res = await fetch(url, { method: "POST" }).catch((e: unknown) => {
    throw new Error(`POST ${url} sin respuesta (${String(e)}): el gabinete simulado no está`);
  });
  if (!res.ok) throw new Error(`POST ${url} → ${res.status} (${why})`);
}

/** El estímulo del gabinete simulado (`demo/gabinete.py`): el contacto del WR-1. */
async function poke(path: "/sasmex" | "/sasmex/clear"): Promise<void> {
  await post(CONTROL_URL, path, "cerrar/abrir el contacto seco");
}

/** CERRAR ALERTA en el panel LAN: desenclava el edge para que el siguiente flanco cuente. */
async function rearm(): Promise<void> {
  await post(PANEL_URL, "/api/reset", "re-armar la alerta enclavada");
}

/** Cierra en la DB local todo incidente que no esté cerrado; devuelve cuántos. */
function closeOpenIncidents(): number {
  let out: string;
  try {
    out = execFileSync(
      "psql",
      [
        DB_DSN,
        "-tAX",
        "-c",
        "UPDATE incidents SET state = 'closed', closed_at = COALESCE(closed_at, now()) " +
          "WHERE state <> 'closed'",
      ],
      { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
    );
  } catch (e) {
    throw new Error(
      `no se pudo cerrar los incidentes con psql contra ${DB_DSN}: ${String(e)} ` +
        "(hace falta el cliente psql y la DB del arnés en :5433)",
    );
  }
  const tag = /UPDATE (\d+)/.exec(out);
  return tag === null ? 0 : Number(tag[1]);
}

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

async function waitFor<T>(
  what: string,
  probe: () => Promise<T | null>,
  timeoutMs: number,
  everyMs = 1_000,
): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const got = await probe();
    if (got !== null) return got;
    if (Date.now() >= deadline) {
      throw new Error(`tras ${timeoutMs / 1000}s sigue sin haber ${what}`);
    }
    await sleep(everyMs);
  }
}

const isAlert = (i: IncidentRow): boolean => i.trigger === "sasmex" && i.severity === "critical";

/**
 * Deja el stack local en la escena pedida y devuelve una línea con lo que hizo
 * (para adjuntarla al reporte). Idempotente: forzar dos veces la misma escena
 * no dispara dos alertas.
 */
export async function forceScene(scene: ForcedScene): Promise<string> {
  const token = await devToken();
  if (scene === "alert") {
    const already = (await openIncidents(token)).find(isAlert);
    if (already !== undefined) return `alerta ya en pantalla (incidente ${already.incident_id})`;
    // Re-armar y abrir ANTES de cerrar: con el enclave puesto o el contacto ya
    // cerrado, un segundo cierre no produce flanco y el edge no publica nada.
    await rearm();
    await poke("/sasmex/clear");
    await sleep(1_000);
    await poke("/sasmex");
    const incident = await waitFor(
      "un incidente SASMEX crítico abierto (edge → bridge → motor de incidentes)",
      async () => (await openIncidents(token)).find(isAlert) ?? null,
      90_000,
    );
    return `SASMEX forzado por :9100 → incidente ${incident.incident_id}`;
  }
  // El gabinete también vuelve a reposo: una consola en `normal` con el panel
  // LAN todavía en ALERTA no es el reposo que se quiere medir.
  await poke("/sasmex/clear");
  await rearm();
  const closed = closeOpenIncidents();
  await waitFor(
    "cero incidentes abiertos",
    async () => ((await openIncidents(token)).length === 0 ? true : null),
    30_000,
  );
  return `contacto WR-1 abierto, gabinete re-armado y ${closed} incidente(s) cerrado(s) en la DB local`;
}

/**
 * CONTROL POSITIVO: la pantalla declara la escena forzada. Sin esto, un barrido
 * «sin solapes» bajo alerta podría estar midiendo la consola en reposo — que es
 * exactamente lo que este archivo dejó de tolerar.
 */
export async function expectScene(page: Page, scene: ForcedScene, path: string): Promise<void> {
  await expect(
    page.getByTestId("scene-strip"),
    `la franja de escena de ${path} no declara "${scene}": la escena no se forzó de verdad`,
  ).toHaveAttribute("data-scene", scene, { timeout: 15_000 });
  if (scene !== "alert") return;
  if (path === "/console") {
    // En el wall la alerta es la TARJETA anclada al escenario (`WALL_ROUTE`).
    const banner = page.getByTestId("alert-banner");
    await expect(banner, "sin tarjeta de alerta en el wall bajo escena alert").toBeVisible();
    await expect(banner).toHaveAttribute("data-authorizes", "true");
    return;
  }
  // En las otras cinco, su ECO en la franja del shell.
  const line = page.getByTestId("scene-alert");
  await expect(line, `sin línea de alerta en la franja de ${path}`).toBeVisible();
  await expect(line).toHaveAttribute("data-kind", "alert");
}
