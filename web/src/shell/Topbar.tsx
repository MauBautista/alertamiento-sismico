import { Cpu, LogOut } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink } from "react-router";

import logoTakab from "../assets/LogoTakab2.png";
import { useSessionStore } from "../auth/session.store";
import { navTabsFor } from "./navItems";

/** Reloj SOC. CST fijo vía America/Mexico_City (México abolió el DST en 2022). */
function formatClock(now: Date): { utc: string; cst: string; date: string } {
  return {
    utc: now.toISOString().slice(11, 19),
    cst: now.toLocaleTimeString("en-GB", { timeZone: "America/Mexico_City", hour12: false }),
    date: now
      .toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        timeZone: "America/Mexico_City",
      })
      .toUpperCase(),
  };
}

/** Port de Design System/jsx/Topbar.jsx sobre NavLink + allowed_routes del server. */
export default function Topbar() {
  const me = useSessionStore((s) => s.me);
  const logout = useSessionStore((s) => s.logout);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const clock = formatClock(now);
  const tabs = navTabsFor(me?.allowed_routes ?? []);

  return (
    <header className="soc-topbar">
      <div className="soc-brand">
        <img src={logoTakab} alt="TAKAB TECHNOLOGY" className="soc-brand__logo" />
      </div>

      {/* La telemetría real llega en T-1.27: estado neutral explícito ("SIN
          DATOS"), nunca CONECTADO fingido (regla de oro #7). */}
      <div className="soc-system">
        <span className="soc-meta">SISTEMA OPERATIVO</span>
        <span className="soc-pill soc-pill--idle">
          <span className="soc-dot" /> SIN DATOS
        </span>
        <span className="soc-pill soc-pill--idle">
          <Cpu size={12} /> EDGE · MQTT · SIN DATOS
        </span>
      </div>

      <nav className="soc-nav" aria-label="Primary">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <NavLink
              key={tab.path}
              to={tab.path}
              className={({ isActive }) => `soc-nav__tab${isActive ? " is-active" : ""}`}
            >
              <Icon size={14} />
              {tab.label}
            </NavLink>
          );
        })}
      </nav>

      <div className="soc-clock" aria-label="System time">
        <span className="meta">UTC</span>
        <span>{clock.utc}</span>
        <span className="sep">|</span>
        <span className="meta">CST</span>
        <span>{clock.cst}</span>
        <span className="sep">|</span>
        <span>{clock.date}</span>
      </div>

      <div className="soc-user">
        <span className="soc-meta">{me?.role ?? ""}</span>
        <button
          type="button"
          className="soc-icon-btn"
          aria-label="Cerrar sesión"
          onClick={() => void logout()}
        >
          <LogOut size={14} />
        </button>
      </div>
    </header>
  );
}
