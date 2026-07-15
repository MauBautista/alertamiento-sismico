// app/screens/Profile2.jsx
// PROFILE 2 · Brigadista / Personal de Seguridad
// Design directive: situational awareness + forensic data collection.
// Direct counterpart to the SOC web console's Triage tab.

// =====================================================================
// SCREEN 2.1 — Dashboard Táctico Local (cabinet health + BMS + remote)
// =====================================================================
const BrigadistaPanel = () => (
  <Phone profile="brigadista" active="panel" notif={true}>
    <div className="tactical-banner">
      <div className="tactical-banner__icon">
        <i data-lucide="cpu" width="18" height="18" />
      </div>
      <div className="tactical-banner__main">
        <div className="tactical-banner__lbl">Gabinete · CHL-A-EDIFA</div>
        <div className="tactical-banner__val">EDGE · MQTT · enlazado</div>
      </div>
      <span className="pill pill--ok"><span className="pill__dot" /> OK</span>
    </div>

    <div className="t-section">Salud del hardware</div>
    <div className="statgrid">
      <div className="statcell statcell--ok">
        <div className="statcell__lbl">UPS Batería</div>
        <div className="statcell__val">96<span style={{ fontSize: 13, color: 'var(--tk-fg-3)' }}>%</span></div>
        <div className="statcell__sub statcell__sub--ok">▲ 48 min autonomía</div>
      </div>
      <div className="statcell statcell--ok">
        <div className="statcell__lbl">MQTT · RTT</div>
        <div className="statcell__val">77<span style={{ fontSize: 13, color: 'var(--tk-fg-3)' }}>ms</span></div>
        <div className="statcell__sub statcell__sub--ok">● NTP −0.2 ms</div>
      </div>
      <div className="statcell">
        <div className="statcell__lbl">RS4D · sensor</div>
        <div className="statcell__val" style={{ color: 'var(--tk-status-normal)' }}>LIVE</div>
        <div className="statcell__sub">100 sps · 4 canales</div>
      </div>
      <div className="statcell statcell--warn">
        <div className="statcell__lbl">Temp. interior</div>
        <div className="statcell__val">38<span style={{ fontSize: 13, color: 'var(--tk-fg-3)' }}>°C</span></div>
        <div className="statcell__sub statcell__sub--warn">▲ Ventilar gabinete</div>
      </div>
    </div>

    <div className="t-section">Actuadores BMS · post-evento</div>
    <div className="card">
      <div className="bms-row">
        <div className="bms-row__icon bms-row__icon--ok">
          <i data-lucide="bell-ring" width="14" height="14" />
        </div>
        <div>
          <div className="bms-row__label">Sirenas locales</div>
          <div className="bms-row__sub">RELAY-01 · 14:35:22</div>
        </div>
        <span className="pill pill--ok">ACTIVAS</span>
      </div>
      <div className="bms-row">
        <div className="bms-row__icon bms-row__icon--ok">
          <i data-lucide="flame" width="14" height="14" />
        </div>
        <div>
          <div className="bms-row__label">Válvulas de gas</div>
          <div className="bms-row__sub">BAC-V42 / V43 · 14:35:22</div>
        </div>
        <span className="pill pill--ok">CERRADAS</span>
      </div>
      <div className="bms-row">
        <div className="bms-row__icon bms-row__icon--ok">
          <i data-lucide="door-open" width="14" height="14" />
        </div>
        <div>
          <div className="bms-row__label">Retenedores de puerta</div>
          <div className="bms-row__sub">8/8 · todos los pisos</div>
        </div>
        <span className="pill pill--ok">LIBRES</span>
      </div>
      <div className="bms-row">
        {/* lucide no tiene "elevator" (slot vacío en el diseño original) */}
        <div className="bms-row__icon bms-row__icon--warn">
          <i data-lucide="arrow-up-down" width="14" height="14" />
        </div>
        <div>
          <div className="bms-row__label">Elevadores · llamada PB</div>
          <div className="bms-row__sub">E-01 OK · E-02 sin respuesta</div>
        </div>
        <span className="pill pill--warn">REVISAR</span>
      </div>
    </div>

    <div className="t-section">Acciones rápidas</div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div className="swipe">
        <div className="swipe__progress" style={{ width: 28 }} />
        <div className="swipe__thumb">
          <i data-lucide="volume-x" width="20" height="20" />
        </div>
        <div className="swipe__track">Deslice → Silenciar sirena</div>
      </div>
      <div className="swipe swipe--danger">
        <div className="swipe__thumb">
          <i data-lucide="alert-triangle" width="20" height="20" />
        </div>
        <div className="swipe__track">Deslice → Disparo manual</div>
      </div>
    </div>
  </Phone>
);

