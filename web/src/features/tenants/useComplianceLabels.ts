import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { client } from "@takab/sdk";
import type {
  ComplianceClaimIn as ComplianceClaimInGen,
  ComplianceClaimOut,
  ComplianceLabelsIn,
  ComplianceLabelsOut,
} from "@takab/sdk";

/*
 * [T-2.82] Etiquetas de cumplimiento del cliente.
 *
 * [T-2.82.b] Los tipos ya NO se escriben aquí. Eran el contrato de
 * `api/src/takab_api/schemas/compliance.py` copiado a mano «mientras el SDK se
 * regenera»; el SDK se regeneró el 2026-08-08 y publica `ComplianceLabelsOut`,
 * `ComplianceClaimOut`, `ComplianceClaimIn` y `ComplianceLabelsIn` con sus campos
 * requeridos. Los nombres locales se conservan como ALIAS —no como declaraciones—
 * para no obligar a las pantallas que ya los importan a renombrar nada: son un
 * nombre para la misma verdad, no una segunda.
 *
 * Se sigue llamando con `client.get`/`client.put` y NO con las funciones generadas:
 * los tests de esta zona sustituyen `@takab/sdk` entero con `vi.mock` sin
 * `importOriginal`, así que una función generada llegaría como `undefined`. Los
 * tipos viajan por `import type`, que se borra al compilar.
 *
 * NADA de lo que se pinta se compone aquí: `notice`, `notes` y `title` los sirve el
 * servidor. Es deliberado. Las palabras con las que se presenta una afirmación
 * normativa las decide UN solo sitio (`takab_api.compliance.compliance_block`), el
 * mismo que las imprime en el dictamen PDF. Si la consola redactara las suyas,
 * pantalla y papel acabarían diciendo cosas distintas del mismo cliente — y el papel
 * lleva una firma debajo.
 */

/** Clases de afirmación admitidas. Espejo de `takab_api.compliance.CATALOG`. */
export const COMPLIANCE_CATALOG: Readonly<Record<string, string>> = {
  regulatory_framework: "Marco al que el cliente declara estar sujeto",
  internal_protocol: "Protocolo interno del cliente",
  third_party_certification: "Certificación emitida por un tercero",
  insurance_requirement: "Requisito de la aseguradora del cliente",
  contractual_obligation: "Obligación contractual del cliente",
};

export type ComplianceClaim = ComplianceClaimOut;

/**
 * El documento del cliente en su ficha. `notice` es el deslinde PERMANENTE (acompaña
 * al formulario mientras se teclea) y `notes` es lo que hay que imprimir de ESTE
 * documento, ya resuelto por el servidor.
 */
export type ComplianceDoc = ComplianceLabelsOut;

export type ComplianceClaimIn = ComplianceClaimInGen;

export type ComplianceLabelsBody = ComplianceLabelsIn;

/**
 * Sin relectura tras este umbral el documento pasa a DATOS RETENIDOS.
 *
 * No es un dato de campo, pero envejece igual: lo edita el dueño de la plataforma
 * desde otra sesión, y lo que aquí se muestra acaba impreso en un dictamen firmado.
 * Presentar como vigente una afirmación normativa retirada hace diez minutos es
 * exactamente lo que veta la regla de oro 7.
 */
export const COMPLIANCE_STALE_MS = 300_000;

const COMPLIANCE_FRESH_MS = 60_000;

export function complianceErrorMessage(status: number): string {
  switch (status) {
    case 403:
      return "SIN PERMISO · solo el dueño de la plataforma carga el marco declarado.";
    case 404:
      return "NO ENCONTRADO · el cliente no existe o no es visible para tu rol.";
    case 409:
      return "CAMBIÓ EN EL SERVIDOR · alguien editó el marco declarado. Recarga y reintenta.";
    case 422:
      return "AFIRMACIÓN INVÁLIDA · revisa la clase, el texto y la referencia citable.";
    default:
      return `/compliance-labels falló (HTTP ${status})`;
  }
}

function url(tenantId: string): string {
  return `/tenants/${tenantId}/compliance-labels`;
}

export interface ComplianceData {
  doc: ComplianceDoc | null;
  loading: boolean;
  error: string | null;
  /** Epoch ms del último dato fresco cuando YA es viejo; null = fresco. */
  staleSince: number | null;
  refetch: () => void;
}

export function useComplianceLabels(tenantId: string | null): ComplianceData {
  const query = useQuery({
    queryKey: ["compliance-labels", tenantId],
    queryFn: async (): Promise<ComplianceDoc> => {
      const { data, response } = await client.get<ComplianceDoc>({ url: url(tenantId as string) });
      if (data === undefined) {
        throw new Error(complianceErrorMessage(response.status));
      }
      return data;
    },
    enabled: tenantId !== null,
    staleTime: COMPLIANCE_FRESH_MS,
  });
  const age = Date.now() - query.dataUpdatedAt;
  return {
    doc: query.data ?? null,
    loading: tenantId !== null && query.isPending,
    error: query.error ? query.error.message : null,
    staleSince: query.dataUpdatedAt > 0 && age > COMPLIANCE_STALE_MS ? query.dataUpdatedAt : null,
    refetch: () => void query.refetch(),
  };
}

export interface ComplianceMutation {
  save: (body: ComplianceLabelsBody) => void;
  pending: boolean;
  error: string | null;
}

export function useSaveComplianceLabels(tenantId: string | null): ComplianceMutation {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: async (body: ComplianceLabelsBody): Promise<ComplianceDoc> => {
      const { data, response } = await client.put<ComplianceDoc>({
        url: url(tenantId as string),
        body,
      });
      if (data === undefined) {
        throw new Error(complianceErrorMessage(response.status));
      }
      return data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["compliance-labels", tenantId] });
    },
  });
  return {
    save: (body) => mutation.mutate(body),
    pending: mutation.isPending,
    error: mutation.error ? mutation.error.message : null,
  };
}
