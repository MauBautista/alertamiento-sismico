// Contrato StateFrame: prioridad loading > error > empty > contenido(+stale).
import { render } from "@testing-library/react-native";
import { Text } from "react-native";

import { StateFrame } from "./StateFrame";
import { timeAgoLabel } from "./timeAgo";

const BASE = { empty: false, emptyText: "sin datos", staleSinceMs: null };
const CHILD = <Text>CONTENIDO</Text>;

describe("StateFrame — prioridad de estados", () => {
  it("loading gana a todo", async () => {
    const v = await render(
      <StateFrame {...BASE} loading={true} error="x" empty={true}>
        {CHILD}
      </StateFrame>,
    );
    expect(v.getByTestId("state-loading")).toBeTruthy();
    expect(v.queryByText("CONTENIDO")).toBeNull();
  });

  it("error sin datos: texto honesto, no spinner infinito", async () => {
    const v = await render(
      <StateFrame {...BASE} loading={false} error="intente de nuevo">
        {CHILD}
      </StateFrame>,
    );
    expect(v.getByTestId("state-error")).toBeTruthy();
    expect(v.getByText(/SIN CONEXIÓN/)).toBeTruthy();
  });

  it("empty declarado", async () => {
    const v = await render(
      <StateFrame {...BASE} loading={false} error={null} empty={true} emptyText="sin contactos">
        {CHILD}
      </StateFrame>,
    );
    expect(v.getByTestId("state-empty")).toBeTruthy();
    expect(v.getByText("sin contactos")).toBeTruthy();
  });

  it("stale: contenido VIEJO con banner DATOS RETENIDOS + edad honesta", async () => {
    const now = 1_800_000_000_000;
    const v = await render(
      <StateFrame
        {...BASE}
        loading={false}
        error={null}
        staleSinceMs={now - 7 * 60_000}
        nowMs={now}
      >
        {CHILD}
      </StateFrame>,
    );
    expect(v.getByText("CONTENIDO")).toBeTruthy();
    expect(v.getByTestId("state-stale")).toBeTruthy();
    expect(v.getByText(/DATOS RETENIDOS · hace 7 min/)).toBeTruthy();
  });

  it("fresco: contenido sin banner", async () => {
    const v = await render(
      <StateFrame {...BASE} loading={false} error={null}>
        {CHILD}
      </StateFrame>,
    );
    expect(v.getByText("CONTENIDO")).toBeTruthy();
    expect(v.queryByTestId("state-stale")).toBeNull();
  });
});

describe("timeAgoLabel", () => {
  const now = 1_800_000_000_000;
  it.each([
    [now - 30_000, "hace segundos"],
    [now - 5 * 60_000, "hace 5 min"],
    [now - 3 * 3_600_000, "hace 3 h"],
    [now - 2 * 86_400_000, "hace 2 d"],
    [now + 60_000, "hace segundos"], // reloj adelantado: jamás negativo
  ])("%d ⇒ %s", (since, expected) => {
    expect(timeAgoLabel(since as number, now)).toBe(expected);
  });
});
