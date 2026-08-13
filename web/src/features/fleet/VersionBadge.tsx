// ¿Qué versión corre este gabinete, y desde cuándo lo sabemos? (T-2.69)
//
// El estado lo deriva el servidor (`schemas/fleet.py::derive_version_drift`) con el
// MISMO umbral de "vivo" que `derived_state` — aquí no hay una segunda opinión que
// pueda divergir. Esta vista solo pinta, y sobre todo distingue las cinco formas de
// NO saber qué corre, que antes se veían todas iguales (un `fw s/d` en minúsculas,
// o peor: la última versión conocida pintada como si fuera la actual):
//
//   AL DÍA           → corre el último release publicado, confirmado hace poco
//   ATRASADA         → corre código viejo, y se dice CUÁNTOS releases y de cuándo
//   ÚLTIMA CONOCIDA  → sin enlace: esto es lo que reportó, NO lo que corre
//   NO DECLARA       → late, y dice que no sabe qué versión corre
//   SIN REPORTAR     → nunca ha llegado un latido de este gabinete
//   DESCONOCIDA      → corre algo que no figura en el registro de releases
//   SIN REFERENCIA   → no hay releases publicados: no hay contra qué medir
//
// El caso que motiva todo esto es ÚLTIMA CONOCIDA. Un `fw_version` de hace tres
// semanas no es la versión que corre: es la última que reportó. Pintarla como
// actual es el defecto del 14-jul (15 h ciego con la consola en OPERATIVO) en su
// forma de versiones.

import type { GatewayOut } from "@takab/sdk";

import { ageLabel } from "../../lib/time";
import { SD } from "./estadoGlosario";

type Tone = "ok" | "warn" | "crit" | "idle";

export interface VersionView {
  label: string;
  tone: Tone;
  title: string;
}

/**
 * Los DOS únicos estados en los que la consola puede afirmar si este gabinete
 * corre o no el código actual.
 *
 * `SIN REFERENCIA` NO está aquí y es deliberado: sí se sabe qué corre, pero no si
 * eso es lo último (nadie ha publicado un release contra el que medirlo). Para la
 * pregunta de la tira de KPI —*¿puedo afirmar que esta flota corre lo actual?*—
 * la respuesta ahí es no, y contarlo como certeza dejaría una plataforma sin
 * registro pintada como una flota al día.
 */
const CIERTAS: ReadonlySet<string> = new Set(["AL DÍA", "ATRASADA", "SIN REINICIAR"]);

/**
 * [T-2.70] Estados en los que se sabe que el gabinete NO corre el código actual.
 *
 * Se deriva (certeza menos "AL DÍA") en vez de enumerarse: cualquier estado
 * futuro en el que se pueda afirmar la deriva entra solo. Enumerar dejaba fuera
 * a `SIN REINICIAR` sin que nada avisara, y un gabinete con el código nuevo
 * escrito y sin aplicar habría desaparecido de la cuenta de pendientes.
 */
export function isVersionAtrasada(state: string | undefined | null): boolean {
  return isVersionCierta(state) && state !== "AL DÍA";
}

/**
 * ¿Se puede afirmar si este gabinete corre el código actual?
 *
 * Se deriva por EXCLUSIÓN a propósito: un estado que esta consola no conozca
 * —porque el servidor es más nuevo— cae en "no se sabe", nunca en certeza. El
 * default ante lo desconocido tiene que ser la peor causa, no la más benigna.
 */
export function isVersionCierta(state: string | undefined | null): boolean {
  return state !== undefined && state !== null && CIERTAS.has(state);
}

