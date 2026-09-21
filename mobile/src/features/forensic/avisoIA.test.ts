// [T-7.27 · D-32] EL AVISO DE QUE LA FOTO PUEDE SALIR DEL INMUEBLE.
//
// `D-32` decidió que la capa narrativa vea **las fotos del reporte de daños**:
// se envían a OpenRouter (Estados Unidos) y al proveedor del modelo. Quien
// fotografía un daño tiene derecho a saberlo ANTES de disparar, y el único
// aviso que había en esta pantalla —«METADATOS RETENIDOS»— habla de otra cosa:
// de la edad del dato con el que se sella, no de a dónde va la imagen.
//
// Este archivo prueba EL TEXTO, que es lo único que la persona lee. Que el
// aviso esté en pantalla y en qué momento lo prueba `tests/app/camera-states`;
// que NO entre en el pixel ni en el manifiesto lo prueba `watermark.test.ts`.
import { AVISO_IA_ALCANCE, AVISO_IA_LIMITE, AVISO_IA_TITULO, avisoIALineas } from "./avisoIA";

describe("[T-7.27] el aviso dice lo que pasa, sin prometer de más", () => {
  const texto = () => avisoIALineas().join(" ");

  it("dice PUEDE, no DICE que ya está pasando", () => {
    // La capa narrativa está APAGADA por defecto y se enciende por despliegue
    // (`TAKAB_API_OPENROUTER_ENABLED`, T-7.26). Un aviso en indicativo —«esta
    // foto se envía»— sería falso en todos los sitios que no la tengan
    // encendida, y un aviso falso gasta la credibilidad del que sí importa.
    expect(AVISO_IA_TITULO).toMatch(/PUEDE/);
    expect(texto()).not.toMatch(/\bse enviará\b/i);
  });

  it("nombra lo que la persona no puede deducir: que sale de México y a quién", () => {
    // Sin esto el aviso no avisa de nada: «se procesa con IA» deja creer que
    // ocurre dentro del mismo sistema donde ya viven sus datos.
    expect(texto()).toMatch(/FUERA DE MÉXICO/);
    expect(texto()).toMatch(/inteligencia artificial/i);
    expect(texto()).toMatch(/inmueble/i);
  });

  it("declara la REGLA DE ORO 1: la IA no decide nada", () => {
    // La prosa jamás toca el veredicto (`tests/narrative/test_contract.py`).
    // Si el brigadista cree que la máquina clasifica el daño que fotografía,
    // el aviso le ha enseñado el sistema al revés.
    expect(AVISO_IA_LIMITE).toMatch(/NO DECIDE/);
    expect(texto()).toMatch(/no clasifica/i);
    expect(texto()).toMatch(/no firma/i);
  });

  it("dice lo que HOY viaja: la imagen sí, el sello no, y nada de anonimato", () => {
    // ⚠️ Esta guarda fijaba la frase contraria —exigía «marca de agua» en el
    // aviso— y era correcta hasta el 2026-09-21: la banda horneada con hora,
    // GPS e identificador de operador viajaba dentro del JPEG. `T-7.27` la
    // TAPA antes de salir (`api/src/takab_api/narrative/marca.py`), así que
    // seguir exigiéndola habría dejado al aviso mintiéndole al brigadista en
    // la pantalla donde consiente. Una guarda que fija una frase que dejó de
    // ser verdad defiende el defecto, que es lo que este repositorio ya midió
    // en `test_cap_CERO_significa_sin_tope_no_tope_cero`.
    //
    // Lo que se afirma ahora, y muerde por los DOS lados:

    // 1 · La imagen SALE. Prometer que no viaja nada sería mentir sobre la
    //     propia pieza que se manda.
    expect(texto()).toMatch(/fuera de méxico/i);
    expect(texto()).not.toMatch(/an[oó]nim/i);

    // 2 · El sello NO sale, y el aviso lo dice. Si alguien quita el tapado del
    //     servidor, esta línea se queda mintiendo — y por eso el lado de `api/`
    //     tiene su propia guarda sobre los píxeles del cuerpo real
    //     (`test_la_marca_no_viaja_en_el_pixel.py`): son las dos mitades del
    //     mismo trato y ninguna basta sola.
    expect(AVISO_IA_ALCANCE).toMatch(/sin el sello/i);
    expect(AVISO_IA_ALCANCE).toMatch(/identificador de operador/i);

    // 3 · Y lo que nunca viajó tampoco se calla. Se comprueba el HECHO —que
    //     nombre y teléfono se nombran como lo que NO sale— y no una redacción
    //     concreta: la frase exacta ya cambió una vez en esta misma ficha, y
    //     una guarda atada a la letra obliga a tocarla cada vez que alguien
    //     mejora el texto, que es como se acaba tocando la guarda sin pensar.
    expect(texto()).toMatch(/(ni su|tampoco viajan su)[^.]*nombre/i);
    expect(texto()).toMatch(/tel[eé]fono/i);
  });

  it("son TRES líneas y ninguna está vacía: nada de deslindes escondidos", () => {
    // La lección de T-2.104 que ya cita `watermark.ts`: lo que se lee primero
    // manda, y un deslinde detrás de un «ver más» no deslinda.
    const lineas = avisoIALineas();
    expect(lineas).toHaveLength(3);
    expect(lineas.every((l) => l.trim().length > 0)).toBe(true);
    expect(lineas[0]).toBe(AVISO_IA_TITULO);
  });
});
