# TAKAB Ailert · App móvil

Complemento móvil del SOC (Fase 2). **Spec canónica:**
`takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md` · **backlog:**
`takab-docs/TASKS.md · ## Fase 2`. Este directorio nace en T-2.02 (scaffold);
las pantallas llegan por tarea (cada placeholder declara la suya).

## Stack

Expo SDK 57 (React Native 0.86 · React 19) con **dev client / prebuild — NO
Expo Go** (Critical Alerts iOS y canales Android custom exigen código nativo).
TypeScript estricto · expo-router (grupos `(occupant)` / `(brigadista)`) ·
TanStack Query · Zustand · `@takab/sdk` y `@takab/design-tokens` por `file:`
(TS crudo, sin build; Metro observa `shared/` — ver `metro.config.js`).

## Correr en desarrollo

```bash
npm install
npx expo prebuild            # genera android/ ios/ (CNG: van gitignorados)
npx expo run:android         # o run:ios — compila el dev client
```

Checks (los mismos del job `mobile` de CI):

```bash
npm test                     # jest (unit)
npm run typecheck            # tsc --noEmit
npx expo lint                # eslint (config expo flat)
```

## Configuración (EXPO_PUBLIC_*, sin secretos)

Los IDs de pool/cliente y dominios son identificadores públicos
(`takab-docs/specs/cognito-pool-v1.md` §1); salen de
`terraform -chdir=infra/terraform/envs/dev output` tras el apply:

| Variable | Output de Terraform |
|---|---|
| `EXPO_PUBLIC_API_BASE_URL` | URL del API (misma que la consola) |
| `EXPO_PUBLIC_COGNITO_OCCUPANTS_ISSUER` | `occupants_issuer` |
| `EXPO_PUBLIC_COGNITO_OCCUPANTS_CLIENT_ID` | `occupants_client_id` |
| `EXPO_PUBLIC_COGNITO_OCCUPANTS_DOMAIN` | `occupants_hosted_ui_domain` |
| `EXPO_PUBLIC_COGNITO_TACTICAL_ISSUER` | `issuer` (pool principal) |
| `EXPO_PUBLIC_COGNITO_TACTICAL_CLIENT_ID` | `mobile_tactical_client_id` |
| `EXPO_PUBLIC_COGNITO_TACTICAL_DOMAIN` | `hosted_ui_domain` |

Un pool sin configurar se DECLARA en la pantalla de login (botón deshabilitado
con aviso); jamás se finge. Las lecturas de env son expresiones estáticas
`process.env.EXPO_PUBLIC_X` (el acceso dinámico no se inlinea).

## Autenticación — dos pools (decisión #7 · T-2.00)

| Perfil | Pool | MFA | Sesión |
|---|---|---|---|
| `occupant` | `takab-*-occupants` | **OPCIONAL** (opt-in TOTP desde Cuenta) | refresh 90 días — alerta sin login en crisis |
| táctico (`brigadista`, `security_guard`, `inspector`, `building_admin`) | pool principal | **ON** (no negociable, RBAC §4.3) | refresh 24 h — las acciones re-verifican |

Hosted UI + código + PKCE (`expo-auth-session`); tokens SOLO en
Keychain/Keystore (`expo-secure-store`). El deep link `takab://auth/callback`
DEBE coincidir con el `scheme` de `app.json` y con `mobile_callback_urls` del
módulo Terraform `identity`. El grupo de rutas es **server-driven** con
default-deny: `gateFor(/me)` (`src/auth/profileGate.ts`); el gating fino por
`allowed_actions` llega con T-2.03.

## Módulos que exigen prebuild / entitlements

- **Ya en uso:** `expo-dev-client`, `expo-secure-store` (Keychain/Keystore).
- **Próximos:** push con Critical Alerts iOS + canal `seismic_alert` Android
  (T-2.04), cámara forense (T-2.10).
- **`GATE-STORE` (no auto-verificable):** entitlement **Critical Alerts** de
  Apple — solicitud INICIADA por Mauricio (2026-07-15), pendiente de
  aprobación; fallback `interruption-level: time-sensitive` (spec §6). Bypass
  de No Molestar en Android requiere flujo guiado de permisos (pantalla 0.2,
  T-2.04). Verificación física en dispositivos = `GATE-STORE`/`GATE-HW`.

## Reglas que esta app NO rompe (spec §13)

Sin cuenta regresiva ni magnitud preliminar en pantallas de crisis; el
teléfono JAMÁS habla directo con el gabinete; sin IA en esta fase; strings
normativos solo del backend; tokens visuales solo de `@takab/design-tokens`;
sin stubs silenciosos — todo placeholder declara su tarea.
