// [T-9.04] EL VEREDICTO QUE SOBREVIVE AL CIERRE, EN INICIO.
//
// Desde `D-33` firmar el dictamen cierra el incidente en tres segundos. El
// servidor ya lo arrastra (`phase = reentry_blocked` + `reentry.reason`), pero
// la app sólo sabía pintar el cartel VERDE: un NO HABITAR firmado dejaba INICIO
// diciendo SEGURO, sin una palabra del bloqueo. Estos tests fijan la derivación
// PURA: qué aviso toca, con qué tono y qué rótulo toma la tarjeta de estado.
//
// ⚠️ Ningún aviso de bloqueo convive con «SEGURO». Hasta la revisión de F0 sólo
// lo negaba el NO HABITAR: con un pendiente —que el servidor sirve 30 días— o
// con un motivo desconocido, INICIO decía en grande «SEGURO» bajo una franja de
// «reingreso bloqueado». Son dos verdades que se desmienten, y la persona lee
// la grande.
import type { MobileStateOut } from "@takab/sdk";

import type { HealthBanner } from "@/features/home/health";

import { avisoDeReingreso, estadoDelInmueble } from "./avisoReingreso";

type Entrada = Pick<MobileStateOut, "phase" | "reentry">;

function estado(
  phase: MobileStateOut["phase"],
  reason: MobileStateOut["reentry"]["reason"],
): Entrada {
  return {
    phase,
    reentry: {
      blocked: reason !== null,
      dictamen_signed: reason === "no_habitable",
      dictamen_status: reason === "no_habitable" ? "do_not_inhabit" : null,
      incident_id: "i-cerrado",
      reason,
    },
  };
}

describe("avisoDeReingreso — el motivo del servidor manda", () => {
  it("no_habitable ⇒ cartel ROJO, y el inmueble deja de poder decir SEGURO", () => {
    const aviso = avisoDeReingreso(estado("reentry_blocked", "no_habitable"));
    expect(aviso).toMatchObject({
      motivo: "no_habitable",
      tono: "crit",
      titulo: "REINGRESO NO AUTORIZADO",
      rotulo: "NO HABITABLE",
    });
    expect(aviso?.detalle).toMatch(/el dictamen indica NO HABITAR · INSPECCIÓN/);
  });

  it("pendiente_dictamen ⇒ franja ÁMBAR, y la tarjeta dice REINGRESO PENDIENTE", () => {
    expect(avisoDeReingreso(estado("reentry_blocked", "pendiente_dictamen"))).toMatchObject({
      motivo: "pendiente_dictamen",
      tono: "warn",
      titulo: "REINGRESO PENDIENTE DE DICTAMEN",
      rotulo: "REINGRESO PENDIENTE",
    });
  });

  it("pendiente_confirmacion ⇒ franja ÁMBAR «…DE CONFIRMACIÓN»", () => {
    expect(avisoDeReingreso(estado("reentry_blocked", "pendiente_confirmacion"))).toMatchObject({
      motivo: "pendiente_confirmacion",
      tono: "warn",
      titulo: "REINGRESO PENDIENTE DE CONFIRMACIÓN",
      rotulo: "REINGRESO PENDIENTE",
    });
  });

  it("bloqueado SIN motivo ⇒ aviso genérico, nunca SEGURO", () => {
    const entrada: Entrada = {
      phase: "shaking_concluded",
      reentry: {
        blocked: true,
        dictamen_signed: false,
        dictamen_status: null,
        incident_id: "i-abierto",
        reason: null,
      },
    };
    const aviso = avisoDeReingreso(entrada);
    expect(aviso).toMatchObject({ motivo: "desconocido", tono: "warn" });
    const seguro: HealthBanner = { label: "SEGURO", tone: "ok", detail: "gabinete vigilando" };
    expect(estadoDelInmueble(aviso, seguro).label).not.toBe("SEGURO");
  });

  it("reposo sin veredicto ⇒ ningún aviso", () => {
    expect(avisoDeReingreso(estado("idle", null))).toBeNull();
  });

  it("reingreso AUTORIZADO ⇒ ningún aviso de bloqueo (lo pinta el cartel verde)", () => {
    expect(avisoDeReingreso(estado("reentry_approved", null))).toBeNull();
  });
});

