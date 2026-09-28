// [T-9.41 · D-43] La tabla de casos del asistente «Cierre del evento».
//
// Lo que se defiende aquí: todo «hecho» sale de un dato del servidor, y un dato
// que no cargó se dice «sin dato», nunca «pendiente». Las etiquetas de «quién
// puede» se DERIVAN de la matriz generada: ninguna aserción las escribe a mano.

import { describe, expect, it } from "vitest";

import matriz from "../../../../shared/fixtures/rbac-matrix.json";
import { etiquetaDeRol } from "../../auth/rolesHistoricos";
import {
  MOTIVO_MIN_CHARS,
  derivarPasos,
  motivoExigido,
  quienPuede,
  recuentoPorTipo,
  type HechosDelCierre,
  type Paso,
  type Permisos,
} from "./pasos";

type MatrizRol = { routes: string[]; actions: Record<string, boolean> };
const ROLES = matriz.roles as Record<string, MatrizRol>;
const INTERNOS = matriz.internal_roles as readonly string[];

/** Lo que la matriz dice, sin pasar por el código bajo prueba. */
function rolesConAlguna(...acciones: string[]): string[] {
  return Object.keys(ROLES)
    .filter((r) => !INTERNOS.includes(r))
    .filter((r) => acciones.some((a) => ROLES[r].actions[a] === true))
    .map(etiquetaDeRol)
    .sort();
}

const TODO: Permisos = {
  ack_incident: true,
  sign_dictamen: true,
  confirm_dictamen: true,
  classify_incident: true,
  generate_report: true,
  close_incident: true,
};
const NADA: Permisos = {};

const FIRMADO = { signed_by: "u-1", band: "amarillo", status: "restricted_use" };
const SIN_FIRMA = (band: string | null = "amarillo") => ({
  signed_by: null,
  band,
  status: "restricted_use",
});

function hechos(over: Partial<HechosDelCierre> = {}): HechosDelCierre {
  return {
    incidente: { state: "acked", max_pga_g: 0.08, max_pgv_cms: 3.2 },
    dictamenes: [FIRMADO],
    clasificacion: { vigente: "real" },
    reportes: [{}],
    ...over,
  };
}

function paso(ps: Paso[], id: Paso["id"]): Paso {
  const p = ps.find((x) => x.id === id);
  if (p === undefined) throw new Error(`no hay paso ${id}`);
  return p;
}

describe("derivarPasos · forma", () => {
  it("son exactamente seis pasos, en el orden del diseño", () => {
    expect(derivarPasos(hechos(), TODO).map((p) => p.id)).toEqual([
      "acusar",
      "sacudida",
      "reportes",
      "dictamen",
      "clasificar",
      "cierre",
    ]);
  });

  it("todo paso trae título, estado y porqué", () => {
    for (const p of derivarPasos(hechos(), TODO)) {
      expect(p.titulo).not.toBe("");
      expect(p.porque).not.toBe("");
    }
  });
});

describe("derivarPasos · cada paso hecho y pendiente", () => {
  it.each<[string, Paso["id"], Partial<HechosDelCierre>, Paso["estado"]]>([
    ["acusado", "acusar", {}, "hecho"],
    [
      "abierto sin acuse",
      "acusar",
      { incidente: { state: "open", max_pga_g: 0.08, max_pgv_cms: 1 } },
      "pendiente",
    ],
    ["con PGA medida", "sacudida", {}, "hecho"],
    ["con un reporte", "reportes", {}, "hecho"],
    ["sin reportes", "reportes", { reportes: [] }, "pendiente"],
    ["cabeza firmada", "dictamen", {}, "hecho"],
    ["cabeza sin firmar", "dictamen", { dictamenes: [SIN_FIRMA()] }, "pendiente"],
    ["sin cadena", "dictamen", { dictamenes: [] }, "pendiente"],
    ["clasificado", "clasificar", {}, "hecho"],
    ["sin clasificar", "clasificar", { clasificacion: { vigente: null } }, "pendiente"],
    [
      "cerrado",
      "cierre",
      { incidente: { state: "closed", max_pga_g: 0.08, max_pgv_cms: 1 } },
      "hecho",
    ],
    ["listo para cerrar", "cierre", {}, "pendiente"],
  ])("%s ⇒ %s es %s", (_caso, id, over, estado) => {
    expect(paso(derivarPasos(hechos(over), TODO), id).estado).toBe(estado);
  });

  it("la cabeza es dictamenes[0]: una versión vieja firmada no marca hecho", () => {
    const ps = derivarPasos(hechos({ dictamenes: [SIN_FIRMA(), FIRMADO] }), TODO);
    expect(paso(ps, "dictamen").estado).toBe("pendiente");
  });

  it("sin reportes el porqué dice que no impide cerrar", () => {
    const p = paso(derivarPasos(hechos({ reportes: [] }), TODO), "reportes");
    expect(p.porque).toMatch(/sin reportes de la brigada: no impide cerrar/i);
    expect(p.requeridoParaCerrar).toBe(false);
  });

  it("el cierre queda BLOQUEADO sin acuse o sin clasificación, y dice qué falta", () => {
    const sinAcuse = paso(
      derivarPasos(
        hechos({ incidente: { state: "open", max_pga_g: null, max_pgv_cms: null } }),
        TODO,
      ),
      "cierre",
    );
    expect(sinAcuse.estado).toBe("bloqueado");
    expect(sinAcuse.porque).toMatch(/ACUSAR/);
    const sinClasif = paso(
      derivarPasos(hechos({ clasificacion: { vigente: null } }), TODO),
      "cierre",
    );
    expect(sinClasif.estado).toBe("bloqueado");
    expect(sinClasif.porque).toMatch(/CLASIFICAR/);
  });

  it("obligatorios: acusar y clasificar sí; sacudida y reportes no", () => {
    const ps = derivarPasos(hechos(), TODO);
    expect(paso(ps, "acusar").requeridoParaCerrar).toBe(true);
    expect(paso(ps, "clasificar").requeridoParaCerrar).toBe(true);
    expect(paso(ps, "sacudida").requeridoParaCerrar).toBe(false);
    expect(paso(ps, "reportes").requeridoParaCerrar).toBe(false);
  });
});

