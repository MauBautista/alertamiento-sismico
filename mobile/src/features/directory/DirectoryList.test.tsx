// 1.7 — agrupación por zona, llamada de un toque y "sin teléfono" honesto.
import type { DirectoryEntryOut } from "@takab/sdk";
import { fireEvent, render } from "@testing-library/react-native";
import { Linking } from "react-native";

import { DirectoryList, groupByZone } from "./DirectoryList";

const ENTRIES: DirectoryEntryOut[] = [
  {
    user_id: "u-1",
    display_name: "Brigada Uno",
    role: "brigadista",
    zone_id: "z-1",
    zone_name: "P10-A",
    phone: "+525511112222",
  },
  {
    user_id: "u-2",
    display_name: "Seguridad Norte",
    role: "security_guard",
    zone_id: null,
    zone_name: null,
    phone: null,
  },
];

describe("DirectoryList (1.7)", () => {
  it("agrupa por zona (sin zona ⇒ grupo SIN ZONA declarado)", () => {
    const groups = groupByZone(ENTRIES);
    expect(groups.map(([z]) => z)).toEqual(["P10-A", "SIN ZONA"]);
  });

  it("un toque llama; sin teléfono NO hay botón (se declara)", async () => {
    const spy = jest.spyOn(Linking, "openURL").mockResolvedValue(true);
    const v = await render(<DirectoryList entries={ENTRIES} />);
    await fireEvent.press(v.getByTestId("dir-call-u-1"));
    expect(spy).toHaveBeenCalledWith("tel:+525511112222");
    expect(v.queryByTestId("dir-call-u-2")).toBeNull();
    expect(v.getByText("sin teléfono")).toBeTruthy();
    spy.mockRestore();
  });
});