// =====================================================================
// SCREEN 2.2 — Control Remoto Edge · armed confirmation
// Showing the swipe-to-confirm interaction in its "armed" mid-state.
// =====================================================================
const BrigadistaControlRemoto = () => (
  <Phone profile="brigadista" active="panel">
    <div className="card" style={{
      background: 'rgba(255,82,82,0.08)',
      border: '1px solid var(--tk-status-critical)',
      padding: 14,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <i data-lucide="shield-alert" width="20" height="20" style={{ color: 'var(--tk-status-critical)' }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, letterSpacing: '0.14em', color: 'var(--tk-status-critical)', fontWeight: 700, textTransform: 'uppercase' }}>
            Control remoto · 2 pasos
          </div>
          <div style={{ fontSize: 12, color: 'var(--tk-fg-2)', marginTop: 4, lineHeight: 1.4 }}>
            Sólo brigadistas autorizados. Las acciones quedan registradas y firmadas.
          </div>
        </div>
      </div>
    </div>

    <div className="t-section">Acción seleccionada</div>
    <div className="card card--cyan">
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <div style={{
          width: 44, height: 44, borderRadius: 8,
          background: 'var(--tk-cyan-15)', color: 'var(--tk-cyan)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flex: '0 0 44px',
        }}>
          <i data-lucide="volume-x" width="22" height="22" />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Silenciar sirena local</div>
          <div style={{ fontSize: 11, color: 'var(--tk-fg-3)', marginTop: 4, fontFamily: 'var(--tk-font-mono)' }}>
            CHL-A · RELAY-01 · zona evacuada
          </div>
          <div style={{
            marginTop: 10, paddingTop: 10,
            borderTop: '1px solid var(--tk-border)',
            fontSize: 11, color: 'var(--tk-fg-2)', lineHeight: 1.5,
          }}>
            Use sólo cuando todos los ocupantes hayan salido del edificio.
            La acción es <strong style={{ color: 'var(--tk-fg-1)' }}>reversible</strong> con autorización del SOC.
          </div>
        </div>
      </div>
    </div>

    <div className="t-section">Paso 1 · Confirmación</div>
    <div className="card" style={{ padding: 14 }}>
      <div style={{ display: 'grid', gap: 10 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <div style={{
            width: 22, height: 22, borderRadius: 999,
            background: 'var(--tk-status-normal)', color: '#062f17',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 12, fontWeight: 700,
          }}>
            <i data-lucide="check" width="14" height="14" />
          </div>
          <div style={{ flex: 1, fontSize: 13 }}>Edificio evacuado confirmado</div>
          <span className="pill pill--ok" style={{ fontSize: 9 }}>OK</span>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <div style={{
            width: 22, height: 22, borderRadius: 999,
            background: 'var(--tk-status-normal)', color: '#062f17',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <i data-lucide="check" width="14" height="14" />
          </div>
          <div style={{ flex: 1, fontSize: 13 }}>Headcount completo (8/8 pisos)</div>
          <span className="pill pill--ok" style={{ fontSize: 9 }}>OK</span>
        </div>
      </div>
    </div>

    <div className="t-section">Paso 2 · Deslice para activar</div>
    <div className="swipe" style={{ height: 64 }}>
      <div className="swipe__progress" style={{ width: 180 }} />
      <div className="swipe__thumb" style={{ width: 56, height: 56, left: 132 }}>
        <i data-lucide="volume-x" width="22" height="22" />
      </div>
      <div className="swipe__track" style={{ fontSize: 13, color: 'var(--tk-cyan)' }}>Mantener →</div>
    </div>

    <div style={{
      fontSize: 10, color: 'var(--tk-fg-3)', textAlign: 'center',
      fontFamily: 'var(--tk-font-mono)', letterSpacing: '0.04em', marginTop: 4,
    }}>
      OPERADOR: M.RODRÍGUEZ · FIRMA HW · NONCE VÁLIDO 02:41
    </div>
  </Phone>
);

// =====================================================================
// SCREEN 2.3 — Cámara Forense con marca de agua inalterable
// Live viewfinder; watermark is BAKED into the captured pixel.
// =====================================================================
const BrigadistaCamara = () => (
  <Phone profile="brigadista" hideChrome={true}>
    <div className="cam">
      {/* Viewfinder background — simulated photo of a cracked column */}
      <div className="cam__viewport">
        <svg
          className="cam__crack"
          viewBox="0 0 374 540"
          preserveAspectRatio="xMidYMid slice"
        >
          {/* Concrete column silhouette */}
          <rect x="100" y="0" width="170" height="540" fill="#3a3633" />
          <rect x="100" y="0" width="170" height="540" fill="url(#gritGrad)" />
          {/* Floor */}
          <rect x="0" y="430" width="374" height="110" fill="#1a1816" />
          <defs>
            <linearGradient id="gritGrad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="rgba(255,255,255,0.08)" />
              <stop offset="0.5" stopColor="rgba(255,255,255,0)" />
              <stop offset="1" stopColor="rgba(0,0,0,0.3)" />
            </linearGradient>
            <pattern id="noise" patternUnits="userSpaceOnUse" width="4" height="4">
              <rect width="4" height="4" fill="#3a3633" />
              <circle cx="1" cy="1" r="0.3" fill="rgba(255,255,255,0.04)" />
              <circle cx="3" cy="3" r="0.3" fill="rgba(0,0,0,0.18)" />
            </pattern>
          </defs>
          {/* Rebar exposed cracks */}
          <path d="M 165 90 Q 168 160 158 220 Q 152 280 168 340 Q 175 400 162 480"
                stroke="#0a0907" strokeWidth="4" fill="none" strokeLinecap="round" />
          <path d="M 158 220 Q 144 232 132 248" stroke="#0a0907" strokeWidth="2.5" fill="none" />
          <path d="M 168 340 Q 184 350 196 364" stroke="#0a0907" strokeWidth="3" fill="none" />
          <path d="M 162 480 Q 150 490 134 502" stroke="#0a0907" strokeWidth="2" fill="none" />
          {/* spall */}
          <path d="M 200 200 Q 220 210 226 232 Q 232 252 216 268 Q 200 280 188 270 L 200 200 Z"
                fill="rgba(0,0,0,0.5)" />
          <path d="M 200 200 Q 220 210 226 232" stroke="rgba(255,200,180,0.18)" strokeWidth="1.2" fill="none" />
          {/* AR measurement overlay */}
          <g stroke="rgba(0,191,255,0.85)" fill="none" strokeWidth="1.5">
            <line x1="158" y1="220" x2="220" y2="220" />
            <line x1="158" y1="215" x2="158" y2="225" />
            <line x1="220" y1="215" x2="220" y2="225" />
          </g>
          <text x="190" y="212" fontFamily="JetBrains Mono, monospace" fontSize="11"
                fill="#00BFFF" textAnchor="middle">12.4 cm</text>
        </svg>

        {/* Top status bar — recording chip + close */}
        <div className="cam__topbar">
          <span className="cam__pill"><span className="dot" /> CAPTURA FORENSE</span>
          <span className="cam__pill">⬢ GPS · ±4m</span>
        </div>

        {/* Reticle */}
        <svg className="cam__reticle" viewBox="0 0 374 540" preserveAspectRatio="none">
          {/* corner brackets */}
          <g stroke="rgba(255,255,255,0.55)" strokeWidth="1.5" fill="none">
            <path d="M 30 70 L 30 50 L 50 50" />
            <path d="M 344 70 L 344 50 L 324 50" />
            <path d="M 30 360 L 30 380 L 50 380" />
            <path d="M 344 360 L 344 380 L 324 380" />
          </g>
        </svg>

        {/* Inalterable watermark — baked into the pixel */}
        <div className="cam__brand-watermark">
          <div className="cam__wm-grid">
            <span className="cam__wm-lbl">UTC</span><span className="cam__wm-val">2026-05-14 · 14:42:08</span>
            <span className="cam__wm-lbl">GPS</span><span className="cam__wm-val">19.0589°N · 98.2997°W</span>
            <span className="cam__wm-lbl">PGA</span><span className="cam__wm-val">0.150g · CHL-A</span>
            <span className="cam__wm-lbl">OP</span><span className="cam__wm-val">BRIG-04 · J. LOZANO</span>
          </div>
          <div className="cam__wm-stamp">
            <i data-lucide="shield-check" width="11" height="11" />
            SHA-256
          </div>
        </div>
      </div>

      {/* Camera controls */}
      <div className="cam__controls">
        <button className="cam__tag">
          <i data-lucide="folder" width="22" height="22" />
        </button>
        <button className="cam__shutter" />
        <button className="cam__tag">
          <i data-lucide="flashlight" width="22" height="22" />
        </button>
      </div>
    </div>
    <span className="home-indicator" />
  </Phone>
);

// =====================================================================
// SCREEN 2.4 — Formulario Rápido de Daños
// Quick triage form; ties each entry to the camera shot + GPS.
// =====================================================================
const BrigadistaFormulario = () => (
  <Phone profile="brigadista" active="triage">
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <div>
        <div className="t-eyebrow">EVT-20260514-1435 · P-10 · A</div>
        <div style={{ fontSize: 18, fontWeight: 600, marginTop: 2, letterSpacing: '-0.01em' }}>
          Reporte de daños
        </div>
      </div>
      <span className="pill pill--cyan">3 / 12</span>
    </div>

    {/* Photo strip from the camera */}
    <div className="card" style={{ padding: 10 }}>
      <div className="card__hd" style={{ marginBottom: 8 }}>
        <div className="card__title" style={{ fontSize: 12 }}>Evidencia · 3 fotos</div>
        <span className="card__sub">14:42:08 → 14:43:51</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
        {[1,2,3].map(i => (
          <div key={i} style={{
            aspectRatio: '1', borderRadius: 4,
            background: 'linear-gradient(135deg,#1a1a1a,#3a3633)',
            position: 'relative', overflow: 'hidden',
            border: '1px solid var(--tk-border)',
          }}>
            <svg viewBox="0 0 40 40" preserveAspectRatio="xMidYMid slice" style={{ width: '100%', height: '100%' }}>
              <rect x="14" y="0" width="12" height="40" fill="#3a3633" />
              <path d={`M ${15 + i*2} 0 Q ${17 + i*2} 14 ${13 + i*2} 24 Q ${10 + i*2} 32 ${15 + i*2} 40`} stroke="#0a0907" strokeWidth="1.2" fill="none" />
            </svg>
            <div style={{
              position: 'absolute', bottom: 2, left: 3, right: 3,
              fontFamily: 'var(--tk-font-mono)', fontSize: 6.5,
              color: 'rgba(255,255,255,0.85)', letterSpacing: '0.02em',
            }}>14:4{1+i} · ±4m</div>
          </div>
        ))}
        <button style={{
          aspectRatio: '1', borderRadius: 4,
          background: 'var(--tk-cyan-08)', border: '1px dashed var(--tk-cyan)',
          color: 'var(--tk-cyan)', display: 'flex',
          alignItems: 'center', justifyContent: 'center',
          cursor: 'pointer',
        }}>
          <i data-lucide="plus" width="20" height="20" />
        </button>
      </div>
    </div>

    <div className="t-section">Categoría · marca todas las que apliquen</div>

    <div>
      <div className="form-check is-crit">
        <div className="form-check__box" />
        <div>
          <div className="form-check__main">Daño estructural</div>
          <div className="form-check__sub">Columnas · muros de carga · trabes</div>
        </div>
        <span className="form-check__sev pill pill--crit">CRÍT</span>
      </div>
      <div className="form-check is-on">
        <div className="form-check__box" />
        <div>
          <div className="form-check__main">Daño no estructural</div>
          <div className="form-check__sub">Plafones · cristales · acabados</div>
        </div>
        <span className="form-check__sev pill pill--warn">MED</span>
      </div>
      <div className="form-check is-on">
        <div className="form-check__box" />
        <div>
          <div className="form-check__main">Fuga · agua</div>
          <div className="form-check__sub">Localizada en cuarto de máquinas</div>
        </div>
        <span className="form-check__sev pill pill--warn">MED</span>
      </div>
      <div className="form-check">
        <div className="form-check__box" />
        <div>
          <div className="form-check__main">Fuga · gas</div>
          <div className="form-check__sub">Olor / detector activado</div>
        </div>
        <span className="form-check__sev pill pill--crit">CRÍT</span>
      </div>
      <div className="form-check">
        <div className="form-check__box" />
        <div>
          <div className="form-check__main">Daño eléctrico</div>
          <div className="form-check__sub">Tablero · chispa · pérdida de fase</div>
        </div>
        <span className="form-check__sev pill pill--crit">CRÍT</span>
      </div>
      <div className="form-check">
        <div className="form-check__box" />
        <div>
          <div className="form-check__main">Personas atrapadas / heridas</div>
          <div className="form-check__sub">Reportar conteo y ubicación</div>
        </div>
        <span className="form-check__sev pill pill--crit">911</span>
      </div>
    </div>

    <div style={{ display: 'flex', gap: 8 }}>
      <button className="btn btn--ghost" style={{ flex: 1 }}>
        <i data-lucide="save" width="14" height="14" /> Borrador
      </button>
      <button className="btn btn--primary" style={{ flex: 2 }}>
        <i data-lucide="upload" width="14" height="14" /> Enviar al SOC
      </button>
    </div>
  </Phone>
);

// =====================================================================
// SCREEN 2.5 — Sincronización Asíncrona (Offline-first)
// Phone lost signal mid-evacuation; reports queue locally and dispatch
// automatically when the link returns.
// =====================================================================
const BrigadistaSync = () => (
  <Phone profile="brigadista" active="triage" appbarRight={
    <span className="pill pill--warn"><i data-lucide="wifi-off" width="11" height="11" /> SIN ENLACE</span>
  }>
    <div className="card" style={{
      borderColor: 'var(--tk-status-warning)',
      background: 'linear-gradient(180deg, rgba(255,193,7,0.10), transparent)',
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: 'var(--tk-status-warning-15)', color: 'var(--tk-status-warning)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <i data-lucide="cloud-off" width="18" height="18" />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Modo offline</div>
          <div style={{ fontSize: 11, color: 'var(--tk-fg-2)', marginTop: 4, lineHeight: 1.4 }}>
            Sus capturas y reportes se guardan localmente cifrados.
            La sincronización con AWS arrancará en cuanto se recupere señal.
          </div>
        </div>
      </div>
    </div>

    <div className="t-section">Cola de envío · 7 elementos</div>

    <div className="card" style={{ padding: 14 }}>
      <div className="card__hd" style={{ marginBottom: 6 }}>
        <div className="card__title" style={{ fontSize: 12 }}>Subida automática</div>
        <span className="card__sub">12.8 MB en cola</span>
      </div>
      <div className="sync-bar">
        <div className="sync-bar__track">
          <div className="sync-bar__fill" style={{ width: '0%' }} />
        </div>
        <div className="sync-bar__pct">0<span className="unit">%</span></div>
      </div>
      <div style={{ fontSize: 10, color: 'var(--tk-fg-3)', fontFamily: 'var(--tk-font-mono)', letterSpacing: '0.04em' }}>
        Reintentando en 0:14 · WiFi/LTE
      </div>
    </div>

    <div>
      <div className="sync-row">
        <div className="sync-row__thumb">
          <svg viewBox="0 0 40 40" preserveAspectRatio="xMidYMid slice" style={{ width: '100%', height: '100%' }}>
            <rect x="14" y="0" width="12" height="40" fill="#3a3633" />
            <path d="M 17 0 Q 19 14 15 24 Q 12 32 17 40" stroke="#0a0907" strokeWidth="1.4" fill="none" />
          </svg>
        </div>
        <div>
          <div className="sync-row__name">IMG_20260514_144208.jpg</div>
          <div className="sync-row__meta">P10-A · Columna NE · 4.2 MB</div>
        </div>
        <span className="sync-row__state pill pill--warn">PEND</span>
      </div>
      <div className="sync-row">
        <div className="sync-row__thumb">
          <svg viewBox="0 0 40 40" preserveAspectRatio="xMidYMid slice" style={{ width: '100%', height: '100%' }}>
            <rect x="0" y="0" width="40" height="40" fill="#3a3633" />
            <rect x="6" y="20" width="28" height="2" fill="#0a0907" />
            <rect x="6" y="26" width="22" height="2" fill="#0a0907" />
          </svg>
        </div>
        <div>
          <div className="sync-row__name">RPT-EVT20260514-1435.json</div>
          <div className="sync-row__meta">Formulario daños · 2.1 KB</div>
        </div>
        <span className="sync-row__state pill pill--warn">PEND</span>
      </div>
      {/* La cola solo contiene lo que el TELÉFONO produce (fotos, reportes,
          check-ins, headcount). El miniSEED del sensor sube edge→S3 en eventos
          confirmados y jamás pasa por el móvil (spec §1 / regla de oro 9). */}
      <div className="sync-row">
        <div className="sync-row__thumb">
          <svg viewBox="0 0 40 40" preserveAspectRatio="xMidYMid slice" style={{ width: '100%', height: '100%' }}>
            <rect x="0" y="0" width="40" height="40" fill="#3a3633" />
            <circle cx="14" cy="15" r="5" fill="none" stroke="#00BFFF" strokeWidth="1.5" />
            <path d="M 11 15 L 13.5 17.5 L 18 12.5" stroke="#00BFFF" strokeWidth="1.5" fill="none" />
            <rect x="8" y="26" width="24" height="2" fill="#0a0907" />
            <rect x="8" y="31" width="18" height="2" fill="#0a0907" />
          </svg>
        </div>
        <div>
          <div className="sync-row__name">CHECKIN_DELEGADO_P10-22.json</div>
          <div className="sync-row__meta">Verificado en persona · 0.8 KB</div>
        </div>
        <span className="sync-row__state pill pill--warn">PEND</span>
      </div>
      <div className="sync-row">
        <div className="sync-row__thumb">
          <svg viewBox="0 0 40 40" preserveAspectRatio="xMidYMid slice" style={{ width: '100%', height: '100%' }}>
            <rect x="0" y="0" width="40" height="40" fill="#3a3633" />
            <circle cx="20" cy="20" r="6" fill="none" stroke="#FFC107" strokeWidth="2" />
          </svg>
        </div>
        <div>
          <div className="sync-row__name">HEADCOUNT_P10.csv</div>
          <div className="sync-row__meta">38 ocupantes · 6 sin reporte</div>
        </div>
        <span className="sync-row__state pill pill--warn">PEND</span>
      </div>
      <div className="sync-row">
        <div className="sync-row__thumb" style={{ background: 'rgba(0,230,118,0.10)' }}>
          <i data-lucide="check" width="20" height="20" style={{ color: 'var(--tk-status-normal)', margin: 8 }} />
        </div>
        <div>
          <div className="sync-row__name">IMG_20260514_143955.jpg</div>
          <div className="sync-row__meta">P-2 · enviado 14:41 · 3.6 MB</div>
        </div>
        <span className="sync-row__state pill pill--ok">OK</span>
      </div>
    </div>

    <div style={{
      padding: '10px 14px', borderRadius: 6,
      border: '1px dashed var(--tk-border-strong)',
      fontSize: 10, color: 'var(--tk-fg-3)',
      fontFamily: 'var(--tk-font-mono)', letterSpacing: '0.04em',
      textAlign: 'center',
    }}>
      AES-256 LOCAL · CADENA DE CUSTODIA PRESERVADA
    </div>
  </Phone>
);

// =====================================================================
// SCREEN 2.6 — Headcount / Pase de lista
// Cross-references the occupant "Estoy a salvo" check-ins with the
// roster assigned to this brigadista's floor. "No reportados" is the
// default filter for obvious reasons.
// =====================================================================
const BrigadistaHeadcount = () => (
  <Phone profile="brigadista" active="lista" appbarRight={
    <span className="pill pill--crit"><span className="pill__dot" /> 6 SIN REPORTE</span>
  }>
    <div>
      <div className="t-eyebrow">PASE DE LISTA · PISO 10 · EDIF. A</div>
      <div style={{ fontSize: 18, fontWeight: 600, marginTop: 2, letterSpacing: '-0.01em' }}>
        38 ocupantes asignados
      </div>
    </div>

    <div className="hc-summary">
      <div className="hc-summary__cell">
        <div className="num" style={{ color: 'var(--tk-status-normal)' }}>32</div>
        <div className="lbl">A salvo</div>
      </div>
      <div className="hc-summary__cell hc-summary__cell--alert">
        <div className="num">6</div>
        <div className="lbl">Sin reporte</div>
      </div>
      <div className="hc-summary__cell">
        <div className="num" style={{ color: 'var(--tk-status-warning)' }}>0</div>
        <div className="lbl">Necesita ayuda</div>
      </div>
    </div>

    {/* Filter pills */}
    <div className="tab-pillrow" style={{ gridTemplateColumns: '1fr 1fr 1fr' }}>
      <button className="tab-pillrow__btn">Todos · 38</button>
      <button className="tab-pillrow__btn is-active">No reportados · 6</button>
      <button className="tab-pillrow__btn">A salvo · 32</button>
    </div>

    <div>
      <div className="hc-row hc-row--alert">
        <div className="hc-row__avatar">MR</div>
        <div>
          <div className="hc-row__name">María Reyes Pérez</div>
          <div className="hc-row__meta">Cubículo 10-14 · +52 55 1284 8211</div>
        </div>
        <button className="hc-row__action"><i data-lucide="phone" width="16" height="16" /></button>
      </div>
      <div className="hc-row hc-row--alert">
        <div className="hc-row__avatar">RG</div>
        <div>
          <div className="hc-row__name">Ricardo Gómez Solís</div>
          <div className="hc-row__meta">Sala juntas 10-B · +52 55 6712 0019</div>
        </div>
        <button className="hc-row__action"><i data-lucide="phone" width="16" height="16" /></button>
      </div>
      <div className="hc-row hc-row--alert">
        <div className="hc-row__avatar">PC</div>
        <div>
          <div className="hc-row__name">Pedro Castillo M.</div>
          <div className="hc-row__meta">Visitante · acceso 09:14 · +52 55 4501 2208</div>
        </div>
        <button className="hc-row__action"><i data-lucide="phone" width="16" height="16" /></button>
      </div>
      <div className="hc-row hc-row--alert">
        <div className="hc-row__avatar">LV</div>
        <div>
          <div className="hc-row__name">Lucía Vargas Romero</div>
          <div className="hc-row__meta">Cubículo 10-22 · +52 55 8821 0094</div>
        </div>
        <button className="hc-row__action"><i data-lucide="phone" width="16" height="16" /></button>
      </div>
      <div className="hc-row hc-row--alert">
        <div className="hc-row__avatar">TM</div>
        <div>
          <div className="hc-row__name">Tomás Medina A.</div>
          <div className="hc-row__meta">Cubículo 10-08 · +52 55 1900 3372</div>
        </div>
        <button className="hc-row__action"><i data-lucide="phone" width="16" height="16" /></button>
      </div>
      <div className="hc-row hc-row--alert">
        <div className="hc-row__avatar">SO</div>
        <div>
          <div className="hc-row__name">Sofía Ortega B.</div>
          <div className="hc-row__meta">Cubículo 10-31 · +52 55 7012 4488</div>
        </div>
        <button className="hc-row__action"><i data-lucide="phone" width="16" height="16" /></button>
      </div>
    </div>

    {/* Sin envío de mensajes de texto: ese canal no existe en la plataforma
        (stub simulado). La notificación a no reportados es push clase OPS. */}
    <button className="btn btn--ghost btn--block">
      <i data-lucide="bell-ring" width="14" height="14" /> Notificar a no reportados · push
    </button>
  </Phone>
);

// =====================================================================
// SCREEN 2.7 — Recepción de Dictamen de Reingreso
// Civil-protection-signed PDF arrives in the brigadista app. The
// brigadista is the one who gives the verbal "all-clear" downstairs.
// =====================================================================
const BrigadistaDictamen = () => (
  <Phone profile="brigadista" active="triage" notif={true}>
    <div className="t-eyebrow" style={{ color: 'var(--tk-status-normal)' }}>
      <i data-lucide="bell-ring" width="11" height="11" /> Notificación · ahora
    </div>
    <div style={{ fontSize: 18, fontWeight: 600, marginTop: 2, letterSpacing: '-0.01em' }}>
      Dictamen oficial recibido
    </div>

    <div className="cert">
      <div className="cert__seal">
        FIRMA<br />DIGITAL<br />VÁLIDA
      </div>
      <div className="cert__eyebrow">
        <i data-lucide="shield-check" width="11" height="11" /> Protección Civil
      </div>
      <div className="cert__title">Edificio aprobado para reingreso</div>
      <div className="cert__site">Planta Cholula · Edificio A · EVT-20260514-1435</div>

      <dl className="cert__meta">
        <div>
          <dt>Veredicto</dt>
          <dd style={{ color: 'var(--tk-status-normal)' }}>HABITAR</dd>
        </div>
        <div>
          <dt>Vigencia</dt>
          <dd>72 hrs · re-inspección</dd>
        </div>
        <div>
          <dt>Firma</dt>
          <dd>Ing. R. Aguilar</dd>
        </div>
        <div>
          <dt>Folio</dt>
          <dd>DCT-26-05-0017</dd>
        </div>
      </dl>

      <div className="cert__sig">
        <i data-lucide="fingerprint" width="14" height="14" style={{ color: 'var(--tk-status-normal)' }} />
        FIRMA DIGITAL · INSPECTOR · 15:24:08 CST
      </div>
    </div>

    {/* PDF preview */}
    <div className="t-section">Vista previa · PDF</div>
    <div className="pdf-thumb">
      <div className="pdf-thumb__bar" />
      <div className="pdf-thumb__h">DICTAMEN TÉCNICO DE REINGRESO</div>
      <div style={{ fontFamily: 'var(--tk-font-mono)', fontSize: 8, color: 'var(--tk-fg-on-light-2)', marginBottom: 8 }}>
        FOLIO DCT-26-05-0017 · 14 MAY 2026 · 15:24 CST
      </div>
      <div style={{ marginBottom: 10 }}>
        Visto y revisado el evento sísmico EVT-20260514-1435 (magnitud oficial
        del catálogo SSN, publicada posterior al evento), el cual provocó un
        PGA local medido de 0.150g sobre el inmueble, y habiendo concluido la
        inspección estructural por piso bajo el marco normativo configurado
        del cliente, se determina lo siguiente:
      </div>
      <div className="pdf-thumb__line" style={{ width: '88%' }} />
      <div className="pdf-thumb__line" style={{ width: '76%' }} />
      <div className="pdf-thumb__line" style={{ width: '92%' }} />
      <div className="pdf-thumb__line" style={{ width: '64%' }} />
      <div className="pdf-thumb__line" style={{ width: '80%' }} />
    </div>

    <div style={{ display: 'flex', gap: 8 }}>
      <button className="btn btn--ghost" style={{ flex: 1 }}>
        <i data-lucide="download" width="14" height="14" /> Guardar
      </button>
      <button className="btn btn--primary" style={{ flex: 1.4 }}>
        <i data-lucide="megaphone" width="14" height="14" /> Notificar pisos
      </button>
    </div>
  </Phone>
);

Object.assign(window, {
  BrigadistaPanel, BrigadistaControlRemoto, BrigadistaCamara,
  BrigadistaFormulario, BrigadistaSync, BrigadistaHeadcount, BrigadistaDictamen,
});
