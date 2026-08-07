// T-2.71 · Lo que la consola DICE de una ventana de mantenimiento.
//
// El criterio 2 de la ficha es "la consola lo dice en pantalla mientras dure;
// nadie debe deducirlo". Aquí vive la mitad pura de esa frase: qué texto sale, y
// qué cuenta como "tapado por una ventana". Se prueba aparte del banner porque
// es lo que también consume la tarjeta de flota — dos pantallas, una sola verdad.

import { describe, expect, it } from "vitest";

import type { MaintenanceWindowOut } from "@takab/sdk";

import {
  MUTE_OUTCOMES,
  maintenanceLabel,
  muteAckLine,
  muteHeadline,
  muteOutcome,
  windowCovering,
} from "./maintenance";
import type { MuteOutcome } from "./maintenance";

/** La afirmación incondicional que el banner soltaba pasara lo que pasara. */
const AFIRMACION = "ALARMAS DE OPERACIÓN SILENCIADAS";

const NOW = Date.parse("2026-08-06T03:35:00Z");

function w(over: Partial<MaintenanceWindowOut> = {}): MaintenanceWindowOut {
  return {
    window_id: "w-1",
    tenant_id: "t-1",
    gateway_id: "gw-1",
    gateway_serial: "SER-1",
    site_name: "Torre Dev",
    scope: "gateway",
    opened_by: "u-1",
    reason: "cambio del cable de red del Shake",
    duration_s: 1800,
    opened_at: "2026-08-06T03:30:12Z",
    starts_at: "2026-08-06T03:31:00Z",
    ends_at: "2026-08-06T04:01:00Z",
    closed_at: null,
    active: true,
    alarm_names: ["takab-dev-gateway-offline-gw-a", "takab-dev-sensor-mudo-gw-a"],
    requested: 2,
    silenced: 2,
    missing_names: [],
    missing: 0,
    mute_rule: "takab-dev-mw-w-1",
    ...over,
  } as MaintenanceWindowOut;
}

// --- [B8] El TITULAR no puede afirmar lo que el servidor contradice ----------
//
// El banner decía «ALARMAS DE OPERACIÓN SILENCIADAS» SIEMPRE, incluso con un
// `0/N` en el mismo payload. Y con `ops_muting_enabled=False` —el default que va
// a producción— ese es el estado de TODA ventana: en producción, hoy, la consola
// afirmaría que la vigilancia está apagada mientras las alarmas siguen sonando.
// No es la regla de oro 7 (dato viejo pintado como fresco): es peor, es una
// afirmación que el servidor desmiente en el MISMO cuerpo de la respuesta.

describe("muteHeadline", () => {
  it("solo afirma el silencio cuando el servidor dice que TODAS quedaron mudas", () => {
    expect(muteHeadline(w())).toBe("ALARMAS DE OPERACIÓN SILENCIADAS");
  });

  it("el default de producción —silenciador apagado— NO afirma silencio", () => {
    // `ops_muting_enabled=False` ⇒ el servidor ni emite regla (`mute_rule` null)
    // ni silencia nada. Es el estado de TODA ventana en producción hoy.
    const apagado = w({
      requested: 2,
      silenced: 0,
      missing: 2,
      missing_names: ["a", "b"],
      mute_rule: null,
    });
    expect(muteHeadline(apagado)).toBe("LAS ALARMAS DE OPERACIÓN SIGUEN SONANDO");
    expect(muteHeadline(apagado)).not.toContain(AFIRMACION);
  });

  it("un silencio a medias NO se cuenta como silencio", () => {
    // El titular carga el hecho peligroso: parte de la vigilancia sigue viva y
    // quien está de guardia va a recibir ESOS correos.
    const parcial = w({ requested: 2, silenced: 1, missing: 1, missing_names: ["a"] });
    expect(muteHeadline(parcial)).toBe("PARTE DE LAS ALARMAS DE OPERACIÓN SIGUE SONANDO");
    expect(muteHeadline(parcial)).not.toContain(AFIRMACION);
  });

  it("sin alarmas que silenciar no afirma ni silencio ni ruido", () => {
    expect(muteHeadline(w({ requested: 0, silenced: 0, missing: 0, missing_names: [] }))).toBe(
      "SIN ALARMAS DE OPERACIÓN QUE SILENCIAR",
    );
  });

  // El guardia de la clase entera NO vive aquí: vive en «el guardia de la CLASE»
  // (final del archivo), derivado de `MUTE_OUTCOMES`. El que había en este sitio
  // iteraba cuatro fixtures escritas a mano y se vendía como exhaustivo; era
  // teatro — el quinto estado (`assumed`) entró sin que se quejara.
});

