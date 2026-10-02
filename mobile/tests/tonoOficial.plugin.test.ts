// [T-9.70 · D-50] El plugin de prebuild que mete el sonido OFICIAL en la APK sin que
// el fichero entre al repositorio. Lo que se prueba es lo que decide: QUÉ fichero
// acaba en `res/raw/alerta_oficial.wav` y qué dice la compilación de sí misma.
import { createHash } from "crypto";
import { mkdirSync, mkdtempSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";

import { RECURSO_OFICIAL } from "../src/services/tonoOficial";

// eslint-disable-next-line @typescript-eslint/no-require-imports
const plugin = require("../plugins/tonoOficial");

function fichero(dir: string, nombre: string, contenido: string): string {
  const ruta = join(dir, nombre);
  writeFileSync(ruta, contenido);
  return ruta;
}

function huella(contenido: string): string {
  return createHash("sha256").update(contenido).digest("hex");
}

describe("resolverTono", () => {
  const dir = mkdtempSync(join(tmpdir(), "tono-"));
  const propio = fichero(dir, "alerta_sismica.wav", "PROPIO");

  it("sin TAKAB_TONO_OFICIAL ⇒ el propio, y dice por qué", () => {
    const r = plugin.resolverTono({ fuente: undefined, propio });
    expect(r).toMatchObject({ origen: "propio", ruta: propio });
    expect(r.motivo).toMatch(/TAKAB_TONO_OFICIAL/);
  });

  it("la ruta no existe ⇒ el propio", () => {
    const r = plugin.resolverTono({ fuente: join(dir, "no-esta.wav"), propio });
    expect(r).toMatchObject({ origen: "propio", ruta: propio });
    expect(r.motivo).toMatch(/no existe/);
  });

  it("otra huella ⇒ el propio: sólo entra el fichero auditado", () => {
    const otro = fichero(dir, "otro.wav", "OTRO");
    const r = plugin.resolverTono({ fuente: otro, propio });
    expect(r).toMatchObject({ origen: "propio", ruta: propio });
    expect(r.motivo).toMatch(/huella/);
  });

  it("la huella auditada ⇒ el oficial", () => {
    const oficial = fichero(dir, "sasmex_oficial.wav", "OFICIAL");
    const r = plugin.resolverTono({ fuente: oficial, propio, sha256: huella("OFICIAL") });
    expect(r).toEqual({ origen: "oficial", ruta: oficial, motivo: null });
  });

  it("la huella por defecto es la del manifiesto (y la del gabinete)", () => {
    const manifiesto = require("../../shared/audio/MANIFEST.json");
    const entrada = manifiesto.audios.find((e: { id: string }) => e.id === "sasmex-oficial-v1");
    expect(plugin.SHA256_OFICIAL).toBe(entrada.sha256);
  });
});

describe("tonoEmpaquetado", () => {
  it("sin android/ generado ⇒ null (CI, jest, `expo export`)", () => {
    expect(plugin.tonoEmpaquetado(mkdtempSync(join(tmpdir(), "sin-android-")))).toBeNull();
  });

  it("con el recurso ⇒ «oficial» u «propio» según su huella", () => {
    const raiz = mkdtempSync(join(tmpdir(), "con-android-"));
    const raw = join(raiz, "android", "app", "src", "main", "res", "raw");
    mkdirSync(raw, { recursive: true });
    fichero(raw, "alerta_oficial.wav", "OFICIAL");
    expect(plugin.tonoEmpaquetado(raiz, huella("OFICIAL"))).toBe("oficial");
    expect(plugin.tonoEmpaquetado(raiz, huella("OTRA"))).toBe("propio");
  });
});

// [T-9.70] Un `android/` generado ANTES del plugin no trae el recurso, y Gradle volvía a
// evaluar `app.config.js` con `tonoOficial: null`: la app creaba `alerta_oficial_v1`
// con el tono propio y, como el sonido de un canal es inmutable, ninguna APK posterior
// lo arreglaba sin desinstalar (revisión adversarial). Al COMPILAR no puede faltar.
describe("compilacionSinRecurso", () => {
  function proyecto(conRecurso: boolean): string {
    const raiz = mkdtempSync(join(tmpdir(), "compila-"));
    const raw = join(raiz, "android", "app", "src", "main", "res", "raw");
    mkdirSync(raw, { recursive: true });
    if (conRecurso) {
      fichero(raw, "alerta_oficial.wav", "PROPIO");
    }
    return raiz;
  }
  const gradle = "/x/node_modules/expo-constants/scripts/getAppConfig.js";

  it("Gradle sobre un android/ sin el recurso ⇒ lo dice y manda repetir el prebuild", () => {
    expect(plugin.compilacionSinRecurso(proyecto(false), gradle)).toMatch(/expo prebuild/);
  });

  it("Gradle con el recurso (oficial o propio) ⇒ compila", () => {
    expect(plugin.compilacionSinRecurso(proyecto(true), gradle)).toBeNull();
  });

  it("fuera de Gradle (el propio prebuild, `expo config`, CI) ⇒ nunca frena", () => {
    expect(plugin.compilacionSinRecurso(proyecto(false), "/x/expo/bin/cli")).toBeNull();
    expect(plugin.compilacionSinRecurso(proyecto(false), undefined)).toBeNull();
  });
});

describe("un solo nombre de recurso", () => {
  it("el plugin escribe el mismo recurso que nombran el canal y el bucle", () => {
    expect(plugin.RECURSO).toBe(RECURSO_OFICIAL);
  });
});
