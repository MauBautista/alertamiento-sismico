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
  `TACTICO_EMAIL`, `TACTICO_PASSWORD`, `SITE_CODE` y `HOSTED_UI_LOGOUT_URL`. Las escribe
  `make cloud-mobile-users`; la fuente de verdad es el secreto `takab/dev/mobile/users`
  (o `…/users-e2e` para el perfil del arnés).

  ⚠️ **`HOSTED_UI_LOGOUT_URL` va ENTRECOMILLADA y con `https://`.** Dos trampas medidas el
  2026-09-18: el valor lleva `?` y `&`, y sin comillas el `source` del `.env` toma el `&` como
  «ejecuta en segundo plano» y parte la línea —la variable queda vacía y `run.sh` avisa de que no
  existe aunque esté escrita—; y `hosted_ui_domain` **no trae esquema**, y un `am start -d` sin
  `https://` no casa el intent `VIEW`, así que el navegador no se abre y nadie se entera.

### ⚠️ Los E2E van contra el SITIO DEL ARNÉS, nunca contra Puebla

`site-dev` es **el sitio del gabinete REAL `gw-dev-0001`**. El arnés que prepara la fase
(`seed_staging_incident.sh`) **cierra todos los incidentes abiertos del sitio**, así que correrlo
contra Puebla cerraba incidentes de operación — es el defecto que destapó `T-7.51`: tres incidentes
cerrados sin hora, con su dictamen pericial diciendo «EN CURSO». Lo decidió `D-34`.

Desde `T-7.52` hay **dos ficheros de entorno**, y se elige con `TAKAB_MAESTRO_ENV`:

| fichero | sitio | identidades | para qué |
|---|---|---|---|
| `.env` (defecto) | el que tuviera | las de siempre | lo ya acreditado, sin tocar |
| `.env.e2e` | `site-e2e-900` | `…+occupant-e2e@…` y `…+brigadista-e2e@…` | los E2E |

```bash
make cloud-e2e-site                        # siembra el sitio del arnés (una vez)
PERFIL_SUFIJO=-e2e SITE_ID=d1000000-0000-0000-0000-000000000900   ZONE_ID=d2000000-0000-0000-0000-000000000900 SITE_CODE=E2E-OCUPANTE   make cloud-mobile-users                  # las DOS identidades del arnés
TAKAB_MAESTRO_ENV=.env.e2e .maestro/run.sh 01a-crisis.yaml
```

**Son DOS identidades y no una** (`D-35`): dos de los cuatro flujos son del brigadista, y el
brigadista resuelve su sitio por `custom:site_scope`, del que la app toma el **`[0]`** de una lista
que `/me` devuelve **ordenada** — así que Puebla (`…-000000`) le gana siempre al arnés
(`…-000900`). Darle los dos sitios a la identidad de hoy la dejaría mirando justo el sitio del que
se la quiere sacar.

`run.sh` aborta si `SITE_CODE=site-dev`, para no gastar una corrida descubriéndolo. La guarda dura
—sin bandera que la salte— está en `infra/scripts/sql/staging-incident/guarda.sql`: el arnés no
escribe sobre un sitio que tenga un gabinete, esté latiendo o no.

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
.maestro/run-offline.sh                     # las 3 partes del offline, con el radio (TOTP)

make cloud-staging-incident PHASE=reset     # ← el 03 va APARTE y empieza por reset
make cloud-staging-incident PHASE=crisis
make cloud-staging-incident PHASE=reentry
.maestro/run.sh 03-dictamen-liberacion.yaml # sin TOTP: corre solo
```

**El `03` empieza por `reset` y eso no es ceremonia:** sin él, el dictamen de la vuelta anterior
sigue dentro de la ventana de `reentry_declare_s` (8 h) y la app enseñaría el banner sin que esta
corrida haya probado nada — un verde falso. Lo cerró `T-7.62`, que hizo que `reset` retrodate
también los incidentes que `D-33` ya había cerrado.

**Siempre por `run.sh`, nunca `maestro test` a secas**: Maestro NO hereda el entorno del shell
—solo `-e`— y los flujos declaraban `env: FOO: ${FOO}`, una autorreferencia que produce la
cadena literal `"undefined"` y la teclea en el formulario. Cognito respondía «credenciales
incorrectas» con las credenciales buenas.

**El offline va por `run-offline.sh`**: el modo avión de Android **no apaga el WiFi**, y Maestro
no puede tocar ese radio. El script lo apaga entre las partes 1 y 2, lo restaura con `trap`, y
por eso son tres archivos: el login necesita red y lo que se mide necesita no tenerla.

`maestro test .maestro/` (la carpeta entera) **no** sirve para una corrida de
aceptación: no hay forma de intercalar los cambios de fase entre flujos.

### Acreditar un flujo intermitente (la tanda de diez)

Cuando un flujo falla a veces, la vara es **diez corridas seguidas en verde** — se fijó en
`T-7.57` y la heredan `T-7.58` y las que vengan. Se corre así:

```bash
cd mobile && export PATH="$HOME/.maestro/bin:$PATH" TAKAB_MAESTRO_ENV=.env.e2e
for i in $(seq 10); do
  printf 'corrida %s: ' "$i"
  timeout 420 .maestro/run.sh 02-tactico-foto-danos.yaml >/tmp/tanda$i.log 2>&1 \
    && echo OK || { echo "FALLO — mira /tmp/tanda$i.log"; break; }