describe("derivarPasos · no_aplica sin PGA", () => {
  it("sin medición la sacudida no aplica y lo explica", () => {
    const p = paso(
      derivarPasos(
        hechos({ incidente: { state: "acked", max_pga_g: null, max_pgv_cms: null } }),
        TODO,
      ),
      "sacudida",
    );
    expect(p.estado).toBe("no_aplica");
    expect(p.porque).toMatch(/el sensor no registró PGA/i);
  });
});

describe("motivo exigido: solo real/indeterminado con la cabeza sin firmar", () => {
  it.each<[string, string | null, boolean, boolean]>([
    ["real sin firma", "real", false, true],
    ["indeterminado sin firma", "indeterminado", false, true],
    ["real firmado", "real", true, false],
    ["falso positivo sin firma", "falso_positivo", false, false],
    ["prueba sin firma", "prueba", false, false],
    ["reproducción sin firma", "reproduccion", false, false],
    ["sin clasificar", null, false, false],
  ])("%s ⇒ %s", (_caso, vigente, firmada, exige) => {
    const h = hechos({
      clasificacion: { vigente },
      dictamenes: [firmada ? FIRMADO : SIN_FIRMA()],
    });
    expect(motivoExigido(h)).toBe(exige);
    expect(paso(derivarPasos(h, TODO), "cierre").exigeMotivo).toBe(exige);
  });

  it("con la cadena vacía también se exige (no hay cabeza firmada)", () => {
    expect(motivoExigido(hechos({ dictamenes: [] }))).toBe(true);
  });

  it("el porqué del cierre nombra el mínimo de caracteres", () => {
    const p = paso(derivarPasos(hechos({ dictamenes: [SIN_FIRMA()] }), TODO), "cierre");
    expect(p.porque).toContain(String(MOTIVO_MIN_CHARS));
    expect(MOTIVO_MIN_CHARS).toBe(20);
  });

  it("el dictamen es obligatorio con real/indeterminado y no con una terminal", () => {
    expect(paso(derivarPasos(hechos(), TODO), "dictamen").requeridoParaCerrar).toBe(true);
    expect(
      paso(derivarPasos(hechos({ clasificacion: { vigente: "prueba" } }), TODO), "dictamen")
        .requeridoParaCerrar,
    ).toBe(false);
  });
});

describe("las tres bandas del paso 4 salen de la cabeza", () => {
  it.each<[string | null, RegExp]>([
    ["verde", /el sistema lo firma solo tras 5 min de calma/i],
    ["amarillo", /lo confirma un brigadista, el inspector o el administrador/i],
    ["rojo", /solo el INSPECTOR puede firmarlo/],
    [null, /lo firma el inspector/i],
  ])("banda %s", (band, texto) => {
    const p = paso(derivarPasos(hechos({ dictamenes: [SIN_FIRMA(band)] }), TODO), "dictamen");
    expect(p.porque).toMatch(texto);
  });

  it("AMARILLO sin firmar + confirm_dictamen ⇒ CONFIRMAR", () => {
    const p = paso(
      derivarPasos(hechos({ dictamenes: [SIN_FIRMA("amarillo")] }), { confirm_dictamen: true }),
      "dictamen",
    );
    expect(p.accion).toBe("confirm_dictamen");
  });

  it("ROJO sin firmar + sign_dictamen ⇒ enlace a firmar en Evaluación", () => {
    const p = paso(
      derivarPasos(hechos({ dictamenes: [SIN_FIRMA("rojo")] }), { sign_dictamen: true }),
      "dictamen",
    );
    expect(p.accion).toBe("firmar_en_evaluacion");
  });

  it("ROJO sin firmar + sólo confirm_dictamen ⇒ no confirma: dice quién firma", () => {
    const p = paso(
      derivarPasos(hechos({ dictamenes: [SIN_FIRMA("rojo")] }), { confirm_dictamen: true }),
      "dictamen",
    );
    expect(p.accion).toBeUndefined();
    expect([...(p.quienPuede ?? [])].sort()).toEqual(rolesConAlguna("sign_dictamen"));
  });

  it("cerrado con cabeza no_inhabit_inspect firmada + sign_dictamen ⇒ LEVANTAR RESTRICCIÓN", () => {
    const p = paso(
      derivarPasos(
        hechos({
          incidente: { state: "closed", max_pga_g: 0.3, max_pgv_cms: 20 },
          dictamenes: [{ signed_by: "u-9", band: "rojo", status: "no_inhabit_inspect" }],
        }),
        { sign_dictamen: true },
      ),
      "dictamen",
    );
    expect(p.estado).toBe("hecho");
    expect(p.accion).toBe("levantar_restriccion");
  });
});

