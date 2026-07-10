import { Outlet } from "react-router";

import LiveSocketProvider from "../live/LiveSocketProvider";
import Topbar from "./Topbar";

export default function AppShell() {
  return (
    <LiveSocketProvider>
      <div className="soc-app">
        <Topbar />
        <main className="soc-main">
          <Outlet />
        </main>
      </div>
    </LiveSocketProvider>
  );
}