// --- [C1/C2] La SUPOSICIÓN no se pinta como MEDIDA ---------------------------
//
// `mute_verified=false` es el acuse A CIEGAS: el `PutAlarmMuteRule` se emitió y
// el `GetAlarmMuteRule` que lo comprueba no se pudo leer (timeout, corte, 5xx).
// El servidor rellena entonces `silenced = requested` a propósito —se asume el
// estado peligroso—, así que el payload llega con la MISMA forma que un éxito
// medido: `2/2`, `missing: 0`, `mute_rule` con nombre.
//
// La consola no leía el campo (`grep -rn mute_verified web/` daba CERO) y pintaba
// las dos cosas igual. Es la familia entera de esta fase en una línea: afirmar
// como medido lo que solo se supone. Y aquí la consecuencia es concreta — quien
// lee «2/2 SILENCIADAS» deja de vigilar ese edificio, cuando nadie ha comprobado
// que las alarmas estén mudas ni que vayan a volver.

describe("acuse a ciegas (mute_verified=false)", () => {
  const aCiegas = w({ mute_verified: false });

  it("NO se pinta igual que el mismo payload medido", () => {
    // Misma forma, distinta verdad: sin este assert las dos ramas son la misma
    // pantalla y el arreglo del servidor no llega al operador.
    const medido = w({ mute_verified: true });
    expect(muteOutcome(aCiegas)).not.toBe(muteOutcome(medido));
    expect(muteHeadline(aCiegas)).not.toBe(muteHeadline(medido));
    expect(muteAckLine(aCiegas)).not.toBe(muteAckLine(medido));
    expect(maintenanceLabel(aCiegas)).not.toBe(maintenanceLabel(medido));
  });

  it("no afirma el silencio: lo declara SUPUESTO", () => {
    expect(muteHeadline(aCiegas)).not.toContain(AFIRMACION);
    expect(muteHeadline(aCiegas)).toContain("SUPUESTO");
  });

  it("el acuse NO imprime la cifra medida `N/M ALARMAS SILENCIADAS`", () => {
    // `2/2 ALARMAS SILENCIADAS` es literalmente el molde de lo medido. Aquí ese
    // 2 lo escribió el servidor asumiendo lo peor, no leyéndolo de CloudWatch:
    // reusar el molde sería la mentira.
    const linea = muteAckLine(aCiegas);
    expect(linea).not.toContain("ALARMAS SILENCIADAS");
    expect(linea).toContain("2 ALARMAS PEDIDAS");
    expect(linea).toContain("SIN ACUSE");
  });

  it("la tarjeta de flota tampoco lo redondea a silencio", () => {
    expect(maintenanceLabel(aCiegas)).toBe(
      "EN MANTENIMIENTO HASTA 04:01 UTC · SILENCIO SIN COMPROBAR",
    );
  });

  it("un acuse a ciegas con las cifras a cero TAMPOCO se lee como medido", () => {
    // Punto ciego declarado: hoy `_ack_a_ciegas` solo produce `silenced =
    // requested`, así que esta forma no se puede dar. Si el servidor empezara a
    // emitirla, la clasificación NO puede caer en `none` —«medimos y no se
    // silenció nada»— porque no se midió nada en absoluto.
    expect(muteOutcome(w({ mute_verified: false, requested: 2, silenced: 0, missing: 2 }))).toBe(
      "assumed",
    );
  });

  it("un payload SIN el campo se lee como MEDIDO, y eso es una decisión, no un olvido", () => {
    // PUNTO CIEGO CONOCIDO Y ANCLADO. `mute_verified` es opcional en el SDK
    // porque tiene default en Pydantic (`True`), y el servidor lo emite siempre.
    // Ausente solo puede venir de una respuesta anterior a la migración 0031, y
    // aquel servidor NO tenía el camino del acuse a ciegas: cuando la
    // comprobación fallaba declaraba `0/N`. Así que ausente ⟹ medido es cierto
    // HOY. Si algún día el servidor pudiera omitir el campo sin haber medido,
    // este test es el que hay que venir a romper.
    const sinCampo = w();
    expect("mute_verified" in sinCampo).toBe(false);
    expect(muteOutcome(sinCampo)).toBe("all");
  });
});

