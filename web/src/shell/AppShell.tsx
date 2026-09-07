import { Outlet } from "react-router";

import PrivacyConsentBanner from "../features/privacy/PrivacyConsentBanner";
import SceneStrip from "../features/scene/SceneStrip";
import LiveSocketProvider from "../live/LiveSocketProvider";
import Topbar from "./Topbar";

export default function AppShell() {
  return (
    <LiveSocketProvider>
      <div className="soc-app">
        <Topbar />
        <main className="soc-main">
          {/* [T-6.01] La ESCENA va primera, en el DOM y en la reja: una alerta
              se lee antes que un aviso legal. En escena NORMAL mide cero. */}
          <SceneStrip />
          {/* T-2.79: NO bloqueante y NO modal — se va solo cuando esta al dia. */}
          <PrivacyConsentBanner />
          <Outlet />
        </main>
      </div>
    </LiveSocketProvider>
  );
}
