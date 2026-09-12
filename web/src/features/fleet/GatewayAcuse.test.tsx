/**
 * [T-7.05 · C-4] EL ACUSE ES UN CALLEJÓN SIN SALIDA, Y TIENE QUE SERLO.
 *
 * Esta pantalla es el ÚNICO sitio del producto donde se imprimen los tres UUID que el
 * runbook manda pegar en `/etc/takab/edge.env` del Pi: no salen en la tabla de flota,
 * ni en la ficha del sitio, ni en el detalle del gabinete. Y no vuelve: `editing` es
 * estado local de `FleetAdmin`, así que basta con navegar una vez para que el acuse
 * desaparezca y los identificadores haya que ir a buscarlos a la base de datos — que
 * es literalmente lo que este acuse existe para evitar.
 *
 * El primer intento de `C-4` puso aquí el enlace a `/console?sitio=`, al lado de
 * CONTINUAR. Un clic de más y el alta se quedaba sin sensor y sin UUID. El enlace se
 * movió a `HardwareForm`, donde el alta ya terminó y no queda nada que perder
 * (`HardwareForm.test.tsx`). Lo que esta prueba defiende es esa decisión: si alguien
 * vuelve a colgar aquí una salida, se pone roja.
 */
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { GatewayRowOut } from "@takab/sdk";

import GatewayAcuse from "./GatewayAcuse";

const GATEWAY: GatewayRowOut = {
  gateway_id: "11111111-1111-4111-8111-111111111111",
  tenant_id: "22222222-2222-4222-8222-222222222222",
  site_id: "33333333-3333-4333-8333-333333333333",
  serial: "TKB-0007",
  fw_version: null,
  iot_thing: "gw-dev-0007",
  status: "provisioned",
  has_wr1: true,
  equipment: {
    siren: true,
    strobe: true,
    gas_valve: true,
    elevator: true,
    door_retainer: true,
  },
  installed_at: null,
  row_version: "1",
};

/**
 * Con `MemoryRouter` aunque hoy el acuse no navegue: sin él, colgar aquí un `<Link>`
 * haría REVENTAR la prueba («Cannot destructure property 'basename'») en vez de
 * declarar lo que pasa, y un rojo que no se lee se acaba borrando.
 */
function pintar(gateway: GatewayRowOut = GATEWAY) {
  return render(
    <MemoryRouter>
      <GatewayAcuse gateway={gateway} siteName="Torre E2E" onDone={vi.fn()} />
    </MemoryRouter>,
  );
}

describe("[T-7.05 · C-4] el acuse del gabinete", () => {
  it("imprime los identificadores DEL GABINETE que acaba de nacer", () => {
    pintar();
    const acuse = screen.getByTestId("gateway-acuse");
    // Los tres del `edge.env` más el serial: si uno dejara de pintarse, el runbook de
    // alta se queda sin su fuente y hay que volver a la base de datos.
    for (const valor of [
      GATEWAY.gateway_id,
      GATEWAY.site_id,
      GATEWAY.tenant_id,
      GATEWAY.serial,
      GATEWAY.iot_thing,
    ]) {
      expect(acuse).toHaveTextContent(String(valor));
    }
  });

  it("no ofrece NINGUNA salida de navegación: lo único que sale de aquí es CONTINUAR", () => {
    pintar();
    const acuse = screen.getByTestId("gateway-acuse");
    // `queryAllByRole("link")` cubre cualquier `<a href>` —un `<Link>` de react-router
    // lo es— y no depende del rótulo que se le ponga.
    expect(within(acuse).queryAllByRole("link")).toEqual([]);
    expect(within(acuse).getByRole("button", { name: "CONTINUAR" })).toBeInTheDocument();
  });
});
