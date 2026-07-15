> ⚠️ **SUPERSEDED (2026-07-15) — DOCUMENTO HISTÓRICO, NO IMPLEMENTAR DESDE AQUÍ.**
> La especificación canónica de la app móvil es **`ESPECIFICACION-APP-MOVIL.md`** (esta misma
> carpeta), que reconcilia este PROMPT contra el estado real del proyecto al cierre de la
> Fase 1.10 — la matriz completa de qué se quedó, qué cambió y qué se eliminó está en su §14.
> Este archivo conserva deliberadamente los términos y supuestos originales (rutas con prefijo
> de versión, roles no canónicos, hardware desactualizado) como registro del punto de partida.
> El backlog ejecutable vive en `takab-docs/TASKS.md · ## Fase 2` (T-2.00…T-2.14).

# PROMPT — Especificación de Implementación · App Móvil TAKAB Ailert (Fase 2 · T-1.31 reactivada)

> **Plan: Claude Code (Fable 5, máximo esfuerzo)**
> **ejecución: Claude Code (Opus, máximo esfuerzo)**
> **Repo:** `MauBautista/alertamiento-sismico`
> **Rol:** Ejecutor de implementación. Este documento es la especificación canónica de la aplicación móvil. No improvises fuera de lo aquí definido; si detectas una contradicción entre este documento y el código existente, **detente y repórtala**, no la resuelvas en silencio.
> **Idioma de trabajo:** Español para comunicación, documentación y UI. Inglés para identificadores de código, rutas y términos técnicos.

---

## 0. Contexto del proyecto

TAKAB Technology es una plataforma SaaS multi-tenant de alertamiento sísmico temprano, monitoreo estructural y continuidad operativa para instalaciones críticas en México. El sistema ya tiene desplegado y verificado:

- **Edge:** Raspberry Pi 5 + Raspberry Shake RS4D por edificio, con receptor SASMEX WR-1 (contacto seco GPIO), motor de reglas local determinista, arbitraje de demandas GPIO bajo RLock, comandos firmados con HMAC (nonce de un solo uso, TTL corto, comparación constant-time, framing con separación de dominio).
- **Cloud:** AWS IoT Core (mTLS X.509 por dispositivo), SQS, ECS Fargate, PostgreSQL 16 + TimescaleDB + PostGIS (`timescale/timescaledb-ha:pg16`), Cognito, S3. IaC con Terraform.
- **Frontend web (Consola SOC):** React 18 + TypeScript + Vite, TanStack Query, Zustand, MapLibre GL JS, consumiendo el SDK tipado `@takab/sdk` contra REST + WebSocket reales (sin mocks).

La app móvil fue diferida por diseño (T-1.31). Este documento la reactiva como **Fase 2**. La app es el **complemento móvil del SOC**, no un producto independiente: cada dato que genera alimenta la consola web (especialmente la pestaña Triage Estructural) y cada estado que muestra proviene de la nube o del gabinete edge local.

### 0.1 Fuentes de verdad (leer ANTES de escribir código)

1. **Design system móvil:** carpeta **`/takab-docs/design/app`** del repo. Contiene el diseño exportado desde Claude Design (`app/index.html` y assets). **Es la fuente de verdad visual de la app.** Extrae de ahí: paleta, tipografía, espaciado, radios, componentes, estados de color por severidad, y layout de cada pantalla.
2. **Design system web existente:** tokens de la consola SOC (React web). La app debe **integrarse al mismo design system**: donde el diseño móvil y el web definan el mismo concepto (ej. color CRÍTICO, color ADVERTENCIA, verde OPERATIVO, tipografía monoespaciada para datos técnicos), deben resolver al **mismo token**. Crea un paquete compartido de tokens (ver §9).
3. **Blueprint funcional v1 de la app** (12 pantallas, 2 perfiles) — resumido e incorporado en §7 de este documento, con correcciones. **Donde este documento contradiga al blueprint o a los mockups, gana este documento** (las correcciones son deliberadas, ver §2.1).
4. **`@takab/sdk`** — el SDK tipado existente. La app móvil NO duplica clientes HTTP/WS: extiende el SDK si falta algo, en el paquete del SDK, con tipos exportados.

---

## 1. Alcance de la Fase 2

