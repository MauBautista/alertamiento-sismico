// [T-9.70 · D-50] El sonido OFICIAL del SASMEX en la APK, sin que entre al repositorio.
//
// Mauricio decidió el 2026-10-01 que SASMEX y el cuórum de red suenen con el oficial
// (del CIRES, sin licencia escrita: D-50 revoca en parte D-19 y D-40). El fichero vive
// en `audios/` del checkout principal y NUNCA se comitea; este plugin lo copia en el
// PREBUILD a `res/raw/alerta_oficial.wav`, el recurso al que apunta el canal
// `alerta_oficial_v1` (`src/services/push.ts`) y el bucle de la app (`sound.ts`).
//
// Sin el oficial —CI, un clon, la variable sin definir, otra huella— el recurso se
// llena con el TONO PROPIO y se dice. Nunca falta: un canal que apunta a un recurso
// inexistente suena el del sistema para siempre. Y como el canal guarda una REFERENCIA
// al recurso y no una copia, la siguiente APK con el oficial lo cambia sin reinstalar.
//
// Uso:  TAKAB_TONO_OFICIAL=<ruta>/audios/sasmex_oficial.wav npx expo prebuild --platform android
//
// CommonJS y sin TypeScript: lo carga `app.config.js` en node, fuera del bundle.
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

/** La huella del ÚNICO fichero que se empaqueta como oficial (la del manifiesto y la
 *  del gabinete: `tools/audio/oficial.py`). La comprueba `tests/tonoOficial.plugin.test.ts`. */
const SHA256_OFICIAL = "9b5e81de233a5736f0838f93550c5f03dffee1a5f0419aa194168d196a602896";
/** El MISMO nombre que `RECURSO_OFICIAL` de `src/services/tonoOficial.ts` (canal y bucle);
 *  la prueba del plugin los ata. */
const RECURSO = "alerta_oficial.wav";

function sha256(ruta) {
  return crypto.createHash("sha256").update(fs.readFileSync(ruta)).digest("hex");
}

/** Qué fichero va al recurso: `{ origen, ruta, motivo }`. */
function resolverTono({ fuente, propio, sha256: esperado = SHA256_OFICIAL }) {
  if (!fuente) {
    return { origen: "propio", ruta: propio, motivo: "TAKAB_TONO_OFICIAL no está definida" };
  }
  if (!fs.existsSync(fuente)) {
    return { origen: "propio", ruta: propio, motivo: `no existe ${path.basename(fuente)}` };
  }
  const real = sha256(fuente);
  if (real !== esperado) {
    return {
      origen: "propio",
      ruta: propio,
      motivo: `la huella de ${path.basename(fuente)} (${real.slice(0, 16)}) no es la auditada`,
    };
  }
  return { origen: "oficial", ruta: fuente, motivo: null };
}

/** Lo que trae el `android/` YA GENERADO: «oficial», «propio» o `null` si no hay
 *  (CI, jest, `expo export`). Se lee del recurso y no de la variable: la variable dice
 *  lo que se PIDIÓ en el prebuild, el recurso lo que de verdad se empaquetó. */
function tonoEmpaquetado(raizDelProyecto, esperado = SHA256_OFICIAL) {
  const ruta = path.join(raizDelProyecto, "android", "app", "src", "main", "res", "raw", RECURSO);
  if (!fs.existsSync(ruta)) {
    return null;
  }
  return sha256(ruta) === esperado ? "oficial" : "propio";
}

/** Al COMPILAR (Gradle evalúa `app.config.js` con `expo-constants/scripts/getAppConfig.js`)
 *  el recurso no puede faltar: un `android/` generado antes del plugin haría que la app
 *  creara `alerta_oficial_v1` con el tono propio, y el sonido de un canal es inmutable.
 *  Devuelve el motivo para frenar, o `null`. Fuera de Gradle —el propio prebuild, que es
 *  quien lo crea, `expo config`, CI— nunca frena. */
function compilacionSinRecurso(raizDelProyecto, script = process.argv[1]) {
  if (path.basename(script || "") !== "getAppConfig.js") {
    return null;
  }
  if (tonoEmpaquetado(raizDelProyecto) !== null) {
    return null;
  }
  return (
    `[tono oficial] android/ no trae res/raw/${RECURSO}: se generó antes del plugin. ` +
    "Repite el prebuild (TAKAB_TONO_OFICIAL=<ruta> npx expo prebuild --platform android) " +
    "antes de compilar: si no, el canal alerta_oficial_v1 nacería con el tono propio y " +
    "ninguna APK posterior podría cambiarlo."
  );
}

function withTonoOficial(config) {
  const { withDangerousMod } = require("expo/config-plugins");
  return withDangerousMod(config, [
    "android",
    async (cfg) => {
      const raw = path.join(cfg.modRequest.platformProjectRoot, "app", "src", "main", "res", "raw");
      fs.mkdirSync(raw, { recursive: true });
      const r = resolverTono({
        fuente: process.env.TAKAB_TONO_OFICIAL,
        propio: path.join(cfg.modRequest.projectRoot, "assets", "sounds", "alerta_sismica.wav"),
      });
      fs.copyFileSync(r.ruta, path.join(raw, RECURSO));
      if (r.origen === "oficial") {
        console.log(`[tono oficial] empaquetado (sha256 ${SHA256_OFICIAL.slice(0, 16)})`);
      } else {
        console.warn(
          `[tono oficial] NO empaquetado: ${r.motivo}. SASMEX y el cuórum sonarán con el tono propio.`,
        );
      }
      return cfg;
    },
  ]);
}

module.exports = withTonoOficial;
module.exports.resolverTono = resolverTono;
module.exports.tonoEmpaquetado = tonoEmpaquetado;
module.exports.compilacionSinRecurso = compilacionSinRecurso;
module.exports.SHA256_OFICIAL = SHA256_OFICIAL;
module.exports.RECURSO = RECURSO;
