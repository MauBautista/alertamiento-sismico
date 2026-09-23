import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createUserUsersPost,
  deleteUserUsersUsernameDelete,
  listUsersUsersGet,
  resendInvitationUsersUsernameResendInvitationPost,
  resetPasswordUsersUsernameResetPasswordPost,
  updateUserUsersUsernamePatch,
} from "@takab/sdk";
import type { UserCreate, UserOut, UserPage, UserUpdate } from "@takab/sdk";

/** Lo que se escribe desde ESTA consola se ve al instante: se invalida al escribir. */
const USERS_FRESH_MS = 60_000;

/**
 * Sin relectura tras este umbral la lista pasa a DATOS RETENIDOS.
 *
 * No es un dato de campo, pero SÍ envejece: los roles se reparten desde varias
 * sesiones y desde la propia consola de AWS. Una lista de cinco minutos
 * presentada como viva es exactamente lo que veta la regla de oro 7 — y aquí lo
 * que envejece es quién tiene acceso al sistema.
 */
export const USERS_STALE_MS = 300_000;

/**
 * [A-112 bis · T-8.09] …y por eso se RELEE. Decía «se recarga al escribir, no en
 * un poll», pero el umbral de arriba existe precisamente porque el directorio
 * cambia desde OTRAS sesiones: sin cadencia (y con `refetchOnWindowFocus: false`)
 * la tarjeta rotulaba «DATOS RETENIDOS» a los 5 min con el sistema sano. Dos
 * oportunidades antes del umbral; una relectura fallida suelta no rotula.
 */
export const USERS_REFRESH_MS = 120_000;

/**
 * [A-108] Qué se intentaba: el mismo código HTTP significa cosas distintas según
 * la operación. El 409 del ALTA es «ese correo ya existe»; el de la BAJA es «no
 * puedes darte de baja a ti mismo», y se leía como el primero.
 */
export type UserOperation = "list" | "create" | "update" | "delete" | "action";

/**
 * [A-106] Tope de páginas que se siguen en UNA lectura. Cognito pagina de 60 en
 * 60 como mucho y NO filtra por atributos custom, así que la página de un cliente
 * puede venir vacía con más detrás. 20 páginas son ~1 000 identidades: de sobra
 * para el piloto, y si se alcanza la tarjeta lo DICE (`truncated`) en vez de
 * presentar un corte como la lista entera.
 */
export const USERS_MAX_PAGES = 20;

export function userErrorMessage(
  status: number,
  op: UserOperation = "list",
  detail: string | null = null,
): string {
  if (status === 409 && op !== "create") {
    return `CONFLICTO · ${detail ?? "el servidor rechazó el cambio (HTTP 409)"}`;
  }
  switch (status) {
    case 400:
      return "DATOS INVÁLIDOS · revisa el alcance por estación y el tenant destino.";
    case 403:
      return "SIN PERMISO · tu rol no reparte identidades, o el rol pedido es de plataforma.";
    case 404:
      return "NO ENCONTRADO · el usuario no existe o pertenece a otro cliente.";
    case 409:
      return "YA EXISTE · ese correo ya tiene una cuenta.";
    case 422:
      return "DATOS INVÁLIDOS · revisa el correo, el rol y el alcance.";
    case 502:
      return "DIRECTORIO NO RESPONDE · Cognito rechazó la operación. Nada cambió.";
    case 503:
      return "DIRECTORIO NO DISPONIBLE · no hay pool de identidades configurado.";
    default:
      return `La operación sobre /users falló (HTTP ${status})`;
  }
}

/** El `detail` textual de un error de FastAPI, si lo hay. */
function detailOf(error: unknown): string | null {
  if (typeof error !== "object" || error === null) return null;
  const detail = (error as { detail?: unknown }).detail;
  return typeof detail === "string" && detail.trim() !== "" ? detail : null;
}

async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
  op: UserOperation,
): Promise<T> {
  const { data, error, response } = await call;
  if (data === undefined) {
    throw new Error(userErrorMessage(response.status, op, detailOf(error)));
  }
  return data;
}

