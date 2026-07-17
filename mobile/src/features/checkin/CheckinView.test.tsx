// Pantalla 1.4: dos botones gigantes con transparencia de qué se enviará.
// (El estado posterior vive en 1.5 — features/reentry, con su timeline.)
import { fireEvent, render } from "@testing-library/react-native";

import { CheckinView } from "./CheckinView";

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

