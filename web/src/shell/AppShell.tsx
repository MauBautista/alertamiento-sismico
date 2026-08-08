import { Outlet } from "react-router";

import PrivacyConsentBanner from "../features/privacy/PrivacyConsentBanner";
import LiveSocketProvider from "../live/LiveSocketProvider";
import Topbar from "./Topbar";

export default function AppShell() {
  return (
    <LiveSocketProvider>
      <div className="soc-app">
        <Topbar />
        <main className="soc-main">
          {/* T-2.79: NO bloqueante y NO modal — se va solo cuando esta al dia. */}
          <PrivacyConsentBanner />
          <Outlet />
        </main>
      </div>
    </LiveSocketProvider>
  );
}