export interface UsersData {
  users: UserOut[];
  /**
   * [A-106] `true` si se dejó de seguir el cursor por el tope de páginas: la
   * lista NO es el directorio entero y la tarjeta lo tiene que decir.
   */
  truncated: boolean;
  /** `cognito` o `simulated`; `null` mientras no se sepa. La UI lo ROTULA. */
  backend: string | null;
  loading: boolean;
  error: string | null;
  dataUpdatedAt: number;
  refetch: () => void;
}

/**
 * [T-2.54] Directorio de identidades visible para quien pregunta.
 *
 * El servidor acota por tenant a los roles DE CLIENTE (`routers/users`); a un rol
 * interno le devuelve el pool entero, y por eso el acotamiento a la ficha que se
 * está viendo lo hace `UsersCard` (A-018), no este hook: aquí vive el directorio,
 * allí el cliente. El `enabled` evita pedirlo a quien no tiene la acción — sin él,
 * cada carga de /tenants dispararía un 403 para todo rol sin `manage_users`.
 *
 * [A-106 · T-8.09] Sigue `next_cursor` hasta el final (con tope). Pedir sólo la
 * primera página truncaba el directorio a 50 y, como Cognito no filtra por
 * atributos custom, un cliente cuyos usuarios cayeran en la segunda veía «SIN
 * USUARIOS» con usuarios existentes.
 */
export function useUsers(enabled: boolean): UsersData {
  const query = useQuery({
    queryKey: ["users"],
    queryFn: async () => {
      const items: UserOut[] = [];
      let backend = "";
      let cursor: string | null = null;
      let pages = 0;
      do {
        // Anotado a mano: `cursor` se lee en la llamada y se escribe con su
        // respuesta, y sin el tipo explícito `tsc` no puede cerrar el ciclo.
        const { data, error, response }: { data?: UserPage; error?: unknown; response: Response } =
          await listUsersUsersGet({
            query: cursor === null ? {} : { cursor },
          });
        if (data === undefined) {
          throw new Error(userErrorMessage(response.status, "list", detailOf(error)));
        }
        items.push(...data.items);
        backend = data.backend;
        cursor = data.next_cursor ?? null;
        pages += 1;
      } while (cursor !== null && pages < USERS_MAX_PAGES);
      return { items, backend, truncated: cursor !== null };
    },
    enabled,
    staleTime: USERS_FRESH_MS,
    refetchInterval: USERS_REFRESH_MS,
  });
  return {
    users: query.data?.items ?? [],
    truncated: query.data?.truncated ?? false,
    backend: query.data?.backend ?? null,
    loading: enabled && query.isPending,
    error: query.error ? query.error.message : null,
    dataUpdatedAt: query.dataUpdatedAt,
    refetch: () => void query.refetch(),
  };
}

function useInvalidateUsers() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["users"] });
}

export function useCreateUser() {
  const invalidate = useInvalidateUsers();
  return useMutation({
    mutationFn: (body: UserCreate) => unwrap(createUserUsersPost({ body }), "create"),
    onSuccess: invalidate,
  });
}

export function useUpdateUser() {
  const invalidate = useInvalidateUsers();
  return useMutation({
    mutationFn: ({ username, body }: { username: string; body: UserUpdate }) =>
      unwrap(updateUserUsersUsernamePatch({ path: { username }, body }), "update"),
    onSuccess: invalidate,
  });
}

export function useDeleteUser() {
  const invalidate = useInvalidateUsers();
  return useMutation({
    mutationFn: async (username: string) => {
      const { error, response } = await deleteUserUsersUsernameDelete({ path: { username } });
      if (response.status !== 204) {
        throw new Error(userErrorMessage(response.status, "delete", detailOf(error)));
      }
    },
    onSuccess: invalidate,
  });
}

/** Reset y reenvío: acuses, jamás credenciales (el correo lo lleva Cognito). */
export function useUserAction() {
  return useMutation({
    mutationFn: ({ username, action }: { username: string; action: "reset" | "resend" }) =>
      unwrap(
        action === "reset"
          ? resetPasswordUsersUsernameResetPasswordPost({ path: { username } })
          : resendInvitationUsersUsernameResendInvitationPost({ path: { username } }),
        "action",
      ),
  });
}