describe("«quién puede» cuando falta la acción", () => {
  it("quienPuede() sale de la matriz, sin roles internos", () => {
    expect([...quienPuede("close_incident")].sort()).toEqual(rolesConAlguna("close_incident"));
    expect([...quienPuede("ack_incident")].sort()).toEqual(rolesConAlguna("ack_incident"));
  });

  it.each<[Paso["id"], string[], Partial<HechosDelCierre>]>([
    ["acusar", ["ack_incident"], { incidente: { state: "open", max_pga_g: 1, max_pgv_cms: 1 } }],
    ["clasificar", ["classify_incident"], { clasificacion: { vigente: null } }],
    ["cierre", ["close_incident"], {}],
    ["dictamen", ["confirm_dictamen", "sign_dictamen"], { dictamenes: [SIN_FIRMA("amarillo")] }],
  ])("sin permisos, %s dice quién puede", (id, acciones, over) => {
    const p = paso(derivarPasos(hechos(over), NADA), id);
    expect(p.accion).toBeUndefined();
    expect([...(p.quienPuede ?? [])].sort()).toEqual(rolesConAlguna(...acciones));
    expect((p.quienPuede ?? []).length).toBeGreaterThan(0);
  });

  it("con el permiso no se pinta «quién puede»", () => {
    const p = paso(
      derivarPasos(hechos({ incidente: { state: "open", max_pga_g: 1, max_pgv_cms: 1 } }), TODO),
      "acusar",
    );
    expect(p.accion).toBe("ack_incident");
    expect(p.quienPuede).toBeUndefined();
  });

  it("un paso hecho no ofrece la acción (acusar dos veces no existe)", () => {
    expect(paso(derivarPasos(hechos(), TODO), "acusar").accion).toBeUndefined();
  });

  it("cerrado: no se ofrece reclasificar ni cerrar", () => {
    const ps = derivarPasos(
      hechos({ incidente: { state: "closed", max_pga_g: 0.1, max_pgv_cms: 1 } }),
      TODO,
    );
    expect(paso(ps, "clasificar").accion).toBeUndefined();
    expect(paso(ps, "cierre").accion).toBeUndefined();
  });
});

describe("un dato que no cargó NO es «pendiente»", () => {
  it.each<[Paso["id"], Partial<HechosDelCierre>]>([
    ["acusar", { incidente: null }],
    ["sacudida", { incidente: null }],
    ["reportes", { reportes: null }],
    ["dictamen", { dictamenes: null }],
    ["clasificar", { clasificacion: null }],
    ["cierre", { incidente: null }],
    ["cierre", { clasificacion: null }],
    ["cierre", { dictamenes: null }],
  ])("%s sin su dato ⇒ sin_dato", (id, over) => {
    const p = paso(derivarPasos(hechos(over), TODO), id);
    expect(p.estado).toBe("sin_dato");
    expect(p.accion).toBeUndefined();
  });

  it("pero CERRADO lo dice la fila, aunque lo demás no cargara", () => {
    const p = paso(
      derivarPasos(
        {
          incidente: { state: "closed", max_pga_g: null, max_pgv_cms: null },
          dictamenes: null,
          clasificacion: null,
          reportes: null,
        },
        TODO,
      ),
      "cierre",
    );
    expect(p.estado).toBe("hecho");
  });

  it("sin la cadena no se decide el motivo (ni se exige ni se descarta a ciegas)", () => {
    expect(motivoExigido(hechos({ dictamenes: null }))).toBe(false);
  });
});

describe("recuentoPorTipo · el paso 3 cuenta por tipo con el rótulo de Evaluación", () => {
  it("una categoría cuenta una vez por reporte, de más a menos frecuente", () => {
    expect(
      recuentoPorTipo([
        { categories: [{ key: "gas_leak" }, { key: "gas_leak" }, { key: "structural" }] },
        { categories: [{ key: "gas_leak" }] },
        { categories: [] },
      ]),
    ).toEqual([
      { tipo: "Fuga de gas", n: 2 },
      { tipo: "Daño estructural", n: 1 },
    ]);
  });

  it("una categoría desconocida se pinta cruda, no se descarta", () => {
    expect(recuentoPorTipo([{ categories: [{ key: "otra" }] }])).toEqual([{ tipo: "otra", n: 1 }]);
  });
});