**Incluye:**
- App móvil iOS + Android, dos perfiles de usuario: **Ocupante** (Perfil 1, 5 pantallas) y **Brigadista/Seguridad** (Perfil 2, 7 pantallas).
- Notificaciones push de alta prioridad (Critical Alerts iOS / canal high-priority Android).
- Modo crisis instruction-first, check-in de vida, bloqueo de reingreso.
- Dashboard táctico del brigadista, control remoto edge con confirmación en 2 pasos, cámara forense con marca de agua, formulario de daños, sincronización offline-first, headcount, recepción de dictamen.
- Extensión del `@takab/sdk` para los endpoints móviles nuevos.
- Backend: endpoints nuevos mínimos indispensables (roster, check-ins, reportes de daño, evidencias, tokens push). Reutiliza todo lo existente (incidentes, dictámenes, comandos edge).

**NO incluye (fuera de alcance, no lo implementes):**
- IA de ningún tipo. **Nunca en el camino determinista de seguridad, y en esta fase, en ninguna parte de la app.**
- Cuenta regresiva T-MINUS ni magnitud preliminar en tiempo real (ver §2.1 — bloqueado).
- App de escritorio, watch, widgets.
- Streaming continuo de forma de onda cruda al teléfono. El sismograma en vivo del brigadista (pantalla 2.1) usa el mismo canal WebSocket decimado que ya consume la consola web — no abras un canal nuevo hacia el RS4D.

---

## 2. Principios no negociables (heredados y bloqueados)

Estos principios ya están probados en producción y **no se renegocian en la app móvil**:

1. **Autonomía local total del edge.** El teléfono es un espejo y un canal de reporte; jamás es prerequisito de ninguna función de seguridad de vida. Si todos los teléfonos del edificio están apagados, el sistema protege igual.
2. **Sin IA en el camino determinista de seguridad.**
3. **Logging orientado a eventos**, no por intervalos.
4. **Separación estricta edge/cloud.** La app habla con la nube (REST/WS vía `@takab/sdk` + Cognito). **La app nunca habla directamente con el gabinete edge** por red local, BLE ni ningún otro medio. Los comandos al edge viajan: app → cloud → (comando firmado HMAC con nonce/TTL) → edge. Esto preserva la auditoría y el modelo de arbitraje de demandas GPIO.
5. **Evidencia de cumplimiento nunca sujeta a poda de retención:** fotos forenses, reportes de daño, check-ins, dictámenes y logs de acciones críticas son evidencia de incidente.
6. **Sin credenciales AWS en directorios rastreados por git.** La app usa Cognito (User Pool + Identity Pool con credenciales efímeras y scoped para subida directa a S3 de evidencias, si se opta por esa vía).

### 2.1 Correcciones de honestidad respecto a los mockups (OBLIGATORIAS)

Los mockups del blueprint contienen tres elementos que **contradicen decisiones arquitectónicas bloqueadas** o exageran capacidades. Corrígelos así:

**A. T-MINUS / cuenta regresiva y "M 6.8 PRELIMINAR" — PROHIBIDOS.**
El WR-1 de SASMEX entrega únicamente un cierre de contacto seco: un booleano. No transporta magnitud, epicentro ni tiempo estimado de arribo de onda S. Mostrar un cronómetro "15s" o "M 6.8 PRELIMINAR" sería fabricar datos en una pantalla de vida o muerte.

Diseño corregido de las pantallas de crisis (1.2 / 1.3):
- **Instruction-first:** la instrucción gigante ("EVACÚE AHORA" / "REPLIÉGUESE") ES la pantalla. Ocupa la jerarquía visual que el mockup daba al cronómetro.
- Debajo de la instrucción: **T+ transcurrido** desde la recepción de la alerta (`T+04s`, contador ascendente). Es un dato real y verificable, útil y honesto.
- Fuente del evento etiquetada con datos reales según origen:
  - `SASMEX · WR-1` → sin magnitud, sin epicentro. Solo "ALERTA SÍSMICA SASMEX".
  - `DETECCIÓN LOCAL` → puede mostrar PGA instrumental del sitio (dato real del RS4D): "PGA 0.15g · REGLAS LOCALES".
  - `CUÓRUM` → estaciones corroborantes.
