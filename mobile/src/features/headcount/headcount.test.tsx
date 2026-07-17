// 2.6 — clasificación del roster, filtro "no reportados", check-in delegado
// distinguible y cierre solo con todos contabilizados.
import type { RosterEntry, RosterOut } from "@takab/sdk";
import { fireEvent, render } from "@testing-library/react-native";

import { HeadcountView } from "./HeadcountView";
import { allAccounted, personState, rosterRows } from "./rosterView";

function entry(over: Partial<RosterEntry> = {}): RosterEntry {
  return {
    user_id: "u-1",
    display_name: "María Reyes",
    phone: "+525512848211",
    zone_id: "z-1",
    zone_name: "P10-A",
    checkin: null,
    ...over,
  };
}

function roster(entries: RosterEntry[]): RosterOut {
  const safe = entries.filter((e) => e.checkin?.status === "safe").length;
  const need = entries.filter((e) => e.checkin?.status === "need_help").length;
  return {
    incident_id: "i-1",
    site_id: "s-1",
    total: entries.length,
    safe,
    need_help: need,
    unreported: entries.length - safe - need,
    entries,
  };
}

const CB = {
  onToggleFilter: jest.fn(),
  onMarkVerified: jest.fn(),
  onNotifyUnreported: jest.fn(),
  onCloseHeadcount: jest.fn(),
};

describe("rosterView", () => {
  it("clasifica: sin check-in ⇒ unreported; safe/need_help por status", () => {
    expect(personState(entry())).toBe("unreported");
    expect(
      personState(entry({ checkin: { status: "safe", via: "self", created_at: "t", ts_device: null } })),
    ).toBe("safe");
    expect(
      personState(
        entry({ checkin: { status: "need_help", via: "self", created_at: "t", ts_device: null } }),
      ),
    ).toBe("need_help");
  });

  it("filtro 'no reportados' deja solo unreported; orden ayuda→sin reporte→salvo", () => {
    const r = roster([
      entry({ user_id: "safe", checkin: { status: "safe", via: "self", created_at: "t", ts_device: null } }),
      entry({ user_id: "unrep" }),
      entry({ user_id: "help", checkin: { status: "need_help", via: "self", created_at: "t", ts_device: null } }),
    ]);
    expect(rosterRows(r, true).map((x) => x.userId)).toEqual(["unrep"]);
    expect(rosterRows(r, false).map((x) => x.userId)).toEqual(["help", "unrep", "safe"]);
  });

  it("allAccounted solo si total>0 y sin no reportados", () => {
    expect(allAccounted(roster([entry()]))).toBe(false);
    expect(
      allAccounted(
        roster([entry({ checkin: { status: "safe", via: "self", created_at: "t", ts_device: null } })]),
      ),
    ).toBe(true);
    expect(allAccounted(roster([]))).toBe(false);
  });
});

describe("HeadcountView (2.6)", () => {
  it("marca 'verificado en persona' = check-in delegado del no reportado", async () => {
    const onMarkVerified = jest.fn();
    const v = await render(
      <HeadcountView
        {...CB}
        busy={false}
        live
        markingId={null}
        onMarkVerified={onMarkVerified}
        onlyUnreported
        roster={roster([entry({ user_id: "u-9" })])}
      />,
    );
    await fireEvent.press(v.getByTestId("verify-u-9"));
    expect(onMarkVerified).toHaveBeenCalledWith("u-9");
  });

  it("un check-in delegado se rotula 'verificado en persona'", async () => {
    const v = await render(
      <HeadcountView
        {...CB}
        busy={false}
        live
        markingId={null}
        onlyUnreported={false}
        roster={roster([
          entry({
            user_id: "u-2",
            checkin: { status: "safe", via: "delegated", created_at: "t", ts_device: null },
          }),
        ])}
      />,
    );
    expect(v.getByTestId("person-u-2")).toHaveTextContent(/verificado en persona/);
  });

  it("cerrar headcount deshabilitado con no reportados; el pill EN VIVO refleja el WS", async () => {
    const v = await render(
      <HeadcountView
        {...CB}
        busy={false}
        live
        markingId={null}
        onlyUnreported={false}
        roster={roster([entry()])}
      />,
    );
    expect(v.getByTestId("close-headcount")).toHaveTextContent("FALTAN POR CONTABILIZAR");
    expect(v.getByText("EN VIVO")).toBeTruthy();
  });
});