describe("avisoDeReingreso — el bloqueo es un hecho del EDIFICIO, no de la fase", () => {
  it("con la alarma del inmueble sonando, el NO HABITAR sigue viajando y se sigue pintando", () => {
    // La alarma del inmueble gana la precedencia de fase (suena AHORA), pero el
    // bloqueo dura días y el servidor lo sigue mandando en `reentry`.
    expect(avisoDeReingreso(estado("building_alarm", "no_habitable"))).toMatchObject({
      motivo: "no_habitable",
      tono: "crit",
    });
  });
});

describe("avisoDeReingreso — defensivo frente a un servidor más nuevo que la app", () => {
  it("fase reentry_blocked SIN motivo ⇒ franja ÁMBAR genérica, jamás silencio", () => {
    const aviso = avisoDeReingreso(estado("reentry_blocked", null));
    expect(aviso).toMatchObject({
      motivo: "desconocido",
      tono: "warn",
      rotulo: "REINGRESO BLOQUEADO",
    });
    expect(aviso?.titulo).toMatch(/REINGRESO/);
    // No inventa un dictamen que la app no ha visto.
    expect(`${aviso?.titulo} ${aviso?.detalle}`).not.toMatch(/NO HABITAR/);
  });

  it("un motivo que esta versión no conoce ⇒ la misma franja genérica", () => {
    const raro = estado("reentry_blocked", null);
    (raro.reentry as { reason: unknown }).reason = "motivo_del_futuro";
    expect(avisoDeReingreso(raro)).toMatchObject({ motivo: "desconocido", tono: "warn" });
  });

  it("sin `reason` en el objeto (servidor anterior a la fase) ⇒ se lee la fase", () => {
    const viejo: Entrada = {
      phase: "reentry_blocked",
      reentry: { blocked: true, dictamen_signed: false, dictamen_status: null },
    };
    expect(avisoDeReingreso(viejo)).toMatchObject({ motivo: "desconocido" });
  });
});

describe("estadoDelInmueble — ningún aviso de bloqueo convive con SEGURO", () => {
  const SEGURO: HealthBanner = { label: "SEGURO", tone: "ok", detail: "Monitoreo sísmico activo." };
  const DEGRADADO: HealthBanner = { label: "DEGRADADO", tone: "warn", detail: "métricas fuera" };
  const SIN_ENLACE: HealthBanner = { label: "SIN ENLACE", tone: "crit", detail: "no reporta" };
  const MOTIVOS = [
    "no_habitable",
    "pendiente_dictamen",
    "pendiente_confirmacion",
    "motivo_del_futuro",
  ] as const;

  it.each(
    MOTIVOS.flatMap((m) => [SEGURO, DEGRADADO, SIN_ENLACE].map((s) => [m, s.label, s] as const)),
  )("%s con el gabinete %s ⇒ la tarjeta NO afirma SEGURO", (motivo, _label, salud) => {
    const entrada = estado("reentry_blocked", null);
    (entrada.reentry as { reason: unknown }).reason = motivo;
    const aviso = avisoDeReingreso(entrada);
    expect(aviso).not.toBeNull();
    const tarjeta = estadoDelInmueble(aviso, salud);
    expect(tarjeta.label).not.toBe("SEGURO");
    expect(tarjeta.tone).not.toBe("ok");
    // El detalle del gabinete se conserva: sigue vigilando, o no.
    expect(tarjeta.detail).toBe(salud.detail);
  });

  it("pendiente con el gabinete sano ⇒ REINGRESO PENDIENTE en ámbar", () => {
    const aviso = avisoDeReingreso(estado("reentry_blocked", "pendiente_dictamen"));
    expect(estadoDelInmueble(aviso, SEGURO)).toEqual({
      label: "REINGRESO PENDIENTE",
      tone: "warn",
      detail: SEGURO.detail,
    });
  });

  it("pendiente con el gabinete SIN ENLACE ⇒ manda el gabinete: no se ablanda un rojo", () => {
    const aviso = avisoDeReingreso(estado("reentry_blocked", "pendiente_dictamen"));
    expect(estadoDelInmueble(aviso, SIN_ENLACE)).toEqual(SIN_ENLACE);
  });

  it("no_habitable manda sobre cualquier estado del gabinete", () => {
    const aviso = avisoDeReingreso(estado("reentry_blocked", "no_habitable"));
    expect(estadoDelInmueble(aviso, SIN_ENLACE)).toEqual({
      label: "NO HABITABLE",
      tone: "crit",
      detail: SIN_ENLACE.detail,
    });
  });

  it("sin aviso ⇒ el estado del gabinete tal cual", () => {
    expect(estadoDelInmueble(null, SEGURO)).toBe(SEGURO);
  });
});
