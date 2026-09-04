import type { MeActions, MeResponse } from "../auth/me";
import matriz from "../../../shared/fixtures/rbac-matrix.json";

/**
 * Fixtures de `/me` para los tests, **DERIVADAS** de la matriz real (T-5.28).
 *
 * Esto era una tabla escrita a mano que se declaraba «espejo SOLO PARA TESTS de
 * `api/src/takab_api/auth/matrix.py`» y pedía por escrito que se moviera con
 * ella. Nada lo comprobaba, y divergió en **trece celdas** (nueve de CCTV y
 * cuatro de privacidad), todas en la misma dirección: la matriz concede y el
 * espejo no.
 *
 * Lo que hay que recordar es el MODO de fallo: un permiso en `false` no relaja
 * una aserción — hace que el componente que lo gatea **no se monte**, y el test
 * pasa en verde sobre una población vacía. Esta vez no llegó a costar nada (esas
 * trece acciones casi no tienen consumidor aquí), y se descubrió de casualidad:
 * `soc_operator` —el rol principal de la consola— no tenía el permiso que
 * `T-5.12` necesitaba.
 *
 * Ahora no hay tabla: `shared/fixtures/rbac-matrix.json` lo genera
 * `api/scripts/export_rbac_matrix.py`, `api/tests/auth/test_rbac_fixture_es_la_
 * matriz.py` lo ata a la matriz por igualdad y `make drift` lo caza en CI. El
 * mismo patrón que `shared/fixtures/notify-channels.json`.
 *
 * La app real NUNCA consume esta tabla: nav y guards leen
 * `allowed_routes`/`allowed_actions` del servidor (`/me`).
 */

type MatrizRol = { routes: string[]; actions: Record<string, boolean> };

/** Rutas en su ORDEN estable: `landing.ts` toma la primera distinta de `/building`. */
export const ALL_ROUTES = matriz.route_order as readonly string[];

/** Todas las acciones en `false`. Se deriva del listado, no se enumera. */
export const ACTIONS_NONE: MeActions = Object.fromEntries(
  matriz.actions.map((a) => [a, false]),
) as unknown as MeActions;

export const TENANT_ID = "11111111-1111-1111-1111-111111111111";

/**
 * Roles con superficie WEB = los que la matriz deja entrar a alguna ruta, y
 * `MOBILE_ONLY_ROLES` los que no. Se derivan del mismo sitio: repartirlos a mano
 * era otra lista que podía quedarse atrás sin que nada lo dijera.
 */
const ROLES = Object.keys(matriz.roles).sort() as RoleName[];

export type RoleName =
  | "takab_superadmin"
  | "takab_support"
  | "tenant_admin"
  | "soc_operator"
  | "gov_operator"
  | "inspector"
  | "building_admin"
  | "brigadista"
  | "security_guard"
  | "occupant";

const rolDe = (r: string): MatrizRol => (matriz.roles as Record<string, MatrizRol>)[r];

export const WEB_ROLES = ROLES.filter((r) => rolDe(r).routes.length > 0);
export const MOBILE_ONLY_ROLES = ROLES.filter((r) => rolDe(r).routes.length === 0);

function me(role: RoleName): MeResponse {
  const fila = rolDe(role);
  return {
    sub: `sub-${role}`,
    tenant_id: TENANT_ID,
    role,
    site_scope: "*",
    // La superficie sale de la matriz igual que todo lo demás: un rol sin ruta
    // web es de campo. Escribirla aparte volvía a abrir la puerta a la deriva.
    surface: fila.routes.length > 0 ? "web" : "mobile",
    allowed_routes: [...fila.routes],
    allowed_actions: { ...ACTIONS_NONE, ...(fila.actions as unknown as MeActions) },
  };
}

export const ME_FIXTURES: Record<RoleName, MeResponse> = Object.fromEntries(
  ROLES.map((r) => [r, me(r)]),
) as Record<RoleName, MeResponse>;
