// [T-9.62] El rótulo de una pestaña se ENCOGE hasta caber en su hueco; nunca se
// corta en «DIREC…». Visto en un Samsung A53 (1080 px) con las 8 del táctico.
/// <reference types="node" />
import { render } from "@testing-library/react-native";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { MIN_ESCALA_ROTULO, rotuloQueCabe } from "./rotuloQueCabe";

it("una sola línea que se encoge, con el color de la pestaña y el ancho del hueco", async () => {
  const Rotulo = rotuloQueCabe({ fontSize: 10, letterSpacing: 0.4 });
  const v = await render(
    <Rotulo color="#00BCD4" focused={false} position="below-icon">
      DIRECTORIO
    </Rotulo>,
  );
  const t = v.getByText("DIRECTORIO");
  expect(t.props.numberOfLines).toBe(1);
  expect(t.props.adjustsFontSizeToFit).toBe(true);
  expect(t.props.minimumFontScale).toBe(MIN_ESCALA_ROTULO);
  const estilo = Object.assign({}, ...[t.props.style].flat(3));
  expect(estilo).toMatchObject({ color: "#00BCD4", fontSize: 10, alignSelf: "stretch" });
});

it.each(["(brigadista)", "(occupant)"])(
  "la barra %s usa el rótulo que cabe (no el de serie, que recorta)",
  (grupo) => {
    const fuente = readFileSync(resolve(__dirname, `../app/${grupo}/_layout.tsx`), "utf8");
    expect(fuente).toMatch(/tabBarLabel:\s*rotuloQueCabe\(/);
  },
);