done
```

⚠️ **Dos cosas que cuestan una tanda entera, las dos medidas:**

1. **El `timeout` por corrida tiene que sobrar.** El flujo `02` tarda ~263 s; con 260 s el
   `timeout` cortaba a mitad de una aserción y se leía como un fallo del flujo. De ahí los 420 s:
   entran también los 120 s del TOTP.
2. **Un flujo táctico NO se acredita solo.** Desde `T-7.56` cada corrida cierra la sesión de
   Cognito, así que **cada corrida pide un TOTP nuevo** y Maestro no lo genera: el secreto vive en
   el authenticator de la persona, no en Secrets Manager. Diez corridas son ~45 min **con alguien
   delante del teléfono**. Si nadie teclea, el log lo dice con ese nombre
   (`id: totpCodeInput is not visible ... FAILED`) y no acusa a la app — eso lo arregló `T-7.58`.

## Cobertura (criterios de aceptación T-2.14)
| Flujo | Archivo | TOTP | Acceptance | Precondición |
|---|---|---|---|---|
| Toma de crisis | `01a-crisis.yaml` | no | takeover con verbo de zona, sin magnitud ni cuenta regresiva | `PHASE=crisis` |
| Check-in de vida | `01b-checkin-sync.yaml` | no | el check-in declara si está en el dispositivo o en el servidor | `PHASE=conclude` |
| Táctico: foto → daños → Triage | `02-tactico-foto-danos.yaml` | **sí** | evidencia forense + reporte llegan a Triage con hash | `PHASE=crisis` **y luego `conclude`** |
| Dictamen → liberación | `03-dictamen-liberacion.yaml` | no | dictamen firmado → reingreso liberado en la app | `PHASE=reset` → `crisis` → `reentry` |
| Pánico quórum-de-2 | `04-panico-quorum.yaml` | no | 1er voto queda en `1 DE 2`; NO es alerta sísmica | ninguna |
| Offline-first (3 partes) | `05a-offline-preparar.yaml` → `05b` → `05c`, por `run-offline.sh` | **sí** | declara MODO OFFLINE, deja el trabajo PENDIENTE, la cola drena sola | `PHASE=crisis` → `conclude` → `roster` |

### La columna TOTP es la que decide si hace falta una persona

**Los flujos con `sí` entran por el pool PRINCIPAL, cuyo MFA es obligatorio** (RBAC §4.3), y
desde `T-7.56` `run.sh` cierra la sesión de Cognito antes de cada corrida: **cada corrida pide
un código nuevo**, y Maestro no lo genera —el secreto vive en el authenticator de la persona,
no en Secrets Manager—. Los de `no` entran por el pool de OCUPANTES, con MFA opcional: corren
solos, de noche, sin nadie delante.

Planificar una tanda es esto y nada más: **`sí` = ~45 min de alguien tecleando; `no` = déjalo
corriendo**. Estaba escrito en las cabeceras de tres de los ocho flujos y mal en un cuarto, así
que lo deriva un censo —`mobile/tests/flujos-maestro.test.ts`— del subflujo de login que cada
uno invoca de verdad: `login-tactico.yaml` teclea en `totpCodeInput`, `login-occupant.yaml` no.
Una cabecera que diga lo contrario, o que se calle, deja el job `mobile` en rojo.

> ⚠️ **[T-7.63] El `03` NO necesita que nadie firme en la consola web**, y esta tabla decía que
> sí. `reentry.sql` inserta el dictamen **ya firmado** (`signed_by` no nulo, estado
> `inhabit_monitor`): la precondición es una orden de `make`, no una persona. Se llegó a
> planificar una tanda de diez contando con diez firmas manuales. Y el `02` pedía «incidente
> activo» cuando necesita la sacudida **concluida**: con la fase en `crisis` el brigadista ve la
> instrucción a pantalla completa y el flujo muere en `Tap on TRIAGE` por una razón que no tiene
> nada que ver con la cámara. Barridos los ocho el 2026-09-20; los otros seis decían la verdad.

**Lo que estos flujos NO acreditan solos**, y hace falta decirlo porque un gate
que se da por cerrado sin correrse es peor que uno declarado abierto:
- **El 2º voto del quórum de pánico** exige dos occupants del mismo sitio en dos
  dispositivos. `04` cubre el primero y comprueba que uno solo **no** dispara.
- **El TOTP del táctico** no lo genera Maestro: lo teclea una persona en el
  primer login del pool principal (MFA obligatorio) — son el `02` y el trío `05`.
- **El PUSH del `03`.** El flujo acredita que la app pasa a `reentry_approved`, pero sembrando
  por SQL **no se dispara la notificación** —eso lo hace la consola al firmar—, así que lo que
  mide es el siguiente sondeo de `mobile-state`. De ahí la espera de 60 s. Que el push LLEGUE
  al teléfono sigue siendo un hueco declarado, no un verde.

> Estos flujos son la **evidencia ejecutable de `GATE-HW`** (ver
> `takab-docs/runbooks/RUNBOOK-cierre-fase2.md`): se corren en dispositivo real
> antes de cerrar la fase, incluyendo la verificación de que los modos de prueba
> del gabinete (T-1.67/T-1.69) NO disparan pantallas de crisis en el móvil.