// --- [B9] Un rótulo por causa, no un rótulo para tres causas -----------------
//
// El servidor rellena `missing_names` en TRES casos incompatibles y solo uno es
// "no existía": (a) el silenciador está apagado (`client is None`, el default de
// producción), (b) cualquier excepción de CloudWatch, (c) la alarma de verdad no
// existe. Los dos primeros dejan `mute_rule` en NULL —la regla no llegó a
// emitirse— y el tercero NO: ahí está el discriminador que el payload ya trae.
// Es el defecto de T-2.68 (un rótulo que colapsa causas que piden reacciones
// distintas) reproducido tres tareas después.

describe("muteAckLine", () => {
  it("dice N/M SILENCIADAS con el vocabulario que ya existe", () => {
    // Espejo literal de `ackLine` en DrillBanner: no se inventan rótulos nuevos.
    expect(muteAckLine(w())).toBe("2/2 ALARMAS SILENCIADAS");
  });

  it("separa 'no había alarma' de 'no se silenció'", () => {
    // La lección de T-2.48: colapsar los dos hechos es mentir. Aquí sería peor —
    // la pantalla diría que una vigilancia está apagada cuando nunca existió.
    const line = muteAckLine(w({ requested: 2, silenced: 1, missing: 1, missing_names: ["x"] }));
    expect(line).toBe(
      "1/2 ALARMAS SILENCIADAS · 1 SIN SILENCIAR: NO EXISTEN O LA REGLA NO LAS GUARDÓ",
    );
  });

  it("una ventana que no silenció NADA lo dice, no se calla", () => {
    const line = muteAckLine(
      w({ requested: 2, silenced: 0, missing: 2, missing_names: ["a", "b"] }),
    );
    expect(line).toBe(
      "0/2 ALARMAS SILENCIADAS · 2 SIN SILENCIAR: NO EXISTEN O LA REGLA NO LAS GUARDÓ",
    );
  });

  it("la regla que NUNCA se emitió no se rotula 'SIN ALARMA EXISTENTE'", () => {
    // `mute_rule` NULL con `requested > 0` = el servidor no llegó a llamar a
    // CloudWatch: silenciador apagado o excepción. Las alarmas EXISTEN y siguen
    // sonando; decir "no existen" mandaría al operador a buscar un problema de
    // inventario que no tiene.
    const sinRegla = w({
      requested: 2,
      silenced: 0,
      missing: 2,
      missing_names: ["a", "b"],
      mute_rule: null,
    });
    expect(muteAckLine(sinRegla)).toBe(
      "0/2 ALARMAS SILENCIADAS · 2 SIN SILENCIAR: SILENCIADOR APAGADO O CON FALLO",
    );
    expect(muteAckLine(sinRegla)).not.toContain("SIN ALARMA EXISTENTE");
  });

  it("las dos causas de 'sin silenciar' JAMÁS comparten rótulo", () => {
    // El corazón de B9: mismo `0/2`, misma cifra de `missing`, causas distintas.
    const base = { requested: 2, silenced: 0, missing: 2, missing_names: ["a", "b"] };
    expect(muteAckLine(w({ ...base, mute_rule: null }))).not.toBe(
      muteAckLine(w({ ...base, mute_rule: "takab-dev-mw-w-1" })),
    );
  });

  it("un gabinete sin alarmas que silenciar NO finge un cero tranquilizador", () => {
    // `0/0 SILENCIADAS` se leería como "todo en orden". No hubo nada que callar,
    // y eso hay que decirlo con palabras (regla de oro 7).
    expect(muteAckLine(w({ requested: 0, silenced: 0, missing: 0, missing_names: [] }))).toBe(
      "SIN ALARMA QUE SILENCIAR",
    );
  });
});