- La magnitud **solo aparece post-evento** en pantallas de historial/dictamen, obtenida del catálogo oficial (SSN) vía backend, etiquetada como "SSN · dato oficial posterior al evento".
- Estructura el componente de crisis para que, si en el futuro se integra una fuente que sí transporte magnitud/ETA por dato (no por contacto seco), el campo pueda activarse por feature flag **sin tocar el layout**. Nombra el flag `ALERT_SOURCE_CARRIES_ETA` y déjalo `false` con un comentario que remita a esta sección.

**B. "FIRMA HSM" — reformular.** Los teléfonos no tienen HSM. Lo correcto y lo que implementarás:
- Llave de firma por operador generada en **Secure Enclave (iOS) / Android Keystore (StrongBox si disponible)**, no exportable.
- Las acciones críticas del brigadista (silenciar sirena, disparo manual, cierre de headcount, firma de reportes) se firman con esa llave + JWT de Cognito vigente + nonce del servidor. El backend valida y registra en `audit_log`.
- El comando resultante hacia el edge sigue usando el esquema HMAC existente (lo firma la nube, no el teléfono). El teléfono firma la **intención auditada**; la nube firma el **comando ejecutable**.
- En UI y docs escribe "firma con llave respaldada por hardware", nunca "HSM".

**C. Strings de cumplimiento normativo — jamás hardcodeados.** Ya existe el hallazgo `TriageHistory.jsx:65` (string de cumplimiento hardcodeado) y el antecedente de NOM-003-SCT citada incorrectamente (es un estándar de etiquetado de transporte, no sísmico). Regla para la app: **toda referencia normativa proviene de configuración del tenant servida por el backend** (`GET /v1/tenants/{id}/compliance-labels` o campo en el payload de sitio). Cero literales normativos en el bundle. Si el backend no lo expone aún, créalo en esta fase.

---

## 3. Stack técnico

| Capa | Decisión | Justificación |
|---|---|---|
| Framework | **React Native 0.7x + TypeScript estricto** | Reutiliza el equipo/patrones React de la consola SOC y partes del `@takab/sdk` |
| Toolchain | **Expo SDK (dev client / prebuild, NO Expo Go)** | Critical Alerts iOS y canales Android custom requieren código nativo; Expo Go no los soporta |
| Estado servidor | TanStack Query (misma versión mayor que web) | Paridad de patrones con la consola |
| Estado local | Zustand | Paridad con la consola |
| Navegación | React Navigation (stack + tabs por perfil) | Estándar |
| Storage seguro | `expo-secure-store` / Keychain / Keystore para tokens y llaves; **SQLite cifrado (SQLCipher u op-sqlite + cifrado) para la cola offline** | §2.1-B y §7 (2.5) |
| Push | FCM (Android) + APNs (iOS) vía backend propio (SNS o directo) | Ver §6 |
| Mapas | MapLibre GL Native **solo si una pantalla lo exige**; el blueprint actual no requiere mapa en móvil — no lo agregues especulativamente | Peso de bundle |
| Cámara | `expo-camera` + composición de marca de agua en pixel (ver §7, 2.3) | |
| Monorepo | La app vive en `apps/mobile/` del repo; tokens compartidos en `packages/design-tokens/`; SDK en su paquete existente | §9 |

**Nota Expo/nativo:** documenta en el README de `apps/mobile/` qué módulos requieren prebuild y qué entitlements requieren aprobación de Apple (Critical Alerts requiere solicitud explícita a Apple — márcalo como `GATE-STORE`, ver §11).

---

## 4. Arquitectura de la app

```
apps/mobile/
├── app/                        # rutas (expo-router o react-navigation)
│   ├── (occupant)/             # Perfil 1
│   └── (brigade)/              # Perfil 2
├── src/
│   ├── features/
│   │   ├── alert/              # máquina de estados de crisis (§4.1)
│   │   ├── checkin/
│   │   ├── reentry/
│   │   ├── cabinet/            # dashboard táctico + control remoto
│   │   ├── forensics/          # cámara + formulario de daños
│   │   ├── syncqueue/          # cola offline-first (§4.2)
│   │   ├── headcount/
│   │   └── dictamen/
│   ├── services/
│   │   ├── push/               # registro de token, handlers, canales
│   │   ├── crypto/             # llaves hardware-backed, firma de acciones
│   │   └── sdk/                # instancia configurada de @takab/sdk
│   ├── stores/                 # zustand
│   └── ui/                     # componentes que consumen design-tokens
```

### 4.1 Máquina de estados de crisis (núcleo de la app)

