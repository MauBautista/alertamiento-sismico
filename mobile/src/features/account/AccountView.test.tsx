// 1.8 — honestidad de cuenta: la fila TOTP OPCIONAL es SOLO del occupant (los
// tácticos tienen MFA obligatorio de pool); el consentimiento declara su
// efecto real en ambos estados.
import { fireEvent, render } from "@testing-library/react-native";

import { AccountView, type AccountProfile } from "./AccountView";

const PROFILE: AccountProfile = { displayName: "Ana", phone: "+525511112222" };

function props(over: Partial<Parameters<typeof AccountView>[0]> = {}) {
  return {
    role: "occupant",
    isOccupant: true,
    profile: PROFILE,
    onProfileChange: jest.fn(),
    onSaveProfile: jest.fn(),
    canSave: true,
    savingProfile: false,
    profileSavedAt: null,
    gpsConsent: false,
    onToggleConsent: jest.fn(),
    onOpenPermisos: jest.fn(),
    onOpenPrivacidad: jest.fn(),
    onOpenVincular: jest.fn(),
    onOpenContactos: jest.fn(),
    contactosCount: 2 as number | null,
    onLogout: jest.fn(),
    ...over,
  };
}

describe("AccountView (1.8)", () => {
  it("fila TOTP OPCIONAL: visible para occupant, AUSENTE para táctico", async () => {
    const occ = await render(<AccountView {...props()} />);
    expect(occ.getByTestId("totp-row")).toBeTruthy();
    const brig = await render(
      <AccountView {...props({ isOccupant: false, role: "brigadista" })} />,
    );
    expect(brig.queryByTestId("totp-row")).toBeNull();
  });

  it("[F2] la cabecera nombra el rol con su RÓTULO, no con el id crudo", async () => {
    const v = await render(<AccountView {...props({ isOccupant: false, role: "tenant_admin" })} />);
    expect(v.getByText("CUENTA · ADMINISTRADOR")).toBeTruthy();
    expect(v.queryByText("CUENTA · TENANT_ADMIN")).toBeNull();
  });

  it("consentimiento revocado: declara que se enviará zona SIN GPS", async () => {
    const v = await render(<AccountView {...props({ gpsConsent: false })} />);
    expect(v.getByTestId("consent-note")).toHaveTextContent(/su zona asignada, sin GPS/);
  });

  it("consentimiento vigente: declara que el GPS viaja SOLO al pedir auxilio", async () => {
    const v = await render(<AccountView {...props({ gpsConsent: true })} />);
    expect(v.getByTestId("consent-note")).toHaveTextContent(/SOLO en un check-in de auxilio/);
  });

  it("toggle y logout disparan sus callbacks", async () => {
    const onToggleConsent = jest.fn();
    const onLogout = jest.fn();
    const v = await render(<AccountView {...props({ onToggleConsent, onLogout })} />);
    // [T-6.20] Se PULSA LA FILA, que es lo que hace el dedo: el interruptor
    // quedó de indicador porque en Android un control nativo ignora el
    // `hitSlop` y 27 dp no son un objetivo táctil.
    await fireEvent.press(v.getByTestId("consent-switch"));
    expect(onToggleConsent).toHaveBeenCalledWith(true);
    await fireEvent.press(v.getByTestId("logout"));
    expect(onLogout).toHaveBeenCalled();
  });

  it("[T-9.80] CONTACTOS DE EMERGENCIA: la fila está para ocupante Y táctico, con N de 3", async () => {
    const onOpenContactos = jest.fn();
    const occ = await render(<AccountView {...props({ onOpenContactos })} />);
    expect(occ.getByTestId("contactos-row")).toHaveTextContent(/CONTACTOS DE EMERGENCIA/);
    expect(occ.getByTestId("contactos-row")).toHaveTextContent(/2 de 3/);
    await fireEvent.press(occ.getByTestId("contactos-row"));
    expect(onOpenContactos).toHaveBeenCalledTimes(1);

    const brig = await render(
      <AccountView {...props({ isOccupant: false, role: "brigadista", contactosCount: 0 })} />,
    );
    expect(brig.getByTestId("contactos-row")).toHaveTextContent(/0 de 3/);
  });

  it("[T-9.80] sin saber cuántos hay, la fila NO inventa un «0 de 3»", async () => {
    const v = await render(<AccountView {...props({ contactosCount: null })} />);
    expect(v.getByTestId("contactos-row")).not.toHaveTextContent(/de 3/);
  });
});
