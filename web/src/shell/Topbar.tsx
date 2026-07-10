import { Cpu } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink } from "react-router";

import logoTakab from "../assets/LogoTakab2.png";
import { useSessionStore } from "../auth/session.store";
import { edgeMqttView, useLiveHealthStore } from "../live/liveHealth.store";
import { useNow } from "../lib/useNow";
import { navTabsFor } from "./navItems";
import OperatorMenu from "./OperatorMenu";

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

/** Pill del estado del canal live (T-1.49): icono+label, nunca solo color. */
function systemPill(status: "connecting" | "ready" | "closed"): {
  className: string;
  label: string;
} {
  switch (status) {
    case "ready":
      return { className: "soc-pill soc-pill--ok", label: "CONECTADO" };
    case "connecting":
      return { className: "soc-pill soc-pill--warn", label: "CONECTANDO…" };
    default:
      return { className: "soc-pill soc-pill--crit", label: "DESCONECTADO" };
  }
}

/** Port de Design System/jsx/Topbar.jsx sobre NavLink + allowed_routes del server. */
export default function Topbar() {
  const me = useSessionStore((s) => s.me);
  const liveStatus = useLiveHealthStore((s) => s.status);
  const heartbeats = useLiveHealthStore((s) => s.heartbeats);
  const [now, setNow] = useState(() => new Date());
  // Tick lento para re-evaluar staleness del heartbeat sin re-render por frame.
  const nowMs = useNow(5000);

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const clock = formatClock(now);
  const tabs = navTabsFor(me?.allowed_routes ?? []);
  const system = systemPill(liveStatus);
  const mqtt = edgeMqttView(heartbeats, nowMs);

  return (
    <header className="soc-topbar">
      <div className="soc-brand">
        <img src={logoTakab} alt="TAKAB TECHNOLOGY" className="soc-brand__logo" />
      </div>

      {/* Telemetría VIVA (T-1.49): estado del canal /ws + RTT MQTT del último
          heartbeat del edge. Sin heartbeat fresco (90 s) ⇒ S/D — jamás un
          número viejo congelado como fresco (regla de oro 7). */}
      <div className="soc-system">
        <span className="soc-meta">SISTEMA OPERATIVO</span>
        <span className={system.className} data-testid="system-pill">
          <span className="soc-dot" /> {system.label}
        </span>
        <span
          className={mqtt.rttMs !== null ? "soc-pill soc-pill--edge" : "soc-pill soc-pill--idle"}
          data-testid="mqtt-pill"
        >
          <Cpu size={12} />
          {mqtt.rttMs !== null ? `EDGE · MQTT ${mqtt.rttMs.toFixed(2)} ms` : "EDGE · MQTT · S/D"}
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

      <OperatorMenu />
    </header>
  );
}