Estado global único, determinista, sin IA, dirigido por eventos del backend (WS push + push notification como despertador). Estados:

```
IDLE → ALERT_ACTIVE → SHAKING_CONCLUDED → CHECKIN_PENDING → CHECKIN_SENT
                                        ↘ REENTRY_BLOCKED → REENTRY_APPROVED → IDLE
```

Reglas:
- La transición a `ALERT_ACTIVE` toma la pantalla completa (pantallas 1.2/1.3) y no puede ser descartada por el usuario mientras el backend reporte incidente abierto en su sitio.
- `SHAKING_CONCLUDED` la emite el backend (evento de cierre de ventana de movimiento del edge). El teléfono **nunca decide por sí mismo** que el movimiento terminó.
- Si la app estaba cerrada, la push de alta prioridad la despierta y el primer render consulta `GET /v1/sites/{siteId}/state` para reconstruir el estado — la push es despertador, **no** fuente de verdad.
- Todo cambio de estado se registra localmente con timestamp monotónico y se sincroniza (evidencia de tiempos de reacción, orientado a eventos).
- La instrucción (EVACÚE / REPLIÉGUESE) se resuelve por el **piso registrado del usuario** contra la política del edificio servida por backend (`floor_policy`: `evacuate` | `shelter`). Sin heurísticas locales.

### 4.2 Cola offline-first (compartida por check-ins, reportes, fotos)

- SQLite cifrado. Cada elemento: `{id, type, payload, blobs[], created_at, state}` con `state ∈ {pending, uploading, synced, failed}`.
- Subida automática al recuperar conectividad (listener de red + reintentos con backoff exponencial + jitter).
- Blobs (fotos) se suben a S3 mediante URL prefirmada emitida por backend **o** credenciales efímeras de Identity Pool scoped al prefijo del incidente — elige URL prefirmada (más simple de auditar) salvo que el tamaño de lote lo impida.
- **Cadena de custodia:** el hash SHA-256 de cada blob se calcula en el dispositivo al momento de captura, se incluye firmado en el payload del reporte, y el backend lo verifica al recibir el blob. Discrepancia = rechazo + registro en `audit_log`.
- La cola es visible en UI (pantalla 2.5) con estado por elemento.
- Nada se borra del dispositivo hasta confirmación `synced` del backend + margen de 24 h.

---

## 5. Contratos de API (extensiones al backend + SDK)

Reutiliza los endpoints existentes de incidentes, sitios, dictámenes y comandos. Agrega (y tipa en `@takab/sdk`):

| Método y endpoint | Propósito | Auth |
|---|---|---|
| `POST /v1/mobile/push-tokens` | Registro/rotación de token FCM/APNs, ligado a usuario+dispositivo+sitio | OIDC |
| `GET /v1/sites/{siteId}/mobile-state` | Estado consolidado para la app: incidente activo, fase, instrucción por piso, punto de reunión, bloqueo de reingreso | OIDC |
| `POST /v1/incidents/{id}/checkins` | Check-in de vida `{status: safe|help, location?, floor, ts_device}` | OIDC |
| `GET /v1/incidents/{id}/roster` | Roster asignado al brigadista con estado de check-in por persona | OIDC (rol brigade+) |
| `POST /v1/incidents/{id}/damage-reports` | Formulario de daños + hashes de evidencias | OIDC + firma dispositivo |
| `POST /v1/incidents/{id}/evidence-uploads` | Solicita URLs prefirmadas para blobs (devuelve por hash) | OIDC |
| `POST /v1/edge-commands` | Ya existe para la consola; extiende validación para origen móvil con firma de dispositivo (§2.1-B) | OIDC + firma dispositivo |
| `GET /v1/tenants/{id}/compliance-labels` | Strings normativos por tenant (§2.1-C) | OIDC |

Notas:
- `location` en check-in de ayuda: última posición GPS conocida **solo si el usuario otorgó permiso**; alternativa siempre disponible: piso asignado. Ver §8 (LFPDPPP).
- `ts_device` viaja junto con `ts_server` asignado al recibir; ambos se persisten (análisis de latencias, honestidad de tiempos).
- Todos los endpoints con RLS por tenant como el resto de la plataforma.

---

## 6. Notificaciones push

