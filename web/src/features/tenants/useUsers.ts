import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createUserUsersPost,
  deleteUserUsersUsernameDelete,
  listUsersUsersGet,
  resendInvitationUsersUsernameResendInvitationPost,
  resetPasswordUsersUsernameResetPasswordPost,
  updateUserUsersUsernamePatch,
} from "@takab/sdk";
import type { UserCreate, UserOut, UserUpdate } from "@takab/sdk";

/** El directorio no cambia solo: se recarga al escribir, no en un poll. */
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

export function userErrorMessage(status: number): string {
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

async function unwrap<T>(call: Promise<{ data?: T; response: Response }>): Promise<T> {
  const { data, response } = await call;
  if (data === undefined) {
    throw new Error(userErrorMessage(response.status));
  }
  return data;
}

export interface UsersData {
  users: UserOut[];
  /** `cognito` o `simulated`; `null` mientras no se sepa. La UI lo ROTULA. */
  backend: string | null;
  loading: boolean;
  error: string | null;
  dataUpdatedAt: number;
  refetch: () => void;
}

/**
 * [T-2.54] Directorio de identidades del cliente.
 *
 * El servidor ya acota por tenant (`routers/users`), así que aquí NO se vuelve a
 * filtrar: dos filtros sobre la misma frontera dan dos verdades y tarde o temprano
 * una miente. El `enabled` evita pedirlo a quien no tiene la acción — sin él, cada
 * carga de /tenants dispararía un 403 para todo rol sin `manage_users`.
 */
export function useUsers(enabled: boolean): UsersData {
  const query = useQuery({
    queryKey: ["users"],
    queryFn: async () => {
      const { data, response } = await listUsersUsersGet();
      if (data === undefined) {
        throw new Error(userErrorMessage(response.status));
      }
      return data;
    },
    enabled,
    staleTime: USERS_FRESH_MS,
  });
  return {
    users: query.data?.items ?? [],
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
    mutationFn: (body: UserCreate) => unwrap(createUserUsersPost({ body })),
    onSuccess: invalidate,
  });
}

export function useUpdateUser() {
  const invalidate = useInvalidateUsers();
  return useMutation({
    mutationFn: ({ username, body }: { username: string; body: UserUpdate }) =>
      unwrap(updateUserUsersUsernamePatch({ path: { username }, body })),
    onSuccess: invalidate,
  });
}

export function useDeleteUser() {
  const invalidate = useInvalidateUsers();
  return useMutation({
    mutationFn: async (username: string) => {
      const { response } = await deleteUserUsersUsernameDelete({ path: { username } });
      if (response.status !== 204) {
        throw new Error(userErrorMessage(response.status));
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
      ),
  });
}
