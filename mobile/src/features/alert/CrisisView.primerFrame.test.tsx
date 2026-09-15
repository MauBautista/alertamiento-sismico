/**
 * [T-6.23] LOS CUATRO DATOS DE LA CRISIS, EN EL PRIMER FRAME.
 *
 * El principio 2 de la auditoría permite animar la ENTRADA DEL CONTENEDOR, y
 * sólo eso: el contenido tiene que estar pintado y legible desde el primer
 * frame. En una pantalla que le dice a alguien que evacúe, una instrucción que
 * llega desvaneciéndose es una instrucción que todavía no se puede leer.
 *
 * Lo que esto puede probar y lo que no, dicho sin adornos: `render` de RNTL 14
 * es ASÍNCRONO, así que desde aquí no se cuentan fotogramas. Lo que sí se ata
 * son las dos condiciones que juntas dan el resultado — que los cuatro datos
 * salen de PROPS (no de un efecto que llegue después) y que en el camino de
 * lectura no hay ni una animación que los pueda desvanecer. Con las dos, no hay
 * ningún frame en el que la pantalla esté montada y la instrucción no.
 */
/// <reference types="node" />
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render } from "@testing-library/react-native";

import { CrisisView } from "./CrisisView";
import { sourceLabel } from "./source";

const FUENTE = sourceLabel({ trigger: "sasmex" } as Parameters<typeof sourceLabel>[0]);

describe("[T-6.23] la crisis se lee desde el primer frame", () => {
  it("instrucción, zona, fuente y T+ salen de props, sin efectos de por medio", async () => {
    const v = await render(
      <CrisisView policy="evacuate" source={FUENTE} elapsedS={42} viva zoneName="Norte" />,
    );
    // Sin `act` ni avance de temporizadores: nada de esto depende de un efecto.
    expect(v.getByText(/EVACÚE/)).toBeTruthy();
    expect(v.getByText(/ZONA NORTE/)).toBeTruthy();
    expect(v.getByText(FUENTE.title)).toBeTruthy();
    expect(v.getByText(/T\+/)).toBeTruthy();
  });

  it("[T-6.25] y el CONTENEDOR tampoco: cero animaciones en `crisis.tsx`", () => {
    // Criterio explícito de T-6.25: la ficha del movimiento móvil no toca esta
    // pantalla. Es la única de la app donde una animación puede costar
    // segundos de lectura a alguien que tiene que salir del edificio.
    const ruta = readFileSync(resolve(__dirname, "..", "..", "app", "crisis.tsx"), "utf8");
    expect(ruta).not.toMatch(/\bAnimated\b/);
    expect(ruta).not.toMatch(/useSharedValue|withTiming|withSpring|entering=/);
  });

  it("[T-7.19 · D-30] lo ÚNICO que anima es el halo; el texto no se mueve", () => {
    // ⚠️ Esta prueba defendía el §5.3 del plan de reforma visual —«no animar
    // nada en el camino de lectura»—, que `D-30` REVOCA. Lo que aquella
    // prohibición protegía era la LECTURA, no la quietud, y eso es lo que se
    // sigue fijando aquí: la instrucción, el detalle y la fuente son `Text`
    // planos, y lo único envuelto en `Animated` es el anillo de la carcasa.
    //
    // Si mañana alguien envuelve la instrucción en un `Animated.Text`, el caso
    // de arriba seguiría verde —`render` devuelve el árbol, no los fotogramas—
    // y este barrido es la otra mitad.
    const fuente = readFileSync(resolve(__dirname, "CrisisView.tsx"), "utf8");
    // `expect` de jest NO admite mensaje (a diferencia de vitest): lo que
    // explica el fallo va en el comentario y en el nombre del caso.
    const animados = [...fuente.matchAll(/<Animated\.(\w+)/g)].map((m) => m[1]);
    expect(animados).toEqual(["View"]);
    // Y ese único `Animated.View` es el halo, no otra cosa.
    expect(fuente).toMatch(/testID="crisis-halo"/);
    // Reanimated sigue fuera: lo que falta aquí no es una librería (§5.4).
    expect(fuente).not.toMatch(/useSharedValue|withTiming|withSpring|entering=/);
  });
});
