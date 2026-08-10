# E2E de la app móvil (T-2.14 · Maestro)

Flujos end-to-end de los caminos críticos de la spec §4.2. Requieren un occupant
y un táctico sembrados en Cognito (`make cloud-mobile-users`) y, salvo el 04, un
sitio con incidente activo en staging.

## Requisitos
- [Maestro](https://maestro.mobile.dev) instalado (`curl -Ls "https://get.maestro.mobile.dev" | bash`).
- **Un build de RELEASE instalado en el dispositivo**, no un dev-client:
  ```bash
  cd android && ./gradlew :app:assembleRelease -PreactNativeArchitectures=arm64-v8a
  adb install -r app/build/outputs/apk/release/app-release.apk
  ```
  Y tampoco Expo Go: la app usa módulos nativos (biometría, SQLCipher, cámara).

  > **Por qué release y no development build.** Todos los flujos empiezan con
  > `launchApp: clearState`, y eso borra también la configuración del **dev
  > launcher**: un dev-client se queda esperando que alguien le diga a qué
  > servidor de Metro conectarse, y el flujo muere en `DevLauncherActivity` con
  > un «no encuentro el botón de login» que apunta a la app en vez de al build.
  > Un APK de release trae su bundle dentro y arranca solo. Medido en un Pixel 8
  > Pro el 2026-08-09.
  >
  > `-PreactNativeArchitectures=arm64-v8a` no es opcional por prisa: compilar
  > además `armeabi-v7a`, `x86` y `x86_64` multiplica por ~4 el tiempo de
  > compilación nativa para ABIs que ningún teléfono de prueba usa.
- Variables en `.maestro/.env` (NO commitear): `OCCUPANT_EMAIL`, `OCCUPANT_PASSWORD`,
  `TACTICO_EMAIL`, `TACTICO_PASSWORD`, `SITE_CODE`. Las escribe
  `make cloud-mobile-users`; la fuente de verdad es el secreto `takab/dev/mobile/users`.

## Correr
El orden importa: la fase del incidente de staging es una precondición de casi
todos, y cada archivo declara la suya en su cabecera.

```bash
export PATH="$HOME/.maestro/bin:$PATH"
set -a && . .maestro/.env && set +a

.maestro/run.sh 04-panico-quorum.yaml       # no necesita incidente
make cloud-staging-incident PHASE=crisis
.maestro/run.sh 01a-crisis.yaml
make cloud-staging-incident PHASE=conclude
.maestro/run.sh 01b-checkin-sync.yaml
.maestro/run.sh 02-tactico-foto-danos.yaml  # pide el TOTP del táctico
make cloud-staging-incident PHASE=roster    # ocupantes SIN reportar
.maestro/run-offline.sh                     # las 3 partes del offline, con el radio
```

**Siempre por `run.sh`, nunca `maestro test` a secas**: Maestro NO hereda el entorno del shell
—solo `-e`— y los flujos declaraban `env: FOO: ${FOO}`, una autorreferencia que produce la
cadena literal `"undefined"` y la teclea en el formulario. Cognito respondía «credenciales
incorrectas» con las credenciales buenas.

**El offline va por `run-offline.sh`**: el modo avión de Android **no apaga el WiFi**, y Maestro
no puede tocar ese radio. El script lo apaga entre las partes 1 y 2, lo restaura con `trap`, y
por eso son tres archivos: el login necesita red y lo que se mide necesita no tenerla.

`maestro test .maestro/` (la carpeta entera) **no** sirve para una corrida de
aceptación: no hay forma de intercalar los cambios de fase entre flujos.

## Cobertura (criterios de aceptación T-2.14)
| Flujo | Archivo | Acceptance | Precondición |
|---|---|---|---|
| Toma de crisis | `01a-crisis.yaml` | takeover con verbo de zona, sin magnitud ni cuenta regresiva | incidente `crisis` |
| Check-in de vida | `01b-checkin-sync.yaml` | el check-in declara si está en el dispositivo o en el servidor | incidente `conclude` |
| Táctico: foto → daños → Triage | `02-tactico-foto-danos.yaml` | evidencia forense + reporte llegan a Triage con hash | incidente + **TOTP del táctico** |
| Dictamen → liberación | `03-dictamen-liberacion.yaml` | consola-firma → push → PDF → reingreso liberado | **firma de un inspector en la consola** |
| Pánico quórum-de-2 | `04-panico-quorum.yaml` | 1er voto queda en `1 DE 2`; NO es alerta sísmica | ninguna |
| Offline-first (3 partes) | `05a/05b/05c` + `run-offline.sh` | declara MODO OFFLINE, deja el trabajo PENDIENTE, la cola drena sola | incidente `conclude` + `roster` + **TOTP** |

**Lo que estos flujos NO acreditan solos**, y hace falta decirlo porque un gate
que se da por cerrado sin correrse es peor que uno declarado abierto:
- **El 2º voto del quórum de pánico** exige dos occupants del mismo sitio en dos
  dispositivos. `04` cubre el primero y comprueba que uno solo **no** dispara.
- **El TOTP del táctico** no lo genera Maestro: lo teclea una persona en el
  primer login del pool principal (MFA obligatorio).
- **La firma del dictamen de `03`** ocurre en la consola web, con otro usuario.

> Estos flujos son la **evidencia ejecutable de `GATE-HW`** (ver
> `takab-docs/runbooks/RUNBOOK-cierre-fase2.md`): se corren en dispositivo real
> antes de cerrar la fase, incluyendo la verificación de que los modos de prueba
> del gabinete (T-1.67/T-1.69) NO disparan pantallas de crisis en el móvil.
