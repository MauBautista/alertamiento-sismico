// [T-5.05] ¿Este sitio / gabinete / sensor es de DEMOSTRACIÓN?
//
// El defecto que cierra, de la auditoría V1-COMERCIAL del 2026-09-02: la
// separación entre lo simulado y lo real vivía en el seed (`db/seeds/sim_fleet.sql`,
// con su aviso en mayúsculas de que jamás se aplica al entorno desplegado) y en el
// despliegue (`deploy/cloud/deploy.sh` solo siembra el de producción) — pero **no
// en la pantalla**, que es justo donde se hace la demo. En `make soc-local` un
// prospecto veía 21 sitios y 5 gabinetes con idéntico aspecto en el mapa y en la
// flota, de los cuales 20 y 4 no existen.
//
// DECISIÓN: se deriva del PREFIJO del código/serial, no de una columna nueva.
// La razón: la convención ya existe, ya está documentada en la cabecera del propio
// seed y ya la defiende un test (`edge/tests/test_fleet_sim.py`). Una columna sería
// una SEGUNDA verdad sobre el mismo hecho, y las dos podrían divergir — que es
// exactamente la clase de defecto que este repositorio persigue. El servidor
// publica el código (un hecho); cómo se rotula es de la presentación.
//
// Los patrones van ANCLADOS a propósito. Un `includes("sim")` marcaría como
// simulado un sitio real llamado `site-simon-01`, y equivocarse en esa dirección
// —rotular de demo un edificio con gente dentro— es peor que no rotular nada.

/**
 * Exactamente lo que generan los TRES seeds que no son inventario real, y nada más:
 *
 *   `db/seeds/sim_fleet.sql`    · 20 sitios del desarrollo local, JAMÁS en la nube
 *   `db/seeds/demo_red.sql`     · [T-7.11] los 3 de la red de demostración, que SÍ
 *                                 van a la nube y por eso son los que un cliente ve
 *   `db/seeds/e2e_harness.sql`  · [T-7.52] el sitio del arnés de los E2E móviles
 *
 * Los dos primeros comparten prefijo y por eso el segundo no obligó a cambiar la
 * regla —`site-sim-101` casa igual que `site-sim-001`—, que es la ventaja de
 * derivar del prefijo.
 *
 * ⚠️ El TERCERO sí obligó, y es la dirección de error que importa: `site-e2e-900`
 * no casaba con ningún patrón, así que la consola lo habría pintado como un
 * **edificio REAL**. El comentario de arriba dice que equivocarse en el otro
 * sentido es peor; éste es el peor de los dos y estuvo a punto de entrar.
 */
const PATRONES = [
  /^site-sim-\d+$/, // sitios     · site-sim-001 … 020 (local) y 101 … 103 (demo)
  /^gw-sim-\d+$/, //   gabinetes · gw-sim-0001 … 0004 y 0101 … 0103
  /^SIM\d+$/, //       sensores  · SIM001 … SIM020 y SIM101 … SIM103
  /^site-e2e-\d+$/, // arnés E2E · site-e2e-900 (sin gabinete: ver `guarda.sql`)
];

/**
 * `true` sólo para los identificadores de la flota simulada.
 *
 * Sin valor (undefined/null/"") devuelve `false`: la ausencia de dato no puede
 * inventar una marca, ni en un sentido ni en el otro.
 */
export function esDeDemostracion(codigoOSerial: string | null | undefined): boolean {
  if (codigoOSerial == null || codigoOSerial === "") return false;
  return PATRONES.some((p) => p.test(codigoOSerial));
}

/** Rótulo único, para que ninguna superficie pueda escribirlo distinto. */
export const ROTULO_DEMO = "DEMO";

/** Explicación única de la cinta (va al `title`). */
export const TITULO_DEMO = "Dato de demostración: este sitio no existe";

/**
 * [T-6.04] El nombre de un sitio para un contexto de TEXTO PLANO (`<option>`,
 * `title`, SVG), donde no cabe la cinta de `components/SiteLabel`: se le pega el
 * rótulo. Misma función que decide, mismo rótulo que se pinta.
 */
export function siteLabelText(name: string, code: string | null | undefined): string {
  return esDeDemostracion(code) ? `${name} · ${ROTULO_DEMO}` : name;
}
