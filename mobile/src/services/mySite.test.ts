import { siteFromScope } from "./mySite";

describe("siteFromScope — fallback táctico sin adivinar", () => {
  it("lista de sitios ⇒ el primero (selector fino en T-2.08)", () => {
    expect(siteFromScope(["s-1", "s-2"])).toBe("s-1");
  });

  it('"*" (todo el tenant) ⇒ null: no hay sitio único que vigilar', () => {
    expect(siteFromScope("*")).toBeNull();
  });

  it("vacío/ausente ⇒ null (default-deny, se declara)", () => {
    expect(siteFromScope([])).toBeNull();
    expect(siteFromScope(null)).toBeNull();
    expect(siteFromScope(undefined)).toBeNull();
  });
});