- **iOS:** APNs con **Critical Alerts** (`sound.critical`) para alertas sísmicas — se salta No Molestar y silencio. Requiere entitlement aprobado por Apple: **`GATE-STORE`**, no verificable en repo. Implementa fallback: sin entitlement, usa `interruption-level: time-sensitive`.
- **Android:** canal de notificación dedicado `seismic_alert` con `IMPORTANCE_HIGH`, sonido oficial de alerta sísmica empaquetado, `setBypassDnd(true)` (requiere acceso a política de notificaciones concedido por el usuario en onboarding — flujo guiado obligatorio).
- Dos clases de push, jamás mezcladas:
  1. `CRISIS` (alerta activa, cambio de fase): máxima prioridad, sonido crítico.
  2. `OPS` (dictamen recibido, sync completada, recordatorio de simulacro): prioridad normal.
- El payload de push lleva solo `{type, siteId, incidentId, phase}` — **sin datos sensibles** (aparecen en lockscreen). El contenido real se obtiene por API al abrir.
- Onboarding verifica y re-verifica permisos de notificación con pantalla de estado dedicada ("Su teléfono NO recibirá alertas" en rojo si faltan permisos). Este es un producto de seguridad de vida: el estado de permisos degradados debe ser imposible de ignorar.

---

## 7. Especificación pantalla por pantalla

Implementa exactamente las 12 pantallas. El layout visual sale de `/takab-docs/design/app`; aquí van comportamiento, datos, estados y criterios de aceptación. **Directivas de diseño heredadas:** Perfil 1 = cero carga cognitiva, un toque, textos gigantes, una decisión por pantalla. Perfil 2 = conciencia situacional y recopilación forense.

### PERFIL 1 · OCUPANTE

#### 1.1 Modo reposo
- Banner de estado del edificio: `SEGURO` (verde) / degradaciones si el sitio reporta `DEGRADADO` o `SIN ENLACE` (mismos tokens de color que Flota Edge en la consola).
- Directorio de brigadistas del piso del usuario con llamada de un toque (`tel:`).
- Próximo simulacro + resultado del último (`GET /v1/sites/{siteId}/drills` — si no existe el endpoint, créalo simple).
- Enlaces a ruta de evacuación (PDF/imagen por piso, servido de S3 vía URL firmada, **cacheado localmente** para disponibilidad offline) y manual operativo.
- Badge de fuente: "SASMEX ENLAZADO" solo si el estado del gabinete reporta WR-1 con enlace OK — dato real, no decorativo.
- **Aceptación:** con el backend reportando sitio normal, la pantalla renderiza estado verde; al matar la red, muestra el último estado conocido con indicador "datos de hace X min" — nunca finge tiempo real.

#### 1.2 Crisis · "EVACÚE AHORA" (política de piso: evacuate)
- Toma total de pantalla, fondo rojo del design system, disparo por push CRISIS + verificación por API (§4.1).
- Jerarquía corregida (§2.1-A): instrucción gigante → ruta de salida asignada ("Diríjase a la escalera norte. No use elevadores.") → `T+` ascendente → etiqueta de fuente real del evento.
- Emite el sonido oficial de alerta en loop mientras `ALERT_ACTIVE` (respetando que Critical Alert ya sonó).
- Sin botones descartables. Sin navegación.
- **Aceptación:** simular push CRISIS en dev → la pantalla aparece <1 s tras despertar la app; con `source: sasmex_wr1` NO se renderiza ningún campo de magnitud/ETA (test de snapshot que falle si aparecen).

#### 1.3 Crisis · "REPLIÉGUESE" (política de piso: shelter)
- Idéntica estructura, variante ámbar. Zona de seguridad asignada + advertencia de cristales.
- La selección 1.2 vs 1.3 la hace `floor_policy` del backend (§4.1). Un mismo edificio puede tener ambas activas simultáneamente en distintos pisos.
- **Aceptación:** test parametrizado piso bajo/alto → instrucción correcta.

#### 1.4 Post-sismo · Check-in de vida
- Transición automática al recibir `SHAKING_CONCLUDED`.
- Exactamente dos botones gigantes: verde "ESTOY A SALVO" / rojo "NECESITO AYUDA".
- "Necesito ayuda" adjunta última ubicación GPS conocida **si hay permiso**; si no, piso asignado. Muestra al usuario qué se enviará antes de enviar (el mockup ya lo hace: "UBICACIÓN QUE SE ENVIARÁ").
- Encola en la cola offline (§4.2) — el check-in DEBE funcionar sin red y sincronizar después.
- Tras enviar: confirmación mínima + paso a `REENTRY_BLOCKED` si aplica.
- **Aceptación:** check-in en modo avión queda `pending` y sincroniza solo al recuperar red; el roster del brigadista (2.6) lo refleja al sincronizar.

