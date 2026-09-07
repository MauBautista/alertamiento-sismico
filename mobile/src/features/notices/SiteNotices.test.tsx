// [T-6.19] El contenedor cablea el mismo mobile-state que las pestañas, el
// inset del aparato y la preferencia de movimiento.
import type { MobileStateOut } from "@takab/sdk";
import { render } from "@testing-library/react-native";

import { SiteNotices } from "./SiteNotices";

let mockData: MobileStateOut | null = null;
jest.mock("@/features/alert/useAlertState", () => ({
  useAlertState: () => ({ data: mockData }),
}));
jest.mock("@/services/mySite", () => ({ useWatchedSiteId: () => "s-1" }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 42, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("@/ui/useReduceMotion", () => ({ useReduceMotion: () => true }));

describe("SiteNotices", () => {
  it("pinta el aviso del sitio vigilado con el inset del aparato", async () => {
    mockData = {
      demo_mode: false,
      drill: {
        active: false,
        next_scheduled_at: null,
        last_started_at: null,
        last_note: null,
        execution: "rejected",
        sites_total: 2,
        sites_executing: 0,
      },
    } as MobileStateOut;
    const v = await render(<SiteNotices />);
    expect(v.getByTestId("drill-banner")).toHaveTextContent(/NINGÚN GABINETE LO EJECUTA/);
    const style = Object.assign(
      {},
      ...[v.getByTestId("site-notices").props.style].flat(Infinity).filter(Boolean),
    );
    expect(style.paddingTop).toBe(42);
  });

  it("sin dato no pinta nada", async () => {
    mockData = null;
    const v = await render(<SiteNotices />);
    expect(v.queryByTestId("site-notices")).toBeNull();
  });
});
