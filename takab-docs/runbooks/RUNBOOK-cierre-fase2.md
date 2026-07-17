# RUNBOOK · Cierre de Fase 2 — App móvil (2026-07-17)

> **Estado: código COMPLETO (T-2.00…T-2.14). Ítems auto-verificables PASS con evidencia
> reproducible; 4 GATEs no auto-verificables enumerados con su criterio de aceptación y SIN
> marcar (dispositivo/servicio externo/legal ≠ simulador).**
>
> **Regla dura (heredada de la auditoría de Fase 1):** no se modifica código de producción para
> "pasar" un gate; los gates quedan escritos con su criterio y sin marcar. Todo lo físico
> (biometría, cámara, push del store, cert real) es gate.

---

## 0. Cómo leer este runbook

- **[PASS]** — auto-verificable, con evidencia reproducible (suite/comando/archivo:línea).
- **[GATE-X]** — requiere dispositivo real, servicio externo o decisión humana; **sin marcar**.

Suites de la fase (correr desde la raíz):

```bash
# API
cd api && DATABASE_URL="postgresql+psycopg://takab:takab_dev@localhost:5433/takab_test" \
  uv run pytest -q                       # 893 passed, 3 skipped
cd api && uv run ruff check src tests && uv run ruff format --check src tests
# Web (consola)
cd web && npm run build && npx vitest run # 584 passed
cd web && npx eslint src --max-warnings 0 && npx prettier --check src
# Móvil
cd mobile && npx jest                     # 190 passed
cd mobile && npx tsc --noEmit && npx expo lint   # 0 errores, 0 warnings
# Contrato del SDK (sin drift)
cd shared/sdk-ts && npm run check
```

---

## 1. Cobertura de la spec (pantalla → tarea → evidencia)

| Pantalla / capacidad | Tarea | Evidencia (auto-verificable) |
|---|---|---|
| 0.1–0.4 login/onboarding/enrolamiento | T-2.02/T-2.04 | `mobile/src/auth/*`, `src/app/onboarding/*` |
| 1.1 reposo (SIMULACRO ámbar, jamás crisis) | T-2.07 | `HomeView.test.tsx` |
| 1.2/1.3 crisis (sin magnitud/ETA; `ALERT_SOURCE_CARRIES_ETA=false`) | T-2.05 | `CrisisView.test.tsx`, `machine.test.ts` |
| 1.4 check-in de vida (offline, idempotente) | T-2.06 | `sync.test.ts`, `test_mobile_core::…replay…` |
| 1.5 bloqueo de reingreso (release solo por servidor) | T-2.07 | `timeline.test.tsx` |
| 1.6/1.7/1.8 rutas/directorio/cuenta | T-2.07 | `useCachedQuery.test.tsx`, `DirectoryList.test.tsx`, `AccountView.test.tsx` |
| 1.9 pánico quórum-de-2 | T-2.13 | `test_panic_quorum.py` (7 invariantes), `panic.test.ts` |
| 2.1 dashboard táctico (features 1 s, sin waveform) | T-2.08 | `panel.test.tsx`, `test_ws_authz.py` |
| 2.2 control remoto (intención firmada, ack honesto) | T-2.09 | `test_command_intent.py`, `control.test.ts` |
| 2.3/2.4 cámara forense + daños (hash verificable) | T-2.10 | `test_forensic_evidence.py` (tamper⇒invalid), `structural.test.ts` |
| 2.5/2.6 sync + headcount (roster live <2 s) | T-2.11 | `syncView.test.ts`, `test_mobile_core::…notify_live` |
| 2.7 dictamen + liberación | T-2.12 | `dictamen.test.tsx`, `test_mobile_core::…firma_habitable…` |

**[PASS] Sin stubs silenciosos.** `grep -rn "<Pending" mobile/src/app` → vacío (todas las
pantallas del backlog son reales; los antiguos placeholders declaraban su tarea, no eran stubs).

---

## 2. Hardening (auto-verificable)

- **[PASS] Sin secretos en el bundle.** `mobile/.env` está gitignored (`git check-ignore
  mobile/.env`); solo `EXPO_PUBLIC_*` (IDs de cliente Cognito, dominios, API base — públicos por
  diseño) se inlinean, y solo con lecturas ESTÁTICAS. `grep -rniE "secret|password|private_key"
  mobile/src` → sin coincidencias de valores. Los tokens de sesión y la llave de la BD offline
  viven SOLO en `expo-secure-store` (Keychain/Keystore).
- **[PASS] Almacenamiento cifrado honesto.** La cola/caché offline usan SQLCipher; el badge de
  cifrado (2.5) afirma "AES-256" SOLO si `PRAGMA cipher_version` respondió en runtime
  (`db.ts`), jamás por defecto.
- **[PASS] Lint/tests con cero warnings.** `npx expo lint` y `npx eslint --max-warnings 0`
  limpios en móvil y web; `ruff` limpio en API.
- **[PASS] La superficie sensible jamás confía en el cliente.** Todo comando de actuador se
  firma en la NUBE (HMAC por gateway); el teléfono solo firma una INTENCIÓN verificada contra
  `device_keys` + nonce del servidor de un solo uso (T-2.09); el pánico dispara por el MISMO
  pipeline (T-2.13). La UI se gobierna server-side por `/me.allowed_actions`.

### Certificate pinning — estrategia (decisión de ingeniería, no un hash hardcodeado)