describe("maintenanceLabel", () => {
  it("lleva la hora UTC de CIERRE, no la de apertura", () => {
    // Lo que el operador necesita saber es hasta cuándo está ciego el sistema.
    expect(maintenanceLabel(w())).toBe("EN MANTENIMIENTO HASTA 04:01 UTC");
  });

  it("cuando NADA quedó mudo lo dice en la TARJETA, no solo en el banner", () => {
    // «EN MANTENIMIENTO» a secas se lee como «sus alarmas están calladas»: es la
    // suposición por defecto de quien mira la flota. Si es falsa, la tarjeta
    // tiene que romperla ahí mismo — nadie abre el banner para comprobarlo.
    expect(
      maintenanceLabel(
        w({ requested: 2, silenced: 0, missing: 2, missing_names: ["a", "b"], mute_rule: null }),
      ),
    ).toBe("EN MANTENIMIENTO HASTA 04:01 UTC · ALARMAS SIN SILENCIAR");
  });

  it("un silencio a medias también se ve en la tarjeta", () => {
    expect(
      maintenanceLabel(w({ requested: 2, silenced: 1, missing: 1, missing_names: ["a"] })),
    ).toBe("EN MANTENIMIENTO HASTA 04:01 UTC · SILENCIADAS EN PARTE");
  });

  it("sin alarmas que silenciar la tarjeta no insinúa que las haya calladas", () => {
    expect(maintenanceLabel(w({ requested: 0, silenced: 0, missing: 0, missing_names: [] }))).toBe(
      "EN MANTENIMIENTO HASTA 04:01 UTC · SIN ALARMA QUE SILENCIAR",
    );
  });
});

describe("windowCovering", () => {
  const activa = w();
  const vencida = w({ window_id: "w-2", active: false, ends_at: "2026-08-06T03:00:00Z" });
  const otroGw = w({ window_id: "w-3", gateway_id: "gw-9" });

  it("empareja por gateway_id, no por sitio", () => {
    expect(windowCovering([activa, otroGw], "gw-1", NOW)?.window_id).toBe("w-1");
    expect(windowCovering([activa, otroGw], "gw-9", NOW)?.window_id).toBe("w-3");
    expect(windowCovering([activa], "gw-otro", NOW)).toBeNull();
  });

  it("una ventana ya vencida no tapa nada, aunque el servidor la mande", () => {
    // Doble candado con el predicado SQL: si una respuesta vieja se quedara en
    // caché, la pantalla NO seguiría anunciando un silencio que ya terminó.
    expect(windowCovering([vencida], "gw-1", NOW)).toBeNull();
  });

  it("una ventana que aún no arranca ya cuenta como abierta", () => {
    // Entre el clic y el minuto de `at()` pasan hasta 60 s. Anunciarla ya es el
    // lado seguro: el banner se ve de más, nunca de menos.
    const futura = w({ starts_at: "2026-08-06T03:40:00Z", ends_at: "2026-08-06T04:10:00Z" });
    expect(windowCovering([futura], "gw-1", NOW)?.window_id).toBe("w-1");
  });

  it("la ventana de PLATAFORMA no tapa a ningún gabinete concreto", () => {
    // Silencia ec2_*, no las alarmas del aparato: pintarla en una tarjeta de
    // gabinete diría que ESE gabinete está sin vigilancia, y es falso.
    const plataforma = w({ scope: "platform", gateway_id: null, tenant_id: null });
    expect(windowCovering([plataforma], "gw-1", NOW)).toBeNull();
  });
});