#### 1.5 Post-sismo · Bloqueo de reingreso
- Letrero rojo persistente "Reingreso Prohibido · Evaluación Estructural en curso" + línea de tiempo del proceso (evento registrado → check-in recibido → inspección por piso → dictamen → reingreso), alimentada por eventos reales del incidente.
- Punto de reunión asignado visible.
- Se libera **únicamente** cuando la consola SOC emite el dictamen de reingreso (evento `REENTRY_APPROVED`). Sin override local.
- Strings normativos desde compliance-labels (§2.1-C).
- **Aceptación:** ningún camino de código local puede transicionar a `REENTRY_APPROVED` sin evento del backend (test).

### PERFIL 2 · BRIGADISTA / SEGURIDAD

#### 2.1 Dashboard táctico local
- Salud del gabinete en tiempo real (WS): batería/UPS, latencia MQTT, offset NTP, estado RS4D, temperatura — **los mismos campos y umbrales de color que la vista Flota Edge de la consola** (paridad de tokens).
- Sismograma en vivo: canal WS decimado ya existente de la consola. Si el WS cae, congela con marca "SIN ENLACE · último dato HH:MM:SS".
- Checklist de actuadores BMS post-evento (sirenas, válvulas, retenedores, elevadores) con estados reales reportados por edge — reutiliza el modelo de arbitraje de demandas: lo que se muestra es el estado del relé recalculado, no la última orden enviada.
- Accesos rápidos a 2.2.
- **Aceptación:** los valores mostrados provienen del mismo payload que consume la consola web (sin transformaciones divergentes).

#### 2.2 Control remoto Edge · confirmación en 2 pasos
- Acciones: silenciar sirena local, disparo manual. Flujo: (paso 1) checklist de precondiciones confirmadas por el operador (edificio evacuado, headcount completo — con estado real del headcount prellenado, no checkbox ciego) → (paso 2) deslizar para activar.
- Cada acción: firmada con llave hardware-backed del operador (§2.1-B) + JWT vigente + nonce solicitado al backend justo antes del deslizamiento (TTL corto). El backend construye el comando HMAC hacia el edge.
- "Silenciar sirena" es una **retirada de demanda del canal manual** en el modelo de arbitraje — si otra demanda activa (alerta vigente) mantiene la sirena, la UI lo explica ("La sirena permanece activa por alerta vigente") en lugar de fingir éxito.
- Toda acción produce entrada en `audit_log` con identidad del operador y hash de la firma.
- Solo roles autorizados ven esta pantalla; la acción es reintentable con autorización del SOC según política existente.
- **Aceptación:** replay de un comando (mismo nonce) es rechazado por backend; el silenciado durante alerta activa no apaga la sirena y la UI comunica el porqué.

#### 2.3 Cámara forense integrada
- Captura con marca de agua **horneada en el pixel** (composición sobre el bitmap antes de persistir, no overlay de UI ni EXIF-only): fecha-hora exacta (fuente: hora del dispositivo + offset NTP conocido del último sync, ambos registrados), coordenadas GPS, **PGA registrado por el gabinete en ese momento** (consultado al backend; si no hay red, se estampa "PGA: pendiente de sync" y el valor se adjunta al sincronizar — nunca se inventa), ID del brigadista.
- Además de la marca visual: hash SHA-256 del archivo final calculado en captura (§4.2), metadatos duplicados en JSON firmado adjunto al reporte.
- Fotos van a la cola offline; jamás a la galería del sistema.
- **Aceptación:** alterar un byte del archivo tras la captura invalida la verificación de hash en backend.

#### 2.4 Formulario rápido de daños
- Categorías marcables (daño estructural / no estructural / fuga agua / fuga gas / daño eléctrico / personas atrapadas o heridas) con severidad por categoría, ligadas a las evidencias de 2.3.
- "Personas atrapadas / heridas" dispara prioridad máxima: el reporte salta al frente de la cola y, con red, genera notificación inmediata al SOC.
- Payload firmado (§2.1-B). Alimenta directamente la pestaña Triage Estructural de la consola.
- **Aceptación:** un reporte creado en móvil aparece en Triage de la consola con sus evidencias y hashes verificados.

