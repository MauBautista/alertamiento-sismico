/**
 * Los iconos de la app son los de MARCA, y cumplen las reglas de cada tienda.
 *
 * POR QUÉ ESTE TEST EXISTE
 * ------------------------
 * Los iconos son lo único del producto que nadie prueba y todo el mundo ve. Se
 * generan con `shared/brand/generar.py` a partir de los maestros, y las reglas
 * que se comprueban aquí no son estéticas: cada una tiene un fallo caro detrás.
 *
 * - **Alfa en el icono de iOS ⇒ la App Store RECHAZA el envío**, y el correo
 *   llega días después de subirlo. Se comprueba el tipo de color del PNG.
 * - **1024×1024 exacto** es lo que pide el envío de iOS.
 * - **Las capas del icono adaptativo de Android tienen tamaños fijos** (512 y
 *   432): si una llega con otro tamaño, el sistema la escala y el recorte deja
 *   de caer donde se calculó.
 *
 * Se leen las CABECERAS del PNG a mano (no hace falta ninguna dependencia): la
 * cabecera IHDR trae ancho, alto y tipo de color en bytes fijos. Eso acota lo
 * que este test puede afirmar: **NO mira los píxeles**, así que no comprueba la
 * zona segura del 66 % de Android ni que el arte sea el correcto — eso lo fija
 * `shared/brand/generar.py` (ocupación 0.52) y se revisa a ojo.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

const IMAGENES = join(__dirname, "..", "assets", "images");

/** Tipos de color del PNG (IHDR byte 25). 6 = RGBA, 2 = RGB sin alfa. */
const RGB_SIN_ALFA = 2;
const RGBA = 6;

function cabecera(nombre: string) {
  const crudo = readFileSync(join(IMAGENES, nombre));
  expect(crudo.subarray(0, 8)).toEqual(
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  );
  return {
    crudo,
    ancho: crudo.readUInt32BE(16),
    alto: crudo.readUInt32BE(20),
    tipoDeColor: crudo.readUInt8(25),
  };
}

describe("iconos de marca de la app", () => {
  it("el icono de iOS mide 1024 y NO lleva canal alfa (la App Store lo rechazaría)", () => {
    const { ancho, alto, tipoDeColor } = cabecera("icon.png");
    expect([ancho, alto]).toEqual([1024, 1024]);
    expect(tipoDeColor).toBe(RGB_SIN_ALFA);
  });

  it("las capas del icono adaptativo de Android tienen el tamaño que pide el sistema", () => {
    expect(cabecera("android-icon-foreground.png")).toMatchObject({
      ancho: 512,
      alto: 512,
      tipoDeColor: RGBA,
    });
    expect(cabecera("android-icon-background.png")).toMatchObject({
      ancho: 512,
      alto: 512,
    });
    expect(cabecera("android-icon-monochrome.png")).toMatchObject({
      ancho: 432,
      alto: 432,
      tipoDeColor: RGBA,
    });
  });

  it("el favicon y el splash existen y son PNG", () => {
    expect(cabecera("favicon.png")).toMatchObject({ ancho: 48, alto: 48 });
    expect(cabecera("splash-icon.png").ancho).toBeGreaterThanOrEqual(76);
  });

  it("ningún icono es un fichero vacío ni un stub de un puñado de bytes", () => {
    for (const nombre of [
      "icon.png",
      "android-icon-foreground.png",
      "splash-icon.png",
    ]) {
      expect(cabecera(nombre).crudo.byteLength).toBeGreaterThan(1000);
    }
  });

  it("iOS no vuelve a caer en el icono de la PLANTILLA de Expo", () => {
    // `ios.icon` apuntaba a `./assets/expo.icon` —el bundle de Icon Composer que
    // trae la plantilla— y MANDA sobre `icon.png`: mientras estuvo ahí, cambiar
    // el PNG no cambiaba nada en iOS y no lo delataba ningún test.
    const app = JSON.parse(
      readFileSync(join(__dirname, "..", "app.json"), "utf8"),
    );
    expect(app.expo.ios.icon).toBeUndefined();
    expect(app.expo.icon).toBe("./assets/images/icon.png");
  });
});