// --- [C4] El guardia de la CLASE, derivado del tipo --------------------------
//
// El que había aquí se vendía como exhaustivo y recorría CUATRO fixtures
// escritas a mano. Cuando `MuteOutcome` ganó su quinto miembro no se quejó
// nadie: un test que enumera casos concretos se queda ciego ante el siguiente,
// que es la lección número uno de esta fase.
//
// La lista se INVIERTE para arreglarlo: `MUTE_OUTCOMES` es el dato y
// `MuteOutcome` se deriva de él (`(typeof MUTE_OUTCOMES)[number]`), así que no
// pueden divergir — no hay forma de añadir un miembro al tipo sin añadirlo al
// array. Sobre esa lista se apoyan TRES candados de distinta naturaleza:
//
// 1. `Record<MuteOutcome, …>` — un miembro nuevo sin fixture no COMPILA
//    (`tsc --noEmit`). Es el candado más informativo y el que no bloquea nada:
//    vitest transpila sin comprobar tipos.
// 2. las claves de esa tabla contra `MUTE_OUTCOMES` EN TIEMPO DE EJECUCIÓN —
//    este sí tumba la suite, que es la única barrera que para un merge.
// 3. el recorrido de la lista, que exige a cada función una frase propia y no
//    vacía para cada miembro. Un `switch` sin el caso nuevo devuelve `undefined`
//    en ejecución aunque `tsc` lo haya cazado; aquí se cae con nombre y apellido.
describe("el guardia de la CLASE", () => {
  // Una fixture por miembro. NO es la lista: es la tabla que la lista audita.
  const PORTADOR: Record<MuteOutcome, MaintenanceWindowOut> = {
    all: w(),
    assumed: w({ mute_verified: false }),
    partial: w({ requested: 2, silenced: 1, missing: 1, missing_names: ["a"] }),
    none: w({ requested: 2, silenced: 0, missing: 2, missing_names: ["a", "b"] }),
    none_requested: w({ requested: 0, silenced: 0, missing: 0, missing_names: [] }),
  };

  it("la tabla de fixtures cubre EXACTAMENTE los miembros del tipo", () => {
    // Candado 2: el que se cae en vitest —y por tanto en CI— cuando entra un
    // sexto estado y nadie escribe cómo se pinta.
    expect(Object.keys(PORTADOR).sort()).toEqual([...MUTE_OUTCOMES].sort());
  });

  it.each([...MUTE_OUTCOMES])("«%s» tiene su propia frase en las tres funciones", (outcome) => {
    const ventana = PORTADOR[outcome];
    // La fixture produce DE VERDAD ese estado: sin esto la tabla podría estar
    // completa y describir otra cosa.
    expect(muteOutcome(ventana)).toBe(outcome);
    for (const frase of [muteHeadline(ventana), muteAckLine(ventana), maintenanceLabel(ventana)]) {
      expect(typeof frase).toBe("string");
      expect(frase.length).toBeGreaterThan(0);
      expect(frase).not.toContain("undefined");
    }
  });

  it("la afirmación incondicional es EXCLUSIVA de 'todas mudas y medido'", () => {
    // El invariante que de verdad protege al on-call, dicho sobre la clase
    // entera y no sobre una lista de ejemplos: si alguien rotula un estado nuevo
    // con la frase de éxito «por comodidad», esto cae.
    for (const outcome of MUTE_OUTCOMES) {
      expect(muteHeadline(PORTADOR[outcome]).includes(AFIRMACION)).toBe(outcome === "all");
    }
  });

  it("ningún estado comparte titular con otro", () => {
    // Dos estados con el mismo titular son un estado que no se puede ver.
    const titulares = MUTE_OUTCOMES.map((o) => muteHeadline(PORTADOR[o]));
    expect(new Set(titulares).size).toBe(MUTE_OUTCOMES.length);
  });
});