#### 2.5 Sincronización asíncrona · offline-first
- UI de la cola (§4.2): elementos con estado, progreso de subida, reintento manual, tamaño pendiente.
- Banner de modo offline con explicación tranquila (el mockup: "sus capturas y reportes se guardan localmente…").
- Cifrado local en reposo; badge "AES-256" solo si es literalmente cierto en la implementación elegida — verifica el cifrado real de SQLCipher/alternativa antes de rotular.
- **Aceptación:** ciclo completo avión→captura→formulario→red→sync automática sin intervención, con estados visibles en cada paso.

#### 2.6 Headcount · pase de lista
- Roster asignado al brigadista (`GET .../roster`) cruzado con check-ins en tiempo real (WS).
- Contadores: a salvo / necesitan ayuda / no reportados. Filtro "No reportados" con llamada directa de un toque.
- Marcación manual por el brigadista ("verificado en persona") como check-in delegado, firmado por el brigadista, distinguible en datos del check-in propio del ocupante.
- Cierre de headcount (todos contabilizados) es acción firmada — es precondición del paso 1 de 2.2.
- **Aceptación:** check-in del ocupante (1.4) actualiza el roster del brigadista vía WS en <2 s con red.

#### 2.7 Recepción de dictamen de reingreso
- Al firmarse el dictamen en la consola: push OPS + pantalla con certificado (PDF descargado y cacheado) "Edificio Aprobado para Reingreso", folio, firmante, vigencia.
- Habilita al brigadista a dar indicación verbal; botón "Notificar pisos" dispara la liberación de las pantallas 1.5 de los ocupantes (evento backend, no acción local).
- El PDF es el mismo artefacto que genera la consola (dictamen PDF existente) — no generes uno paralelo.
- **Aceptación:** flujo consola-firma → push → PDF visible → ocupantes liberados, verificable en staging.

---

## 8. Seguridad y privacidad

- **AuthN:** Cognito (mismos User Pools que la consola), flujo con PKCE, refresh seguro en Keychain/Keystore. Sesiones de ocupante de larga vida (la app debe alertar sin pedir login en plena crisis); acciones de brigadista siempre re-verifican token vigente.
- **AuthZ:** roles (`occupant`, `brigade`, `security_lead`) en claims; el perfil de UI se deriva del rol, y el backend re-valida cada acción (nunca confíes en la UI).
- **LFPDPPP:** GPS solo con consentimiento explícito registrado; el check-in de ayuda funciona sin GPS (piso asignado). Aviso de privacidad accesible desde onboarding y cuenta. Roster y check-ins son datos personales: RLS estricta, sin exposición cross-tenant, retención según política de evidencia (no poda para evidencia de incidente, sí para datos operativos rutinarios).
- **Transporte:** TLS con certificate pinning contra los endpoints de API/WS (con mecanismo de rotación de pins documentado).
- **Sin secretos en el bundle.** Config remota por entorno.
- Registra en `audit_log` toda acción crítica móvil con: usuario, dispositivo, firma, nonce, resultado.

---

## 9. Integración de design system (web + móvil)

1. Crea `packages/design-tokens/` en el monorepo: tokens en formato agnóstico (JSON/TS) → exportados como (a) CSS variables para la consola web y (b) objeto TS para React Native.
2. **Proceso:** extrae los tokens del diseño en `/takab-docs/design/app` (colores, tipografías, escalas, radios, severidades) y **reconcíliales contra los tokens actuales de la consola**. Donde haya conflicto de valor para el mismo concepto semántico (ej. rojo crítico), documenta la diferencia en `takab-docs/design/DESIGN-TOKENS-RECONCILIATION.md` y propón el valor unificado — **no unifiques silenciosamente**: la consola en producción no debe cambiar de color como efecto colateral de esta fase sin decisión explícita.
3. Migra la consola a consumir el paquete de tokens **solo mediante alias sin cambio visual** en esta fase (mapping 1:1 de sus valores actuales).
4. Tipografía de datos técnicos (monoespaciada), badges de severidad (CRÍTICO/ADVERTENCIA/NORMAL/DEGRADADO/SIN ENLACE) y semáforos deben ser componentes con el mismo contrato semántico en ambas plataformas.

