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

/** Exactamente lo que genera `db/seeds/sim_fleet.sql`, y nada más. */
const PATRONES = [
  /^site-sim-\d+$/, // sitios     · site-sim-001 … site-sim-020
  /^gw-sim-\d+$/, //   gabinetes · gw-sim-0001 … gw-sim-0004
  /^SIM\d+$/, //       sensores  · SIM001 … SIM020
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

/** Rótulo único, para que las dos superficies no puedan escribirlo distinto. */
export const ROTULO_DEMO = "DEMO";
