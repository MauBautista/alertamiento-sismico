import { describe, expect, it } from "vitest";

import type { GatewayOut } from "@takab/sdk";

import { isVersionCierta, versionView } from "./VersionBadge";

// SHAs de 7 hex: el ÚNICO formato que produce `deploy/edge/deploy.sh`
// (`git describe --always --dirty --abbrev=7` sobre un repo sin tags).
const SHA = "62f3f1e";

function gw(over: Partial<GatewayOut> = {}): GatewayOut {
  return {
    gateway_id: "g-1",
    site_id: "s-1",
    site_name: "Planta Cholula",
    site_code: "CHL-A",
    site_status: "active",
    serial: "TKB-0001",
    fw_version: SHA,
    iot_thing: "gw-dev-0001",
    status: "active",
    has_wr1: true,
    installed_at: null,
    row_version: "1",
    derived_state: "OPERATIVO",
    version_state: "AL DÍA",
    releases_behind: 0,
    release_age_s: 7200,
    version_age_s: 42,
    ...over,
  };
}

describe("versionView · qué versión corre este gabinete [T-2.69]", () => {
  it("al día muestra la versión y la EDAD del dato, no su hora", () => {
    const view = versionView(gw());
    expect(view.tone).toBe("ok");
    expect(view.label).toContain(SHA);
    expect(view.label).toContain("AL DÍA");
    expect(view.title).toMatch(/42 s|hace 42/);
  });

  it("atrasada dice CUÁNTOS releases atrás y de cuándo es el código que corre", () => {
    const view = versionView(
      gw({ version_state: "ATRASADA", releases_behind: 3, release_age_s: 21 * 86_400 }),
    );
    expect(view.tone).toBe("warn");
    expect(view.label).toMatch(/3/);
    expect(view.title).toMatch(/21 d/);
  });

  // ---- EL CRITERIO 3: S/D cuando no se sabe -------------------------------

  it("SIN ENLACE jamás pinta la versión como actual, aunque sea la última publicada", () => {
    // El defecto del 14-jul en su forma de versiones: un gabinete callado tres
    // semanas pudo ser reflasheado, apagado o robado. Lo guardado es la última
    // versión QUE REPORTÓ.
    const view = versionView(
      gw({
        version_state: "ÚLTIMA CONOCIDA",
        releases_behind: 0,
        version_age_s: 21 * 86_400,
        derived_state: "SIN ENLACE",
      }),
    );
    expect(view.label).not.toContain("AL DÍA");
    expect(view.label).toMatch(/ÚLTIMA/);
    expect(view.label).toMatch(/21 d/); // la edad va EN EL RÓTULO, no escondida
    expect(view.tone).not.toBe("ok");
    expect(isVersionCierta("ÚLTIMA CONOCIDA")).toBe(false);
  });

  it("late y no declara versión ⇒ S/D, y NO la última conocida", () => {
    const view = versionView(gw({ version_state: "NO DECLARA", fw_version: SHA }));
    // El servidor ya puso `fw_version` a NULL al recibir el null explícito; aun
    // así la vista no puede depender de eso: si llegara un valor viejo, no se pinta.
    expect(view.label).not.toContain(SHA);
    expect(view.label).toContain("S/D");
    expect(view.tone).toBe("warn");
  });

  it("nunca reportó se distingue de dejó de declarar", () => {
    const nunca = versionView(gw({ version_state: "SIN REPORTAR", fw_version: null }));
    const dejo = versionView(gw({ version_state: "NO DECLARA", fw_version: null }));
    expect(nunca.label).not.toBe(dejo.label);
    expect(nunca.title).not.toBe(dejo.title);
  });

  it("una versión fuera del registro GRITA en vez de callarse", () => {
    const view = versionView(
      gw({ version_state: "DESCONOCIDA", fw_version: "62f3f1e-dirty", releases_behind: null }),
    );
    expect(view.tone).toBe("crit");
    expect(view.label).toContain("62f3f1e-dirty");
    expect(view.title).toMatch(/registro/i);
  });

  it("sin releases publicados no se acusa al gabinete de correr algo raro", () => {
    const view = versionView(
      gw({ version_state: "SIN REFERENCIA", releases_behind: null, release_age_s: null }),
    );
    expect(view.tone).toBe("idle");
    expect(view.label).toContain(SHA); // sí se sabe QUÉ corre
    expect(view.label).not.toContain("AL DÍA"); // no si es lo actual
  });

  // ---- el default ante lo desconocido es la peor causa, no la más benigna --

  it("un estado que esta versión de la consola no conoce NO se pinta como sano", () => {
    // Patrón 4 de la sesión: `RELÉS · S/D` decía "arranque en frío" mientras el
    // proceso que toca la sirena podía estar roto. Un servidor más nuevo que
    // añada un estado no puede colarlo como certeza.
    const view = versionView(gw({ version_state: "ALGO QUE NADIE HA ESCRITO AÚN" }));
    expect(view.tone).not.toBe("ok");
    expect(view.label).toContain("S/D");
    expect(isVersionCierta("ALGO QUE NADIE HA ESCRITO AÚN")).toBe(false);
  });

  it("la certeza se deriva por EXCLUSIÓN, no enumerando los estados dudosos", () => {
    expect(isVersionCierta("AL DÍA")).toBe(true);
    expect(isVersionCierta("ATRASADA")).toBe(true);
    expect(isVersionCierta("SIN REPORTAR")).toBe(false);
    expect(isVersionCierta("DESCONOCIDA")).toBe(false);
    expect(isVersionCierta(undefined)).toBe(false);
  });

  it("sin registro de releases la flota NO cuenta como certeza", () => {
    // Se sabe qué corre cada gabinete, pero no si eso es lo último. Contarlo como
    // certeza dejaría una plataforma que nunca publicó un release pintada como una
    // flota al día — un cero tranquilizador construido sobre un vacío.
    expect(isVersionCierta("SIN REFERENCIA")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// [T-2.70] ESCRITO ≠ CORRIENDO. `deploy.sh` escribe FW_VERSION antes de
// reiniciar, así que un despliegue que no llegó a reiniciar deja el SHA nuevo en
// el disco y el proceso con el viejo. El servidor lo llama SIN REINICIAR.
// ---------------------------------------------------------------------------

describe("versionView · el despliegue que se quedó a medias [T-2.70]", () => {
  const trabado = gw({
    version_state: "SIN REINICIAR",
    fw_version: "62f3f1e", // lo que dejó el rsync en el disco
    fw_running: "d082095", // lo que el proceso sigue ejecutando
    releases_behind: 1,
    release_age_s: 90_000,
  });

  it("no se pinta como al día ni se confunde con un estado desconocido", () => {
    const view = versionView(trabado);
    expect(view.tone).toBe("crit");
    expect(view.label).not.toContain("AL DÍA");
    expect(view.title).not.toContain("no reconocido");
  });

  it("enseña LOS DOS SHAs, porque la acción depende de cuál es cuál", () => {
    const view = versionView(trabado);
    expect(view.label).toContain("d082095"); // el que CORRE va en el rótulo
    expect(view.title).toContain("62f3f1e"); // el que espera en el disco
  });

  it("es un hecho CIERTO: se puede afirmar que NO corre el código actual", () => {
    // No es una forma de "no saber". Se sabe exactamente qué corre y que no es
    // lo publicado. Contarlo entre los desconocidos escondería un gabinete que
    // sí necesita acción concreta.
    expect(isVersionCierta("SIN REINICIAR")).toBe(true);
  });
});
