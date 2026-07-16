// Pantalla 1.4: dos botones gigantes con transparencia de qué se enviará y
// estado posterior HONESTO (guardado local ≠ recibido por el servidor).
import { fireEvent, render } from "@testing-library/react-native";

import { CheckinStatusView, CheckinView } from "./CheckinView";

describe("CheckinView", () => {
  it("dos botones gigantes; el toque reporta el estado correcto", async () => {
    const onCheckin = jest.fn();
    const view = await render(
      <CheckinView busy={null} gpsConsent={false} onCheckin={onCheckin} zoneName="P10-A" />,
    );
    await fireEvent.press(view.getByTestId("btn-safe"));
    expect(onCheckin).toHaveBeenCalledWith("safe");
    await fireEvent.press(view.getByTestId("btn-need-help"));
    expect(onCheckin).toHaveBeenCalledWith("need_help");
  });

  it("transparencia: sin consentimiento el botón de ayuda declara SIN GPS", async () => {
    const view = await render(
      <CheckinView busy={null} gpsConsent={false} onCheckin={jest.fn()} zoneName="P10-A" />,
    );
    expect(view.getByText(/SIN GPS \(no dio consentimiento\)/)).toBeTruthy();
    expect(view.queryByText(/ubicación GPS actual/)).toBeNull();
  });

  it("transparencia: con consentimiento declara la ubicación GPS SOLO en ayuda", async () => {
    const view = await render(
      <CheckinView busy={null} gpsConsent={true} onCheckin={jest.fn()} zoneName="P10-A" />,
    );
    expect(view.getByText(/ubicación GPS actual/)).toBeTruthy();
    expect(view.getByText(/Sin ubicación/)).toBeTruthy(); // rama "estoy bien"
  });

  it("ocupado ⇒ botones deshabilitados (no doble check-in por doble toque)", async () => {
    const onCheckin = jest.fn();
    const view = await render(
      <CheckinView busy="safe" gpsConsent={false} onCheckin={onCheckin} zoneName={null} />,
    );
    await fireEvent.press(view.getByTestId("btn-need-help"));
    expect(onCheckin).not.toHaveBeenCalled();
  });
});

describe("CheckinStatusView — la verdad de dónde está el dato", () => {
  it("pendiente local ⇒ GUARDADO EN ESTE DISPOSITIVO (jamás finge envío)", async () => {
    const view = await render(<CheckinStatusView localState="pending" serverConfirmed={false} />);
    expect(view.getByTestId("checkin-status")).toHaveTextContent("GUARDADO EN ESTE DISPOSITIVO");
    expect(view.getByText(/se enviará AUTOMÁTICAMENTE en cuanto haya red/)).toBeTruthy();
  });

  it("synced o confirmado por el servidor ⇒ RECIBIDO POR EL SERVIDOR", async () => {
    const synced = await render(<CheckinStatusView localState="synced" serverConfirmed={false} />);
    expect(synced.getByTestId("checkin-status")).toHaveTextContent("RECIBIDO POR EL SERVIDOR");
    const server = await render(<CheckinStatusView localState={null} serverConfirmed={true} />);
    expect(server.getByTestId("checkin-status")).toHaveTextContent("RECIBIDO POR EL SERVIDOR");
  });
});
