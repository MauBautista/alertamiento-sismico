import { Outlet } from "react-router";

import Topbar from "./Topbar";

export default function AppShell() {
  return (
    <div className="soc-app">
      <Topbar />
      <main className="soc-main">
        <Outlet />
      </main>
    </div>
  );
}
