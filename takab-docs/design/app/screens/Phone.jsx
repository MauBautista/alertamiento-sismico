// app/screens/Phone.jsx
// Shared iPhone bezel + statusbar for all mobile screens.
// Variants:
//   - profile: 'ocupante' | 'brigadista'  → drives role pill color in appbar
//   - time, signal, battery               → small details for status bar
//   - hideChrome                          → omit appbar+tabbar (used by full-screen
//                                           crisis / camera screens that draw their own)

const PhoneStatusBar = ({ time = '10:41', sigBars = 4 }) => (
  <div className="statusbar">
    <span>{time}</span>
    <span className="statusbar__right">
      {/* Signal bars */}
      <svg width="16" height="11" viewBox="0 0 16 11" fill="currentColor">
        {[0, 1, 2, 3].map(i => (
          <rect
            key={i}
            x={i * 4}
            y={6 - i * 2}
            width="3"
            height={5 + i * 2}
            opacity={i < sigBars ? 1 : 0.3}
          />
        ))}
      </svg>
      {/* WiFi */}
      <svg width="14" height="11" viewBox="0 0 14 11" fill="currentColor">
        <path d="M7 2.5C4.5 2.5 2.3 3.5 0.6 5.1l1.1 1.1C3.1 4.9 4.9 4 7 4s3.9.9 5.3 2.2l1.1-1.1C11.7 3.5 9.5 2.5 7 2.5zM7 5.5c-1.7 0-3.1.6-4.3 1.6l1.1 1.1C4.6 7.4 5.7 7 7 7s2.4.4 3.2 1.2l1.1-1.1C10.1 6.1 8.7 5.5 7 5.5zM7 8.5c-.8 0-1.6.3-2.1.8l1.1 1.1c.3-.3.6-.4 1-.4s.7.1 1 .4l1.1-1.1c-.5-.5-1.3-.8-2.1-.8z" />
      </svg>
      {/* Battery */}
      <svg width="22" height="12" viewBox="0 0 22 12" fill="none" stroke="currentColor" strokeWidth="1">
        <rect x="0.5" y="1" width="18" height="10" rx="2.5" />
        <rect x="2" y="2.5" width="14" height="7" fill="currentColor" rx="1" />
        <rect x="19.5" y="4" width="1.5" height="4" rx="0.5" fill="currentColor" />
      </svg>
    </span>
  </div>
);

const PhoneAppBar = ({ profile = 'ocupante', user = 'M. RODRÍGUEZ', notif = false, right }) => {
  const role = profile === 'brigadista' ? 'BRIGADISTA · PISO 04' : 'OCUPANTE · PISO 10';
  return (
    <div className="appbar">
      <div className="appbar__brand">
        <svg className="appbar__logo" viewBox="0 0 100 100" fill="currentColor">
          <path d="M 18 12 L 32 12 L 32 88 L 18 88 Z" />
          <path d="M 32 50 L 78 12 L 96 12 L 50 50 Z" />
          <path d="M 32 50 L 78 88 L 96 88 L 50 50 Z" />
        </svg>
        <div>
          <div className="appbar__name">TAKAB</div>
          <div className={'appbar__role' + (profile === 'brigadista' ? ' appbar__role--tactical' : '')}>
            {role}
          </div>
        </div>
      </div>
      {right ?? (
        <button className="iconbtn">
          <i data-lucide="bell" width="16" height="16" />
          {notif && <span className="iconbtn__dot" />}
        </button>
      )}
    </div>
  );
};

// Bottom tab bar — two variants for the two profiles
const PhoneTabBar = ({ profile = 'ocupante', active }) => {
  const tabs = profile === 'brigadista'
    ? [
        { id: 'panel',  lbl: 'Panel',  icon: 'layout-dashboard' },
        { id: 'triage', lbl: 'Triage', icon: 'clipboard-check' },
        { id: 'lista',  lbl: 'Lista',  icon: 'users' },
        { id: 'cuenta', lbl: 'Cuenta', icon: 'user' },
      ]
    : [
        { id: 'inicio',  lbl: 'Inicio',  icon: 'home' },
        { id: 'rutas',   lbl: 'Rutas',   icon: 'map' },
        { id: 'dir',     lbl: 'Directorio', icon: 'phone' },
        { id: 'cuenta',  lbl: 'Cuenta',  icon: 'user' },
      ];
  return (
    <nav className="tabbar">
      {tabs.map(t => (
        <button key={t.id} className={'tab' + (t.id === active ? ' is-active' : '')}>
          <i data-lucide={t.icon} />
          {t.lbl.toUpperCase()}
          {t.id === active && <span className="tab__bar" />}
        </button>
      ))}
    </nav>
  );
};

// Top-level phone wrapper. Children are rendered into the .body region.
const Phone = ({
  profile = 'ocupante',
  active = profile === 'brigadista' ? 'panel' : 'inicio',
  time = '10:41',
  appbarRight,
  notif = false,
  hideChrome = false,
  className = '',
  bodyClass = '',
  children,
}) => (
  <div className={'phone ' + className}>
    <PhoneStatusBar time={time} />
    {!hideChrome && <PhoneAppBar profile={profile} notif={notif} right={appbarRight} />}
    {!hideChrome && (
      <div className={'body ' + bodyClass}>
        {children}
      </div>
    )}
    {hideChrome && children}
    {!hideChrome && <PhoneTabBar profile={profile} active={active} />}
    <span className="home-indicator" />
  </div>
);

Object.assign(window, { Phone, PhoneStatusBar, PhoneAppBar, PhoneTabBar });
