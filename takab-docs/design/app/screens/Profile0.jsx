// app/screens/Profile0.jsx
// ACCESO Y ONBOARDING + pantallas de tabs del ocupante agregadas por la
// spec v2 (ESPECIFICACION-APP-MOVIL.md §7, 2026-07-15):
//   0.1 login · 0.2 permisos de alertas · 0.3 aviso de privacidad
//   0.4 enrolamiento por código · 1.6 rutas · 1.7 directorio · 1.8 cuenta
//   1.9 pánico por quórum-de-2 · 1.1-bis variante SIMULACRO del reposo
// Reglas §2.1 aplicadas: sin cuenta regresiva, sin siglas de hardware
// inexistente, sin literales normativos (compliance-labels del tenant).

// =====================================================================
// SCREEN 0.1 — Login (Cognito Hosted UI + PKCE, patrón de la consola)
// =====================================================================
const AccesoLogin = () => (
  <Phone profile="ocupante" hideChrome={true}>
    <div style={{
      position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', padding: '0 28px',
      background: 'radial-gradient(ellipse at center -20%, rgba(0,191,255,0.10) 0%, transparent 55%), var(--tk-surface-0)',
    }}>
      <svg viewBox="0 0 100 100" fill="var(--tk-cyan)" style={{ width: 54, height: 54 }}>
        <path d="M 18 12 L 32 12 L 32 88 L 18 88 Z" />
        <path d="M 32 50 L 78 12 L 96 12 L 50 50 Z" />
        <path d="M 32 50 L 78 88 L 96 88 L 50 50 Z" />
      </svg>
      <div style={{
        fontFamily: 'var(--tk-font-brand)', fontSize: 34, fontWeight: 700,
        letterSpacing: '0.06em', color: 'var(--tk-fg-1)', marginTop: 14, textTransform: 'uppercase',
      }}>
        TAKAB Ailert
      </div>
      <div style={{ fontSize: 12, color: 'var(--tk-fg-3)', marginTop: 6, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
        Alertamiento sísmico · continuidad operativa
      </div>

      <button className="btn btn--primary btn--block" style={{ marginTop: 44, height: 52, fontSize: 14 }}>
        <i data-lucide="log-in" width="16" height="16" /> Iniciar sesión
      </button>
      <div style={{
        marginTop: 12, fontSize: 10, color: 'var(--tk-fg-3)',
        fontFamily: 'var(--tk-font-mono)', letterSpacing: '0.06em', textAlign: 'center',
      }}>
        AWS COGNITO · CÓDIGO + PKCE · MISMO POOL QUE LA CONSOLA
      </div>

      <div className="card card--flat" style={{ marginTop: 40, padding: '12px 14px', width: '100%' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          <i data-lucide="shield-check" width="16" height="16" style={{ color: 'var(--tk-status-normal)', marginTop: 1 }} />
          <div style={{ fontSize: 11, color: 'var(--tk-fg-2)', lineHeight: 1.5 }}>
            Su sesión de ocupante permanece activa: la app puede alertarle
            <strong style={{ color: 'var(--tk-fg-1)' }}> sin pedir login en plena crisis</strong>.
          </div>
        </div>
      </div>
    </div>
    <span className="home-indicator" />
  </Phone>
);

// =====================================================================
// SCREEN 0.2 — Onboarding de permisos · estado de alertabilidad
// Estado degradado mostrado: imposible de ignorar (spec §6).
// =====================================================================
const AccesoPermisos = () => (
  <Phone profile="ocupante" hideChrome={true}>
    <div style={{ position: 'absolute', inset: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', background: 'var(--tk-surface-0)', padding: '64px 18px 34px' }}>
      <div className="t-eyebrow">CONFIGURACIÓN · PASO 2 DE 4</div>
      <div style={{ fontSize: 20, fontWeight: 600, marginTop: 4, letterSpacing: '-0.01em', color: 'var(--tk-fg-1)' }}>
        Permisos de alerta
      </div>

      <div className="card" style={{
        marginTop: 14, borderColor: 'var(--tk-status-critical)',
        background: 'linear-gradient(180deg, rgba(255,82,82,0.14), rgba(255,82,82,0.04))',
      }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <div style={{
            width: 38, height: 38, borderRadius: 8, flex: '0 0 38px',
            background: 'var(--tk-status-critical-15)', color: 'var(--tk-status-critical)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <i data-lucide="bell-off" width="19" height="19" />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--tk-status-critical)' }}>
              Su teléfono NO recibirá alertas
            </div>
            <div style={{ fontSize: 11, color: 'var(--tk-fg-2)', marginTop: 4, lineHeight: 1.5 }}>
              Faltan 2 permisos. Este es un producto de seguridad de vida:
              sin ellos, la app no puede despertarlo durante un sismo.
            </div>
          </div>
        </div>
        <button className="btn btn--primary btn--block" style={{ marginTop: 12 }}>
          <i data-lucide="settings" width="14" height="14" /> Abrir ajustes del sistema
        </button>
      </div>

      <div className="t-section">Estado por permiso</div>
      <div className="card" style={{ padding: 6 }}>
        {[
          { ic: 'bell-ring', lbl: 'Notificaciones', sub: 'Requerido para cualquier alerta', ok: false },
          { ic: 'moon', lbl: 'Ignorar No Molestar', sub: 'La alerta sísmica suena aun en silencio', ok: false },
          { ic: 'volume-2', lbl: 'Sonido oficial de alerta', sub: 'Empaquetado en la app', ok: true },
          { ic: 'map-pin', lbl: 'Ubicación', sub: 'Opcional · solo para "necesito ayuda"', ok: null },
        ].map((p, i) => (
          <div key={i} style={{
            display: 'flex', alignItems: 'center', gap: 12, padding: '11px 10px',
            borderTop: i ? '1px solid var(--tk-border)' : 'none',
          }}>
            <i data-lucide={p.ic} width="17" height="17" style={{ color: p.ok === false ? 'var(--tk-status-critical)' : 'var(--tk-fg-3)' }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, color: 'var(--tk-fg-1)' }}>{p.lbl}</div>
              <div style={{ fontSize: 10, color: 'var(--tk-fg-3)', marginTop: 2 }}>{p.sub}</div>
            </div>
            {p.ok === true && <span className="pill pill--ok">OK</span>}
            {p.ok === false && <span className="pill pill--crit">FALTA</span>}
            {p.ok === null && <span className="pill">OPCIONAL</span>}
          </div>
        ))}
      </div>

      <div style={{
        marginTop: 'auto', fontSize: 10, color: 'var(--tk-fg-3)', textAlign: 'center',
        fontFamily: 'var(--tk-font-mono)', letterSpacing: '0.05em', lineHeight: 1.6,
      }}>
        SE RE-VERIFICA EN CADA ARRANQUE · LA PUSH ES DESPERTADOR:<br />
        LA PROTECCIÓN DE VIDA ES LA SIRENA DEL EDIFICIO
      </div>
    </div>
    <span className="home-indicator" />
  </Phone>
);

// =====================================================================
// SCREEN 0.3 — Aviso de privacidad (LFPDPPP) + consentimiento GPS
// =====================================================================
const AccesoPrivacidad = () => (
  <Phone profile="ocupante" hideChrome={true}>
    <div style={{ position: 'absolute', inset: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', background: 'var(--tk-surface-0)', padding: '64px 18px 34px' }}>
      <div className="t-eyebrow">CONFIGURACIÓN · PASO 3 DE 4</div>
      <div style={{ fontSize: 20, fontWeight: 600, marginTop: 4, letterSpacing: '-0.01em', color: 'var(--tk-fg-1)' }}>
        Aviso de privacidad
      </div>
      <div style={{ fontSize: 11, color: 'var(--tk-fg-3)', marginTop: 4 }}>
        Resumen · el aviso completo lo sirve su organización (LFPDPPP).
      </div>

      <div className="card" style={{ marginTop: 14, padding: 6 }}>
        {[
          { ic: 'user', txt: 'Tratamos su nombre, zona asignada y check-ins de vida como datos de protección civil del inmueble.' },
          { ic: 'map-pin', txt: 'Su ubicación GPS solo se envía si usted lo consiente Y solo al pulsar "NECESITO AYUDA".' },
          { ic: 'archive', txt: 'Los check-ins de un incidente son evidencia: se conservan según la política de evidencia, no se editan.' },
          { ic: 'lock', txt: 'Sus datos jamás cruzan a otra organización (aislamiento por cliente en base de datos).' },
        ].map((r, i) => (
          <div key={i} style={{
            display: 'flex', gap: 12, alignItems: 'flex-start', padding: '11px 10px',
            borderTop: i ? '1px solid var(--tk-border)' : 'none',
          }}>
            <i data-lucide={r.ic} width="16" height="16" style={{ color: 'var(--tk-cyan)', marginTop: 1, flex: '0 0 16px' }} />
            <div style={{ fontSize: 11.5, color: 'var(--tk-fg-2)', lineHeight: 1.55 }}>{r.txt}</div>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, color: 'var(--tk-fg-1)', fontWeight: 500 }}>Compartir GPS en emergencia</div>
            <div style={{ fontSize: 10, color: 'var(--tk-fg-3)', marginTop: 2 }}>Revocable en Cuenta · sin GPS se envía su zona</div>
          </div>
          <div style={{
            width: 46, height: 26, borderRadius: 999, background: 'var(--tk-status-normal-15)',
            border: '1px solid var(--tk-status-normal)', position: 'relative',
          }}>
            <span style={{
              position: 'absolute', right: 2, top: 2, width: 20, height: 20, borderRadius: 999,
              background: 'var(--tk-status-normal)',
            }} />
          </div>
        </div>
      </div>

      <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <button className="btn btn--primary btn--block" style={{ height: 48 }}>
          <i data-lucide="check" width="15" height="15" /> Aceptar y continuar
        </button>
        <button className="btn btn--ghost btn--block">
          <i data-lucide="file-text" width="14" height="14" /> Ver aviso completo
        </button>
      </div>
    </div>
    <span className="home-indicator" />
  </Phone>
);

// =====================================================================
// SCREEN 0.4 — Enrolamiento por código de sitio (site_enrollment_codes)
// =====================================================================
const AccesoEnrolamiento = () => (
  <Phone profile="ocupante" hideChrome={true}>
    <div style={{ position: 'absolute', inset: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', background: 'var(--tk-surface-0)', padding: '64px 18px 34px' }}>
      <div className="t-eyebrow">CONFIGURACIÓN · PASO 4 DE 4</div>
      <div style={{ fontSize: 20, fontWeight: 600, marginTop: 4, letterSpacing: '-0.01em', color: 'var(--tk-fg-1)' }}>
        Vincular a su edificio
      </div>
      <div style={{ fontSize: 11, color: 'var(--tk-fg-3)', marginTop: 4 }}>
        Ingrese el código que le entregó el administrador de su inmueble.
      </div>

      <div className="card card--cyan" style={{ marginTop: 16, textAlign: 'center', padding: '18px 14px' }}>
        <div style={{ fontSize: 10, letterSpacing: '0.14em', color: 'var(--tk-fg-3)', textTransform: 'uppercase' }}>
          Código de sitio
        </div>
        <div style={{
          fontFamily: 'var(--tk-font-mono)', fontSize: 30, fontWeight: 700,
          letterSpacing: '0.18em', color: 'var(--tk-fg-1)', marginTop: 8,
        }}>
          CHL-A-7Q2F
        </div>
        <div style={{ width: 180, height: 2, background: 'var(--tk-cyan)', margin: '10px auto 0', borderRadius: 2 }} />
      </div>

      <div className="card" style={{
        marginTop: 12, borderColor: 'var(--tk-status-normal)',
        background: 'linear-gradient(180deg, rgba(0,230,118,0.10), transparent)',
      }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <i data-lucide="building-2" width="18" height="18" style={{ color: 'var(--tk-status-normal)', marginTop: 2 }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--tk-fg-1)' }}>Planta Cholula · Edificio A</div>
            <div style={{ fontSize: 11, color: 'var(--tk-fg-2)', marginTop: 4, lineHeight: 1.5 }}>
              Zona asignada: <strong style={{ color: 'var(--tk-fg-1)' }}>Piso 10 · P10-A (repliegue)</strong><br />
              Rol: OCUPANTE
            </div>
            <div style={{ fontFamily: 'var(--tk-font-mono)', fontSize: 9.5, color: 'var(--tk-fg-3)', marginTop: 6, letterSpacing: '0.06em' }}>
              CÓDIGO VÁLIDO · VIGENTE HASTA 2026-08-01 · USOS 41/200
            </div>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 'auto' }}>
        <button className="btn btn--primary btn--block" style={{ height: 48 }}>
          <i data-lucide="check" width="15" height="15" /> Confirmar vinculación
        </button>
        <div style={{
          marginTop: 10, fontSize: 10, color: 'var(--tk-fg-3)', textAlign: 'center',
          fontFamily: 'var(--tk-font-mono)', letterSpacing: '0.05em',
        }}>
          UN CÓDIGO EXPIRADO O AGOTADO SE RECHAZA CON MOTIVO CLARO
        </div>
      </div>
    </div>
    <span className="home-indicator" />
  </Phone>
);

// =====================================================================
// SCREEN 1.6 — Rutas (tab Rutas) · assets cacheados offline
// =====================================================================
const OcupanteRutas = () => (
  <Phone profile="ocupante" active="rutas">
    <div>
      <div className="t-eyebrow">SU ZONA · PISO 10 · P10-A</div>
      <div style={{ fontSize: 18, fontWeight: 600, marginTop: 2, letterSpacing: '-0.01em' }}>
        Rutas y puntos de reunión
      </div>
    </div>

    <div className="t-section">Documentos de su zona</div>
    <div>
      {[
        { ic: 'map', lbl: 'Ruta de evacuación · P10', meta: 'PDF · 1.2 MB · v3.1', off: true },
        { ic: 'shield', lbl: 'Zona de repliegue P10-A', meta: 'Imagen · 640 KB', off: true },
        { ic: 'book-open', lbl: 'Manual operativo', meta: 'PDF · 3.4 MB · v3.1', off: true },
        { ic: 'layout-grid', lbl: 'Plano general del inmueble', meta: 'PDF · 8.1 MB', off: false },
      ].map((d, i) => (
        <div key={i} className="card" style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', marginBottom: 8 }}>
          <i data-lucide={d.ic} width="20" height="20" style={{ color: 'var(--tk-cyan)', flex: '0 0 20px' }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 500 }}>{d.lbl}</div>
            <div style={{ fontSize: 10, color: 'var(--tk-fg-3)', fontFamily: 'var(--tk-font-mono)', marginTop: 2 }}>{d.meta}</div>
          </div>
          {d.off
            ? <span className="pill pill--ok"><i data-lucide="check" width="10" height="10" /> OFFLINE</span>
            : <span className="pill pill--warn">SOLO EN LÍNEA</span>}
        </div>
      ))}
    </div>

    <div className="t-section">Punto de reunión asignado</div>
    <div className="card">
      <div className="card__hd">
        <div className="card__title">Punto de reunión P-2</div>
        <span className="pill pill--ok"><span className="pill__dot" /> ACTIVO</span>
      </div>
      <div style={{ display: 'flex', gap: 10 }}>
        <div style={{
          width: 60, height: 60, borderRadius: 8, background: 'var(--tk-surface-2)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--tk-cyan)',
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

    <div style={{
      padding: '10px 14px', borderRadius: 6, border: '1px dashed var(--tk-border-strong)',
      fontSize: 10, color: 'var(--tk-fg-3)', fontFamily: 'var(--tk-font-mono)',
      letterSpacing: '0.04em', textAlign: 'center',
    }}>
      LO MARCADO OFFLINE ABRE SIN RED · LO DEMÁS DECLARA SU ESTADO
    </div>
  </Phone>
);

// =====================================================================
// SCREEN 1.7 — Directorio (tab Directorio) · llamada de un toque
// =====================================================================
const OcupanteDirectorio = () => (
  <Phone profile="ocupante" active="dir">
    <div>
      <div className="t-eyebrow">DIRECTORIO · PLANTA CHOLULA · EDIF. A</div>
      <div style={{ fontSize: 18, fontWeight: 600, marginTop: 2, letterSpacing: '-0.01em' }}>
        Contactos de emergencia
      </div>
    </div>

    <div className="t-section">Brigadistas · Piso 10</div>
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
      <div className="dir-row">
        <div className="dir-row__avatar">RC</div>
        <div>
          <div className="dir-row__name">Raúl Cordero</div>
          <div className="dir-row__role">EVACUACIÓN · P10</div>
        </div>
        <div className="dir-row__phone"><i data-lucide="phone" width="16" height="16" /></div>
      </div>
    </div>

    <div className="t-section">Seguridad del inmueble</div>
    <div>
      <div className="dir-row">
        <div className="dir-row__avatar" style={{ background: 'var(--tk-cyan-15)', color: 'var(--tk-cyan)' }}>
          <i data-lucide="shield" width="16" height="16" />
        </div>
        <div>
          <div className="dir-row__name">Caseta de seguridad</div>
          <div className="dir-row__role">24 HORAS · PLANTA BAJA</div>
        </div>
        <div className="dir-row__phone"><i data-lucide="phone" width="16" height="16" /></div>
      </div>
    </div>

    <div className="t-section">Emergencias externas</div>
    <div className="card" style={{
      display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px',
      borderColor: 'var(--tk-status-critical)',
    }}>
      <div style={{
        width: 40, height: 40, borderRadius: 8, background: 'var(--tk-status-critical-15)',
        color: 'var(--tk-status-critical)', display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <i data-lucide="phone-call" width="18" height="18" />
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 15, fontWeight: 700, fontFamily: 'var(--tk-font-mono)' }}>911</div>
        <div style={{ fontSize: 10, color: 'var(--tk-fg-3)', marginTop: 2 }}>Emergencias nacionales</div>
      </div>
      <i data-lucide="chevron-right" width="16" height="16" style={{ color: 'var(--tk-fg-3)' }} />
    </div>
  </Phone>
);

// =====================================================================
// SCREEN 1.8 — Cuenta (tab Cuenta · compartida por ambos perfiles)
// =====================================================================
const OcupanteCuenta = () => (
  <Phone profile="ocupante" active="cuenta">
    <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '16px 14px' }}>
      <div style={{
        width: 52, height: 52, borderRadius: 999, background: 'var(--tk-cyan-15)',
        color: 'var(--tk-cyan)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 17, fontWeight: 700,
      }}>
        MR
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 15, fontWeight: 600 }}>María Rodríguez</div>
        <div style={{ fontSize: 10, color: 'var(--tk-fg-3)', fontFamily: 'var(--tk-font-mono)', marginTop: 3, letterSpacing: '0.06em' }}>
          OCUPANTE · PISO 10 · P10-A (REPLIEGUE)
        </div>
        <div style={{ fontSize: 10, color: 'var(--tk-fg-3)', marginTop: 2 }}>Planta Cholula · Edificio A</div>
      </div>
    </div>

    <div className="t-section">Alertas y privacidad</div>
    <div className="card" style={{ padding: 6 }}>
      {[
        { ic: 'bell-ring', lbl: 'Permisos de alertas', sub: 'Verificado hoy · 10:41', pill: { cls: 'pill--ok', txt: 'OK' } },
        { ic: 'map-pin', lbl: 'Consentimiento GPS', sub: 'Solo para "necesito ayuda" · revocable', pill: { cls: 'pill--ok', txt: 'ACTIVO' } },
        { ic: 'file-text', lbl: 'Aviso de privacidad', sub: 'Versión 2026-07 · LFPDPPP', pill: null },
        { ic: 'volume-2', lbl: 'Probar sonido de alerta', sub: 'Reproduce el tono oficial a volumen medio', pill: null },
      ].map((r, i) => (
        <div key={i} style={{
          display: 'flex', alignItems: 'center', gap: 12, padding: '12px 10px',
          borderTop: i ? '1px solid var(--tk-border)' : 'none',
        }}>
          <i data-lucide={r.ic} width="17" height="17" style={{ color: 'var(--tk-cyan)' }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13 }}>{r.lbl}</div>
            <div style={{ fontSize: 10, color: 'var(--tk-fg-3)', marginTop: 2 }}>{r.sub}</div>
          </div>
          {r.pill
            ? <span className={'pill ' + r.pill.cls}>{r.pill.txt}</span>
            : <i data-lucide="chevron-right" width="15" height="15" style={{ color: 'var(--tk-fg-3)' }} />}
        </div>
      ))}
    </div>

    <div className="t-section">Sesión</div>
    <button className="btn btn--ghost btn--block">
      <i data-lucide="log-out" width="14" height="14" /> Cerrar sesión
    </button>

    <div style={{
      marginTop: 8, fontSize: 9.5, color: 'var(--tk-fg-3)', textAlign: 'center',
      fontFamily: 'var(--tk-font-mono)', letterSpacing: '0.06em',
    }}>
      TAKAB AILERT · v2.0.0 · SESIÓN DE LARGA VIDA (ALERTA SIN LOGIN)
    </div>
  </Phone>
);

// =====================================================================
// SCREEN 1.9 — Pánico por quórum-de-2 (emergencia NO sísmica · RBAC §4)
// Un voto JAMÁS activa; dos votos de usuarios distintos en 30 s sí.
// =====================================================================
const OcupantePanico = () => (
  <Phone profile="ocupante" active="inicio">
    <div>
      <div className="t-eyebrow" style={{ color: 'var(--tk-status-critical)' }}>EMERGENCIA NO SÍSMICA</div>
      <div style={{ fontSize: 18, fontWeight: 600, marginTop: 2, letterSpacing: '-0.01em' }}>
        Solicitar activación de alarma
      </div>
    </div>

    <div className="card card--flat" style={{ padding: '12px 14px' }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
        <i data-lucide="info" width="16" height="16" style={{ color: 'var(--tk-fg-3)', marginTop: 2 }} />
        <div style={{ fontSize: 11.5, color: 'var(--tk-fg-2)', lineHeight: 1.55 }}>
          La sirena del edificio se activa únicamente cuando <strong style={{ color: 'var(--tk-fg-1)' }}>dos
          personas distintas</strong> lo solicitan en una ventana de <strong style={{ color: 'var(--tk-fg-1)' }}>30
          segundos</strong>. Esto <strong style={{ color: 'var(--tk-fg-1)' }}>no</strong> es la alerta sísmica:
          úselo ante incendio, intrusión u otra emergencia del inmueble.
        </div>
      </div>
    </div>

    <button style={{
      width: '100%', marginTop: 4, padding: '26px 18px', borderRadius: 12,
      background: 'linear-gradient(180deg, rgba(255,82,82,0.20), rgba(255,82,82,0.08))',
      border: '1px solid var(--tk-status-critical)', color: '#fff', cursor: 'pointer',
      display: 'flex', alignItems: 'center', gap: 16, textAlign: 'left',
      boxShadow: 'var(--tk-shadow-critical)',
    }}>
      <div style={{
        width: 52, height: 52, borderRadius: 999, flex: '0 0 52px',
        background: 'var(--tk-status-critical)', color: '#fff',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <i data-lucide="siren" width="26" height="26" />
      </div>
      <div>
        <div style={{ fontFamily: 'var(--tk-font-brand)', fontSize: 24, fontWeight: 700, letterSpacing: '0.03em', textTransform: 'uppercase', lineHeight: 1 }}>
          Solicitar activación
        </div>
        <div style={{ fontSize: 11, color: 'rgba(255,220,220,0.8)', marginTop: 6 }}>
          Mantenga presionado 2 segundos
        </div>
      </div>
    </button>

    <div className="t-section">Estado de la solicitud</div>
    <div className="card" style={{ borderColor: 'var(--tk-status-warning)' }}>
      <div className="card__hd">
        <div className="card__title" style={{ fontSize: 12 }}>Confirmaciones</div>
        <span className="pill pill--warn"><span className="pill__dot" /> EXPIRA EN 0:23</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 4 }}>
        <div style={{
          fontFamily: 'var(--tk-font-mono)', fontSize: 34, fontWeight: 700,
          color: 'var(--tk-status-warning)', lineHeight: 1,
        }}>
          1<span style={{ color: 'var(--tk-fg-3)', fontSize: 20 }}> / 2</span>
        </div>
        <div style={{ flex: 1, fontSize: 11, color: 'var(--tk-fg-2)', lineHeight: 1.5 }}>
          Su solicitud está registrada. Falta la confirmación de
          <strong style={{ color: 'var(--tk-fg-1)' }}> otra persona</strong> del edificio.
        </div>
      </div>
    </div>

    <div style={{
      padding: '10px 14px', borderRadius: 6, border: '1px dashed var(--tk-border-strong)',
      fontSize: 10, color: 'var(--tk-fg-3)', fontFamily: 'var(--tk-font-mono)',
      letterSpacing: '0.04em', textAlign: 'center',
    }}>
      QUÓRUM 2 EN 30 s · UN SOLO VOTO JAMÁS ACTIVA · TODO QUEDA AUDITADO
    </div>
  </Phone>
);

// =====================================================================
// SCREEN 1.1-bis — Modo reposo · variante SIMULACRO (drill activo)
// Un drill JAMÁS crea incidente (garantía server-side): la app lo muestra
// como banda ámbar informativa, nunca como pantalla de crisis.
// =====================================================================
const OcupanteReposoSimulacro = () => (
  <Phone profile="ocupante" active="inicio" notif={true}>
    <div className="card" style={{
      borderColor: 'var(--tk-status-warning)',
      background: 'linear-gradient(180deg, rgba(255,193,7,0.16), rgba(255,193,7,0.04))',
      padding: '12px 14px',
    }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        <div style={{
          width: 38, height: 38, borderRadius: 8, flex: '0 0 38px',
          background: 'var(--tk-status-warning-15)', color: 'var(--tk-status-warning)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <i data-lucide="traffic-cone" width="19" height="19" />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--tk-status-warning)', textTransform: 'uppercase' }}>
            Simulacro en curso — esto NO es una alerta real
          </div>
          <div style={{ fontSize: 11, color: 'var(--tk-fg-2)', marginTop: 4, lineHeight: 1.5 }}>
            Practique su ruta: diríjase al punto de reunión <strong style={{ color: 'var(--tk-fg-1)' }}>P-2</strong>.
          </div>
          <div style={{ fontFamily: 'var(--tk-font-mono)', fontSize: 9.5, color: 'var(--tk-fg-3)', marginTop: 6, letterSpacing: '0.06em' }}>
            TERMINA 11:30 · UNA ALERTA REAL SIEMPRE DOMINA
          </div>
        </div>
      </div>
    </div>

    <div className="safe-hero" style={{ marginTop: 4 }}>
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
          <div className="val">11:02:44 CST</div>
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

    <div className="t-section">Punto de reunión del simulacro</div>
    <div className="card">
      <div style={{ display: 'flex', gap: 10 }}>
        <div style={{
          width: 60, height: 60, borderRadius: 8, background: 'var(--tk-surface-2)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--tk-status-warning)',
        }}>
          <i data-lucide="map-pin" width="22" height="22" />
        </div>
        <div style={{ flex: 1, fontSize: 12, color: 'var(--tk-fg-2)', lineHeight: 1.5 }}>
          Estacionamiento exterior, costado sur.<br />
          <span style={{ color: 'var(--tk-fg-3)', fontFamily: 'var(--tk-font-mono)', fontSize: 11 }}>
            SU TIEMPO SE MIDE PARA EL REPORTE DEL SIMULACRO
          </span>
        </div>
      </div>
    </div>
  </Phone>
);

Object.assign(window, {
  AccesoLogin, AccesoPermisos, AccesoPrivacidad, AccesoEnrolamiento,
  OcupanteRutas, OcupanteDirectorio, OcupanteCuenta, OcupantePanico,
  OcupanteReposoSimulacro,
});
