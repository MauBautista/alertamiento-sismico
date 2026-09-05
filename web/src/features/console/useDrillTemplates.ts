// [T-5.13] Plantillas de simulacro en la consola.
//
// El alta de un simulacro tenía cinco campos y ninguno era una plantilla, así que
// para el macrosimulacro de septiembre había que teclear los sitios, la duración
// y la nota a mano **cada vez**, en el caso de uso más visible del producto.
//
// El hook expone el CRUD entero y una sola lectura derivada que el modal usa
// para no callar nada: `degradadas`. Va aquí y no en el componente porque es la
// afirmación que la ficha exige —«lo dice al usarla»— y tiene que ser la misma
// en cualquier superficie que pinte plantillas.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createTemplateDrillTemplatesPost,
  deleteTemplateDrillTemplatesTemplateIdDelete,
  listTemplatesDrillTemplatesGet,
  updateTemplateDrillTemplatesTemplateIdPut,
} from "@takab/sdk";
import type { DrillTemplateIn, DrillTemplateOut } from "@takab/sdk";

export const DRILL_TEMPLATES_KEY = ["drill-templates"] as const;

export interface DrillTemplatesData {
  items: DrillTemplateOut[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
  crear: (input: DrillTemplateIn) => void;
  editar: (templateId: string, input: DrillTemplateIn) => void;
  borrar: (templateId: string) => void;
  /** Mutación en vuelo: el formulario se deshabilita mientras dura. */
  pending: boolean;
  /** Error de la última mutación, ya en mayúsculas para pintarlo. */
  mutationError: string | null;
}

/**
 * ¿Cuántos de los sitios de esta plantilla NO se pueden usar hoy?
 *
 * Lo calcula el servidor —evaluando el inventario al leer, nunca congelándolo— y
 * aquí solo se lee. Recalcularlo en el navegador sería inventar un segundo
 * criterio: `/sites` no dice qué edificios tienen gabinete comandable.
 */
export function sitiosNoUsables(t: DrillTemplateOut): number {
  return t.sitios_no_usables ?? 0;
}

/** Las que hoy lanzarían contra menos edificios de los que definen. */
export function degradadas(items: DrillTemplateOut[]): DrillTemplateOut[] {
  return items.filter((t) => sitiosNoUsables(t) > 0);
}

export function useDrillTemplates(enabled: boolean = true): DrillTemplatesData {
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: DRILL_TEMPLATES_KEY,
    enabled,
    queryFn: async () => {
      const { data, response } = await listTemplatesDrillTemplatesGet();
      if (data === undefined) throw new Error(`GET /drill-templates falló (${response.status})`);
      return data.items;
    },
  });

  const invalidar = () => {
    void qc.invalidateQueries({ queryKey: DRILL_TEMPLATES_KEY });
  };

  const crear = useMutation({
    mutationFn: async (input: DrillTemplateIn) => {
      const { data, response } = await createTemplateDrillTemplatesPost({ body: input });
      if (data === undefined) {
        // El 409 del nombre repetido es el que el operador va a ver de verdad, y
        // «falló (409)» no le dice qué hacer.
        throw new Error(
          response.status === 409
            ? "YA EXISTE UNA PLANTILLA CON ESE NOMBRE"
            : `POST /drill-templates falló (${response.status})`,
        );
      }
      return data;
    },
    onSuccess: invalidar,
  });

  const editar = useMutation({
    mutationFn: async (vars: { templateId: string; input: DrillTemplateIn }) => {
      const { data, response } = await updateTemplateDrillTemplatesTemplateIdPut({
        path: { template_id: vars.templateId },
        body: vars.input,
      });
      if (data === undefined) {
        throw new Error(
          response.status === 409
            ? "YA EXISTE UNA PLANTILLA CON ESE NOMBRE"
            : `PUT /drill-templates falló (${response.status})`,
        );
      }
      return data;
    },
    onSuccess: invalidar,
  });

  const borrar = useMutation({
    mutationFn: async (templateId: string) => {
      const { error, response } = await deleteTemplateDrillTemplatesTemplateIdDelete({
        path: { template_id: templateId },
      });
      if (error !== undefined) {
        throw new Error(`DELETE /drill-templates falló (${response.status})`);
      }
    },
    onSuccess: invalidar,
  });

  const enVuelo = [crear, editar, borrar];
  const fallida = enVuelo.find((m) => m.error);

  return {
    items: query.data ?? [],
    loading: query.isPending,
    error: query.error ? query.error.message : null,
    refetch: () => {
      void query.refetch();
    },
    crear: (input) => crear.mutate(input),
    editar: (templateId, input) => editar.mutate({ templateId, input }),
    borrar: (templateId) => borrar.mutate(templateId),
    pending: enVuelo.some((m) => m.isPending),
    mutationError: fallida?.error ? fallida.error.message.toUpperCase() : null,
  };
}
