// app/screens/Profile1.jsx
// PROFILE 1 · Personal del Inmueble (Ocupante / Empleado)
// Design directive: zero cognitive load, one-tap UI, oversized text.
// Five screens covering the full lifecycle: REST → CRISIS → POST-EVENT.

// =====================================================================
// SCREEN 1.1 — Modo Reposo (day-to-day, building safe)
// =====================================================================
const OcupanteReposo = () => (
  <Phone profile="ocupante" active="inicio" notif={true}>
    {/* Hero: building safe */}
    <div className="safe-hero">
      <div className="safe-hero__eyebrow">
        <span style={{ width: 7, height: 7, borderRadius: 999, background: 'var(--tk-status-normal)', display: 'inline-block', boxShadow: '0 0 0 3px rgba(0,230,118,0.20)' }} />
        EDIFICIO · ESTADO
      </div>
      <h1 className="safe-hero__title">Seguro</h1>
      <div className="safe-hero__site">Planta Cholula · Edif. A</div>

      <div className="safe-hero__meta">
        <div className="safe-hero__metaitem">
          <div className="lbl">Su piso</div>
          <div className="val">10 · ZONA REPLIEGUE</div>
        </div>
        <div className="safe-hero__metaitem">
          <div className="lbl">Última verif.</div>
          <div className="val">10:41:08 CST</div>
        </div>
        <div className="safe-hero__metaitem">
          <div className="lbl">Sensor RS4D</div>
          <div className="val" style={{ color: 'var(--tk-status-normal)' }}>● EN LÍNEA</div>
        </div>
        <div className="safe-hero__metaitem">
          <div className="lbl">SASMEX</div>
          <div className="val" style={{ color: 'var(--tk-status-normal)' }}>● ENLAZADO</div>
        </div>
      </div>
    </div>

    <div className="t-section">Brigadistas de su piso</div>
    <div>
      <div className="dir-row">
        <div className="dir-row__avatar">JL</div>
        <div>
          <div className="dir-row__name">Jorge Lozano</div>
          <div className="dir-row__role">JEFE DE BRIGADA · P10</div>
        </div>
        <div className="dir-row__phone"><i data-lucide="phone" width="16" height="16" /></div>
      </div>
      <div className="dir-row">
        <div className="dir-row__avatar">AM</div>
        <div>
          <div className="dir-row__name">Ana Mendoza</div>
          <div className="dir-row__role">PRIMEROS AUXILIOS · P10</div>
        </div>
        <div className="dir-row__phone"><i data-lucide="phone" width="16" height="16" /></div>
      </div>
    </div>

    <div className="t-section" style={{ marginTop: 4 }}>Próximo simulacro</div>
    <div className="drill">
      <div className="drill__date">
        <div className="d">19</div>
        <div className="m">SEP</div>
      </div>
      <div className="drill__main">
        <div className="drill__title">Simulacro nacional · 11:00 hrs</div>
        <div className="drill__meta">Evacuación total · Punto de reunión P-2</div>
      </div>
      <span className="drill__tag pill pill--cyan">PROG.</span>
    </div>
    <div className="drill">
      <div className="drill__date">
        <div className="d">02</div>
        <div className="m">JUN</div>
      </div>
      <div className="drill__main">
        <div className="drill__title">Repliegue interno · Su piso</div>
        <div className="drill__meta">Completado · Tiempo 1:42</div>
      </div>
      <span className="drill__tag pill pill--ok">OK</span>
    </div>

    <div className="t-section" style={{ marginTop: 4 }}>Recursos</div>
    <div className="card" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, padding: 8, background: 'transparent', border: 'none' }}>
      <div className="card" style={{ padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
        <i data-lucide="map" width="20" height="20" style={{ color: 'var(--tk-cyan)' }} />
        <div>
          <div style={{ fontSize: 12, fontWeight: 600 }}>Ruta de evacuación</div>
          <div style={{ fontSize: 10, color: 'var(--tk-fg-3)', fontFamily: 'var(--tk-font-mono)', marginTop: 2 }}>P10 · PDF 1.2 MB</div>
        </div>
      </div>
      <div className="card" style={{ padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
        <i data-lucide="book-open" width="20" height="20" style={{ color: 'var(--tk-cyan)' }} />
        <div>
          <div style={{ fontSize: 12, fontWeight: 600 }}>Manual operativo</div>
          <div style={{ fontSize: 10, color: 'var(--tk-fg-3)', fontFamily: 'var(--tk-font-mono)', marginTop: 2 }}>Versión 3.1</div>
        </div>
      </div>
    </div>
  </Phone>
);

// =====================================================================
// SCREEN 1.2 — Crisis: EVACÚE AHORA (zonas con evac_policy = evacuate)
// Full-screen takeover, instruction-first (spec §2.1-A). El WR-1 entrega
// un booleano: sin magnitud, sin epicentro, sin cuenta regresiva. El dato
// temporal honesto es el T+ transcurrido desde la recepción de la alerta.
// =====================================================================
const OcupanteCrisisEvac = () => (
  <Phone profile="ocupante" hideChrome={true}>
    <div className="crisis">
      <div className="crisis__strip">
        <div className="crisis__strip-eyebrow">● Alerta sísmica activa</div>
        <div className="crisis__strip-title">Alerta Sísmica SASMEX</div>
      </div>
      <div className="crisis__body">
        <div className="crisis__action crisis__action--hero">
          <div className="crisis__action-eyebrow">— SU INSTRUCCIÓN —</div>
          <div className="crisis__instruction crisis__instruction--hero">
            Evacúe<br />ahora
          </div>
          <div className="crisis__detail">
            Diríjase a la escalera <strong style={{ color: '#fff' }}>norte</strong>.<br />
            No use elevadores.
          </div>
          <div className="crisis__floor">
            <i data-lucide="building-2" width="14" height="14" /> Piso 02 · Salida planta baja
          </div>
        </div>

        <div className="crisis__elapsed">
          <div className="crisis__t-eyebrow">Tiempo transcurrido desde la alerta</div>
          <div className="crisis__tplus">
            T+04<span className="unit">s</span>
          </div>
          <div className="crisis__source">
            <i data-lucide="radio-tower" width="12" height="12" /> Fuente · SASMEX WR-1
          </div>
        </div>
      </div>
    </div>
    <span className="home-indicator" />
  </Phone>
);

// =====================================================================
// SCREEN 1.3 — Crisis: REPLIÉGUESE (zonas con evac_policy = shelter, ámbar)
// Same instruction-first blueprint as 1.2 (spec §2.1-A). Upper-floor
// occupants shelter in place rather than evacuate.
// =====================================================================
const OcupanteCrisisReplie = () => (
  <Phone profile="ocupante" hideChrome={true}>
    <div className="crisis crisis--amber">
      <div className="crisis__strip">
        <div className="crisis__strip-eyebrow">● Alerta sísmica activa</div>
        <div className="crisis__strip-title">Alerta Sísmica SASMEX</div>
      </div>
      <div className="crisis__body">
        <div className="crisis__action crisis__action--hero">
          <div className="crisis__action-eyebrow" style={{ color: 'rgba(255,220,150,0.7)' }}>— SU INSTRUCCIÓN —</div>
          <div className="crisis__instruction crisis__instruction--hero crisis__instruction--amber" style={{ fontSize: 58 }}>
            Repliéguese
          </div>
          <div className="crisis__detail" style={{ color: 'rgba(255,240,200,0.85)' }}>
            Zona de seguridad <strong style={{ color: '#fff' }}>P10-A</strong>.<br />
            Aléjese de ventanas y cristales.
          </div>
          <div className="crisis__floor" style={{ borderColor: 'rgba(255,193,7,0.30)', color: 'rgba(255,240,200,0.85)' }}>
            <i data-lucide="building-2" width="14" height="14" /> Piso 10 · Núcleo estructural
          </div>
        </div>

        <div className="crisis__elapsed" style={{ borderTopColor: 'rgba(255,193,7,0.18)' }}>
          <div className="crisis__t-eyebrow" style={{ color: 'rgba(255,220,150,0.7)' }}>Tiempo transcurrido desde la alerta</div>
          <div className="crisis__tplus">
            T+04<span className="unit">s</span>
          </div>
          <div className="crisis__source">
            <i data-lucide="radio-tower" width="12" height="12" /> Fuente · SASMEX WR-1
          </div>
        </div>
      </div>
    </div>
    <span className="home-indicator" />
  </Phone>
);

// =====================================================================
// SCREEN 1.4 — Post-sismo · Check-in de vida
// Two huge buttons; the only thing that exists on this screen.
// =====================================================================
const OcupanteCheckin = () => (
  <Phone profile="ocupante" hideChrome={true}>
    <div className="checkin">
      <div className="checkin__head">
        <div className="checkin__eyebrow">⬢ Movimiento concluido · 14:35 CST</div>
        <div className="checkin__title">¿Está usted bien?</div>
        <div className="checkin__sub">
          Su respuesta llega al SOC y a los brigadistas de su piso.<br />
          Esto toma un segundo. Hágalo ahora.
        </div>
      </div>
      <div className="checkin__body">
        <button className="checkin__btn checkin__btn--safe">
          <div className="lead">Estoy<br />a salvo</div>
          <div className="desc">Estoy fuera del edificio o en zona de seguridad sin lesiones.</div>
          <div className="arrow"><i data-lucide="chevron-right" width="28" height="28" /></div>
        </button>
        <button className="checkin__btn checkin__btn--help">
          <div className="lead">Necesito<br />ayuda</div>
          <div className="desc">Envía su última ubicación GPS y piso al equipo de brigada.</div>
          <div className="arrow"><i data-lucide="chevron-right" width="28" height="28" /></div>
        </button>

        <div className="card card--flat" style={{ marginTop: 4, padding: '12px 14px' }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <i data-lucide="map-pin" width="16" height="16" style={{ color: 'var(--tk-cyan)' }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 10, letterSpacing: '0.12em', color: 'var(--tk-fg-3)', textTransform: 'uppercase' }}>Ubicación que se enviará</div>
              <div style={{ fontFamily: 'var(--tk-font-mono)', fontSize: 11, color: 'var(--tk-fg-1)', marginTop: 2, letterSpacing: '0.02em' }}>
                19.0589° N · 98.2997° W · ±6m · P10
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <span className="home-indicator" />
  </Phone>
);

// =====================================================================
// SCREEN 1.5 — Bloqueo de reingreso (after check-in)
// Hold-state until Protección Civil or Jefe de Brigada lifts the lock.
// =====================================================================
const OcupanteBloqueo = () => (
  <Phone profile="ocupante" active="inicio">
    <div className="reing">
      <div className="reing__eyebrow">
        <i data-lucide="alert-octagon" width="14" height="14" /> Reingreso prohibido
      </div>
      <h1 className="reing__title">Evaluación estructural en curso</h1>
      <div className="reing__body">
        No reingrese al edificio. La brigada está evaluando daños en cada piso. Recibirá una notificación oficial cuando el dictamen sea firmado.
      </div>
      <div className="reing__progress">
        <div className="reing__step is-done">
          <div className="marker" />
          <div className="reing__step__main">
            <div className="reing__step__title">Evento registrado</div>
            <div className="reing__step__meta">14:35:20 · PGA 0.150g</div>
          </div>
        </div>
        <div className="reing__step is-done">
          <div className="marker" />
          <div className="reing__step__main">
            <div className="reing__step__title">Su check-in recibido</div>
            <div className="reing__step__meta">14:38:11 · Estoy a salvo · P-2</div>
          </div>
        </div>
        <div className="reing__step is-current">
          <div className="marker" />
          <div className="reing__step__main">
            <div className="reing__step__title">Inspección por piso · 6 de 10</div>
            <div className="reing__step__meta">Brigada P10 · est. 12 min</div>
          </div>
        </div>
        <div className="reing__step">
          <div className="marker" />
          <div className="reing__step__main">
            <div className="reing__step__title">Dictamen técnico · inspector</div>
            <div className="reing__step__meta">Pendiente</div>
          </div>
        </div>
        <div className="reing__step">
          <div className="marker" />
          <div className="reing__step__main">
            <div className="reing__step__title">Reingreso autorizado</div>
            <div className="reing__step__meta">—</div>
          </div>
        </div>
      </div>
    </div>

    <div className="t-section">Mantente en…</div>
    <div className="card">
      <div className="card__hd">
        <div className="card__title">Punto de reunión P-2</div>
        <span className="pill pill--ok"><span className="pill__dot" /> ACTIVO</span>
      </div>
      <div style={{ display: 'flex', gap: 10 }}>
        <div style={{
          width: 60, height: 60, borderRadius: 8,
          background: 'var(--tk-surface-2)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--tk-cyan)',
        }}>
          <i data-lucide="map-pin" width="22" height="22" />
        </div>
        <div style={{ flex: 1, fontSize: 12, color: 'var(--tk-fg-2)', lineHeight: 1.5 }}>
          Estacionamiento exterior, costado sur.<br />
          <span style={{ color: 'var(--tk-fg-3)', fontFamily: 'var(--tk-font-mono)', fontSize: 11 }}>
            ≈ 80m de la salida principal
          </span>
        </div>
      </div>
    </div>

    <div className="card" style={{ background: 'transparent', borderStyle: 'dashed' }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
        <i data-lucide="info" width="16" height="16" style={{ color: 'var(--tk-fg-3)', marginTop: 2 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, color: 'var(--tk-fg-1)', fontWeight: 500 }}>¿Cuándo podré reingresar?</div>
          <div style={{ fontSize: 11, color: 'var(--tk-fg-3)', marginTop: 4, lineHeight: 1.5 }}>
            Cuando el ingeniero a cargo firme el dictamen electrónico en el SOC.
            Su teléfono vibrará y sonará el toque oficial.
          </div>
        </div>
      </div>
    </div>
  </Phone>
);

Object.assign(window, {
  OcupanteReposo, OcupanteCrisisEvac, OcupanteCrisisReplie,
  OcupanteCheckin, OcupanteBloqueo,
});
