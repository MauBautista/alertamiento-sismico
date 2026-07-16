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
    await fireEvent(v.getByTestId("consent-switch"), "valueChange", true);
    expect(onToggleConsent).toHaveBeenCalledWith(true);
    await fireEvent.press(v.getByTestId("logout"));
    expect(onLogout).toHaveBeenCalled();
  });
});