El API se sirve por TLS con certificado **Let's Encrypt** (leaf que rota cada ~60 días). Pinnear
el hash del **leaf** rompería la app en cada renovación → mala práctica. La estrategia adoptada:

1. **Pin al SPKI del emisor** (Let's Encrypt R10/R11 o el ISRG Root X1 como backup), no al leaf,
   vía `expo-build-properties`:
   - **Android:** `network_security_config` con `<pin-set>` (SHA-256 del SPKI del intermedio +
     un **backup pin** del root — regla OWASP: siempre ≥2 pines).
   - **iOS:** ATS + `TrustKit` (o `NSAppTransportSecurity` con pinned public key) por config
     plugin.
2. **Rotación documentada:** cuando el CA cambie de intermedio, se publica una versión con el
   nuevo pin ANTES de que expire el anterior (los dos pines conviven). El backup del root da la
   ventana de gracia. La lista de pines vive en `mobile/certs/pins.json` (a crear en el build de
   producción; **no** en el repo de features).
3. **Verificación:** `GATE-HW` corre un flujo Maestro contra un proxy con cert distinto (mitmproxy)
   y confirma que la conexión FALLA (pinning efectivo).

> **[GATE-HW · pinning]** — requiere el build de producción con los pines reales + verificación
> con mitmproxy en dispositivo. SIN marcar (no se hornean pines de un CA que aún no se fijó para
> producción; hacerlo en el repo de features es un secreto operativo mal ubicado).

---

## 3. E2E (Maestro) — `mobile/.maestro/`

Flujos escritos (evidencia ejecutable de los caminos de la spec §4.2): crisis→check-in→sync
(`01`), táctico foto→daños→Triage (`02`), dictamen→liberación (`03`), pánico quórum-de-2
(`04`), offline en modo avión (`05`) + subflujos de login. Corren contra un **development
build** en dispositivo/emulador con un occupant y un táctico sembrados.

> **[GATE-HW · E2E]** — requiere dispositivo real + occupant/táctico en Cognito + incidente en
> staging. SIN marcar. Incluye la verificación de que los **modos de prueba del gabinete
> (T-1.67/T-1.69) NO disparan pantallas de crisis en el móvil** (garantía server-side: el edge
> en prueba no publica ⇒ no hay incidente ⇒ `phase=idle`).

---

## 4. GATEs de cierre (NO auto-verificables)

### [GATE-DECISIONS] — decisiones de arranque
- **RESUELTO** en T-2.00: decisión #7 (occupant login simple + MFA OPCIONAL ⇒ dos pools
  Cognito), emisor push = SNS platform endpoints, R1–R10 ratificados. Entitlement Critical
  Alerts de Apple **SOLICITADO por Mauricio (2026-07-15)**, aprobación pendiente.
- **Criterio de cierre:** confirmar la aprobación del entitlement de Apple (o dejar vigente el
  fallback time-sensitive documentado).

### [GATE-STORE] — publicación y push físico
- **Pendiente:** credenciales APNs (.p8) / FCM (service account) reales en el módulo Terraform
  `push/` (hoy CONDICIONAL a credenciales; sin ellas el apply no crea las platform apps) +
  `terraform apply` + verificación de bypass de DND en dispositivos.
- **Criterio de cierre:** un push CRISIS real llega a un dispositivo físico con la app cerrada y
  suena con la interrupción configurada; un push OPS (dictamen/headcount) llega sin sonido
  crítico. Tono SASMEX oficial: **pendiente de LICENCIAMIENTO** (hoy `siren.wav` del edge como
  placeholder).

### [GATE-HW] — hardware y biometría
- **Pendiente:** verificación en dispositivo real de (a) firma con Secure Enclave/Keystore +
  attestation (T-2.09), (b) marca de agua horneada en el pixel + hash que el backend verifica
  (T-2.10), (c) cámara forense que JAMÁS escribe a la galería, (d) cert pinning con mitmproxy
  (§2), (e) los E2E de §3, (f) **los modos de prueba del gabinete no alertan móviles**.
- **Criterio de cierre:** los 5 flujos Maestro en verde en dispositivo + tamper de un byte de la
  foto ⇒ Triage la marca "HASH ALTERADO".

### [GATE-LEGAL] — LFPDPPP + marco normativo
- **Pendiente (pregunta abierta #1 del ANALISIS):** el marco normativo citable sigue por
  confirmar. El aviso de privacidad (0.3) y los `compliance_labels` por tenant existen y son
  configurables server-side; hoy vacíos ⇒ la app NO muestra literal normativo alguno (honesto).
- **Criterio de cierre:** legal confirma el marco (¿NOM aplicable? ¿ley estatal de PC?) y se
  cargan los `compliance_labels` del tenant piloto; el aviso de privacidad se revisa con el DPO.

---

## 5. Semilla pendiente (recurrente)

**Sembrar un occupant real** en el pool `us-east-2_P818WYSql` para el login e2e. Bloqueado en
sesión asistida: obtener el `tenant_id` real exige listar PII de Cognito o leer `edge.env` del
Pi (ambos denegados por el clasificador). Mauricio lo corre con `!` o pega el `tenant_id`:

```bash
! aws --profile takab-dev --region us-east-2 cognito-idp list-users \
    --user-pool-id us-east-2_WlAWpxvnn \
    --query 'Users[0].Attributes[?Name==`custom:tenant_id`].Value' --output text
```
