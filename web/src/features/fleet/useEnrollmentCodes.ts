import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createEnrollmentCodeSitesSiteIdEnrollmentCodesPost,
  deactivateEnrollmentCodeSitesSiteIdEnrollmentCodesCodeDelete,
  listEnrollmentCodesSitesSiteIdEnrollmentCodesGet,
} from "@takab/sdk";
import type { EnrollmentCodeOut } from "@takab/sdk";

/** Alfabeto sin `0/O` ni `1/I/L`: el código se dicta por teléfono y se teclea en
 * un móvil, a veces a oscuras y con prisa. Cada par ambiguo es un enrolamiento
 * fallido en el peor momento posible. */
const ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";

/** Longitud del código generado: 8 caracteres del alfabeto de arriba ≈ 40 bits. */
export const CODE_LENGTH = 8;

/**
 * Código aleatorio con CSPRNG. `Math.random()` no sirve: es predecible, y este
 * código concede acceso al estado de un edificio durante una emergencia.
 */
export function generateEnrollmentCode(): string {
  const bytes = new Uint32Array(CODE_LENGTH);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (n) => ALPHABET[n % ALPHABET.length]).join("");
}

export function enrollmentErrorMessage(status: number): string {
  switch (status) {
    case 403:
      return "SIN PERMISO · tu rol no administra los códigos de alta de esta estación.";
    case 404:
      return "NO ENCONTRADO · la estación o el código no existen para tu tenant.";
    case 409:
      return "CÓDIGO REPETIDO · genera otro.";
    case 422:
      return "DATOS INVÁLIDOS · revisa la vigencia y el número de usos.";
    default:
      return `La operación sobre los códigos falló (HTTP ${status})`;
  }
}

/**
 * Sin relectura tras este umbral el listado pasa a DATOS RETENIDOS.
 *
 * No hay poll (los códigos no cambian solos), pero SÍ envejecen: otro
 * administrador puede revocar uno desde otra sesión y esta pestaña seguiría
 * mostrándolo activo. Un código revocado presentado como vigente es justo el dato
 * falso que veta la regla de oro 7 — y aquí decide quién entra a un edificio.
 */
export const CODES_STALE_MS = 180_000;

export interface EnrollmentCodesData {
  codes: EnrollmentCodeOut[];
  loading: boolean;
  error: string | null;
  dataUpdatedAt: number;
  refetch: () => void;
}

export function useEnrollmentCodes(siteId: string | null): EnrollmentCodesData {
  const query = useQuery({
    queryKey: ["enrollment-codes", siteId],
    queryFn: async () => {
      const { data, response } = await listEnrollmentCodesSitesSiteIdEnrollmentCodesGet({
        path: { site_id: siteId as string },
      });
      if (data === undefined) {
        throw new Error(enrollmentErrorMessage(response.status));
      }
      return data;
    },
    enabled: siteId !== null,
  });
  return {
    codes: query.data ?? [],
    loading: siteId !== null && query.isPending,
    error: query.error ? query.error.message : null,
    dataUpdatedAt: query.dataUpdatedAt,
    refetch: () => void query.refetch(),
  };
}

export interface CreateCodeArgs {
  siteId: string;
  code: string;
  /** RFC3339, o `null` = sin caducidad (la UI lo rotula como tal). */
  expiresAt: string | null;
  /** `null` = usos ilimitados. */
  maxUses: number | null;
}

export function useCreateEnrollmentCode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ siteId, code, expiresAt, maxUses }: CreateCodeArgs) => {
      const { data, response } = await createEnrollmentCodeSitesSiteIdEnrollmentCodesPost({
        path: { site_id: siteId },
        body: { code, expires_at: expiresAt, max_uses: maxUses },
      });
      if (data === undefined) {
        throw new Error(enrollmentErrorMessage(response.status));
      }
      return data;
    },
    onSuccess: (_data, vars) =>
      qc.invalidateQueries({ queryKey: ["enrollment-codes", vars.siteId] }),
  });
}

export function useRevokeEnrollmentCode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ siteId, code }: { siteId: string; code: string }) => {
      const { response } = await deactivateEnrollmentCodeSitesSiteIdEnrollmentCodesCodeDelete({
        path: { site_id: siteId, code },
      });
      if (response.status !== 204) {
        throw new Error(enrollmentErrorMessage(response.status));
      }
    },
    onSuccess: (_data, vars) =>
      qc.invalidateQueries({ queryKey: ["enrollment-codes", vars.siteId] }),
  });
}