---

## 10. Testing

| Tipo | Alcance | Herramienta |
|---|---|---|
| Unit | Máquina de estados de crisis, cola offline, firma de acciones, resolución de instrucción por piso, watermark determinista | Jest + RTL (RN) |
| Snapshot de honestidad | Las pantallas 1.2/1.3 con `source: sasmex_wr1` NO contienen magnitud/ETA; strings normativos nunca literales | Jest snapshot + lint rule custom |
| Integración | SDK contra backend en staging: check-ins, reportes, evidencias con verificación de hash, nonce replay rechazado | Jest + entorno staging |
| E2E | Flujos: crisis→check-in→sync; brigadista: foto→formulario→sync→consola; dictamen→liberación | Maestro (preferido por simplicidad) o Detox |
| Offline | Todos los flujos de §4.2 en modo avión | E2E + mocks de red |

Mantén la disciplina existente: `ruff`-equivalente para RN es ESLint+Prettier con config del repo; cero warnings; tests pasando antes de cada commit.

---

## 11. Marcadores GATE (no auto-verificables en repo)

Marca en el runbook de cierre de fase, como en la auditoría existente:

- `GATE-STORE`: entitlement Critical Alerts de Apple (requiere solicitud/aprobación); publicación TestFlight/Play Internal; comportamiento real de bypass DND en dispositivos físicos.
- `GATE-HW`: silenciado de sirena end-to-end contra gabinete físico con alerta activa (verificación del arbitraje de demandas desde móvil); latencia real push→pantalla de crisis en red celular; estampado de PGA del gabinete en foto forense con evento real o simulado en hardware.
- `GATE-LEGAL`: aviso de privacidad LFPDPPP revisado; textos de compliance-labels validados con el marco normativo correcto (NO NOM-003-SCT).

---

## 12. Convenciones de repo y ejecución

- **Commits:** Conventional Commits, autoría única de Mauricio, **cero footers de co-autoría de IA ni anotaciones "generated with"**.
- **Una tarea por sesión** de Claude Code: revisa en plan mode, ejecuta en accept-edits. No mezcles fases.
- Orden de implementación sugerido (una tarea = una sesión):
  1. `T-2.01` — `packages/design-tokens/` + reconciliación + alias en consola (sin cambio visual).
  2. `T-2.02` — Scaffold `apps/mobile/` (Expo prebuild, navegación por perfil, auth Cognito, instancia SDK).
  3. `T-2.03` — Backend: endpoints móviles de §5 + RLS + tipos en SDK.
  4. `T-2.04` — Push (canales, tokens, onboarding de permisos, fallbacks).
  5. `T-2.05` — Máquina de estados de crisis + pantallas 1.2/1.3 (con tests de honestidad).
  6. `T-2.06` — Cola offline cifrada + check-in 1.4.
  7. `T-2.07` — Pantallas 1.1 y 1.5.
  8. `T-2.08` — Dashboard táctico 2.1 (reuso de WS de consola).
  9. `T-2.09` — Firma hardware-backed + control remoto 2.2.
  10. `T-2.10` — Cámara forense 2.3 + formulario 2.4.
  11. `T-2.11` — Sync UI 2.5 + headcount 2.6.
  12. `T-2.12` — Dictamen 2.7 + liberación de reingreso.
  13. `T-2.13` — E2E, hardening, runbook de cierre con GATEs.
- Al terminar cada tarea: tests + lint limpios, y actualización del documento de estado de fase en `takab-docs/`.

## 13. Qué NO hacer (resumen ejecutivo para Claude Code)

1. No renderices T-MINUS ni magnitud preliminar en tiempo real. Nunca. (§2.1-A)
2. No conectes el teléfono directamente al gabinete edge por ningún canal.
3. No pongas IA en ninguna parte de esta fase.
4. No hardcodees strings normativos ni etiquetas de cumplimiento.
5. No dupliques cliente HTTP/WS fuera de `@takab/sdk`.
6. No cambies colores/tokens de la consola en producción como efecto colateral.
7. No guardes fotos forenses en la galería del sistema ni pierdas la cadena de custodia (hash en captura).
8. No dejes stubs silenciosos: todo placeholder debe fallar ruidosamente o reportarse como hallazgo, siguiendo la disciplina de auditoría de honestidad del proyecto.