export function versionView(gw: GatewayOut): VersionView {
  const version = gw.fw_version ?? null;
  const dataAge = ageLabel(gw.version_age_s);
  const releaseAge = ageLabel(gw.release_age_s);
  const behind = gw.releases_behind ?? null;

  switch (gw.version_state) {
    case "AL DÍA":
      return {
        label: `FW ${version} · AL DÍA`,
        tone: "ok",
        title:
          `Corre el último release publicado (hace ${releaseAge}). ` +
          `El gabinete lo confirmó hace ${dataAge}.`,
      };
    case "ATRASADA":
      return {
        label: `FW ${version} · ${behind ?? "?"} ATRÁS`,
        tone: "warn",
        title:
          `Corre código publicado hace ${releaseAge}; hay ${behind ?? "?"} release(s) ` +
          `posteriores. Confirmado por el gabinete hace ${dataAge}.`,
      };
    case "ÚLTIMA CONOCIDA":
      // El rótulo lleva la edad DENTRO, no en un tooltip: quien mira la reja de
      // tarjetas no pasa el ratón por cada una.
      return {
        label: `FW ${version} · ÚLTIMA CONOCIDA (${dataAge})`,
        tone: "warn",
        title:
          `El gabinete lleva ${dataAge} sin reportar. Esta es la última versión que ` +
          "declaró, NO necesariamente la que corre: desde entonces pudo ser " +
          "reflasheado, apagado o desmontado.",
      };
    case "NO DECLARA":
      return {
        label: `FW ${SD} · NO DECLARA`,
        tone: "warn",
        title:
          "El gabinete late pero declara que no sabe qué versión corre (falta su " +
          "archivo FW_VERSION: ¿un despliegue a medias, un reaprovisionamiento?). " +
          "No se muestra la última conocida porque ya no consta que sea la que corre.",
      };
    case "SIN REPORTAR":
      return {
        label: `FW ${SD} · SIN REPORTAR`,
        tone: "idle",
        title:
          "Nunca ha llegado un latido de este gabinete, así que nunca ha declarado " +
          "versión. Recién dado de alta, o jamás conectado.",
      };
    case "DESCONOCIDA":
      return {
        label: `FW ${version} · FUERA DE REGISTRO`,
        tone: "crit",
        title:
          `Corre "${version}", que no figura en el registro de releases: nadie publicó ` +
          "ese código. Suele ser un despliegue hecho con el árbol sucio (sufijo " +
          "-dirty) o desde una rama. No se puede decir cuánto está atrás.",
      };
    // [T-2.70] El despliegue escribió y no llegó a aplicarse. `crit` y no `warn`:
    // no es "código viejo" (eso es ATRASADA y se arregla desplegando) sino una
    // ORDEN QUE SE DIO Y NO SE CUMPLIÓ, y la causa probable es que la unidad no
    // arrancó. El rótulo lleva el SHA que CORRE, no el del disco: es el que
    // describe lo que protege el edificio ahora mismo.
    case "SIN REINICIAR":
      return {
        label: `FW ${gw.fw_running ?? "?"} · SIN REINICIAR`,
        tone: "crit",
        title:
          `El disco ya tiene "${version}" pero el proceso sigue ejecutando ` +
          `"${gw.fw_running ?? "?"}": el despliegue escribió el código y el reinicio no ` +
          "ocurrió, o falló. Comprueba `systemctl status takab-edge` en el gabinete — " +
          "una unidad que no arranca deja el edificio con el código anterior.",
      };
    case "SIN REFERENCIA":
      return {
        label: `FW ${version}`,
        tone: "idle",
        title:
          `El gabinete confirmó esta versión hace ${dataAge}, pero no hay releases ` +
          "publicados contra los que medir la deriva: se sabe qué corre, no si es lo actual.",
      };
    default:
      return {
        label: `FW ${SD}`,
        tone: "warn",
        title:
          `Estado de versión no reconocido por esta consola (${gw.version_state ?? "ausente"}). ` +
          "No se asume que esté al día.",
      };
  }
}

export default function VersionBadge({ gateway }: { gateway: GatewayOut }) {
  const view = versionView(gateway);
  return (
    <span
      className={`fleet-fw fleet-fw--${view.tone}`}
      title={view.title}
      data-testid="version-badge"
    >
      {view.label}
    </span>
  );
}
