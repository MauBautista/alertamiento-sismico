import { FileSearch, Radar, Server, Shield } from "lucide-react";

export interface NavTab {
  path: string;
  label: string;
  icon: typeof Radar;
}

/** Presentación de los tabs top-level. La AUTORIZACIÓN nunca sale de aquí:
 * el armado por rol es `allowed_routes` del server ∩ este mapa, en el orden
 * del server. /building/:siteId no es tab (se entra por deep-link). */
const NAV_PRESENTATION: ReadonlyMap<string, Omit<NavTab, "path">> = new Map([
  ["/console", { label: "CONSOLA C4I", icon: Radar }],
  ["/fleet", { label: "FLOTA EDGE", icon: Server }],
  ["/triage", { label: "TRIAGE", icon: FileSearch }],
  ["/tenants", { label: "MULTI-TENANT", icon: Shield }],
]);

export function navTabsFor(allowedRoutes: readonly string[]): NavTab[] {
  const tabs: NavTab[] = [];
  for (const route of allowedRoutes) {
    const item = NAV_PRESENTATION.get(route);
    if (item) {
      tabs.push({ path: route, ...item });
    }
  }
  return tabs;
}
