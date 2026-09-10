/**
 * [T-6.25 · U-22] EL LATIDO SE CONSULTA CON EL SISTEMA.
 *
 * `AccessibilityInfo.isReduceMotionEnabled` existía desde T-6.19 y sólo lo
 * miraba la franja de avisos. Un punto que late es la afirmación más pequeña de
 * la app —«esto está llegando ahora»— y también la que más se repite; con la
 * reducción puesta se queda quieto y ENCENDIDO, porque apagarlo sería perder el
 * estado, no respetarlo.
 */
import { render } from "@testing-library/react-native";

import { LatidoPunto } from "./LatidoPunto";

let mockReduce = false;
jest.mock("@/ui/useReduceMotion", () => ({ useReduceMotion: () => mockReduce }));

beforeEach(() => {
  mockReduce = false;
});

describe("[T-6.25] el punto late sólo si puede y debe", () => {
  it("con dato fresco y sin preferencia, late", async () => {
    const v = await render(<LatidoPunto color="#0F0" late />);
    expect(v.getByTestId("live-latido")).toBeTruthy();
  });

  it("con MOVIMIENTO REDUCIDO no late, pero sigue ahí", async () => {
    mockReduce = true;
    const v = await render(<LatidoPunto color="#0F0" late />);
    expect(v.queryByTestId("live-latido")).toBeNull();
    // El punto NO desaparece: sigue diciendo el estado con su color.
    expect(v.getByTestId("live-punto")).toBeTruthy();
  });

  it("sin dato fresco no late aunque no haya preferencia", async () => {
    const v = await render(<LatidoPunto color="#FA0" late={false} />);
    expect(v.queryByTestId("live-latido")).toBeNull();
    expect(v.getByTestId("live-punto")).toBeTruthy();
  });
});
