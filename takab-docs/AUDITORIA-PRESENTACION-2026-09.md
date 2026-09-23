# Auditoría integral para la presentación a clientes · 2026-09-22

> **Qué es.** La auditoría de todo el sistema que pidió Mauricio el 2026-09-22, antes de la
> presentación del **jueves 24-sep-2026**. Revisa la UI/UX por página, cada rol y sus
> flujos, los permisos, la sesión por rol, los componentes, las funciones básicas y lo que falta,
> el PDF, los estatus visibles, las animaciones y las mejoras de móvil, edge y nube.
>
> **Cómo se hizo.** Diez agentes Explore **en solo lectura**, uno por dimensión, orientados
> con `graphify` y verificados contra el código (`ruta:línea`). Los dos P0 de sesión se
> re-verificaron a mano. El volcado íntegro está en
> [`auditoria/descubrimiento-2026-09-22.json`](auditoria/descubrimiento-2026-09-22.json).
> El plan que ejecuta estos hallazgos está en [`PLAN-AUDITORIA-PRESENTACION.md`](PLAN-AUDITORIA-PRESENTACION.md) y
> las fichas en el `BLOQUE IX` de [`TASKS.md`](TASKS.md) (`T-8.01…T-8.19`).
>
> **Es una instantánea fechada.** El estado vivo de cada hallazgo es su ficha. Un
> `❔ NO MEDIDO` no es ni un aprobado ni una acusación: dice que el análisis estático no
> alcanzaba y cómo se mide. Las cifras medidas que se citan viven en
> [`MEDICIONES-TAKAB.md`](MEDICIONES-TAKAB.md).

**356 hallazgos** · P0 **9** · P1 **79** · P2 **125** · P3 **143** · 73 son inventario de lo que está bien (`✅ OK`).

## 1 · Resumen por dimensión

### Web · MONITOREO/EVALUACIÓN · 33 hallazgos

Auditoría de solo lectura, sin ejecutar nada, de la consola web: rutas, shell, MONITOREO (/console), escena y EVALUACIÓN (/triage). Me orienté primero con graphify y después verifiqué en el código.

**Rutas:** hay 9 rutas, todas protegidas por `allowed_routes` del servidor, sin matriz en el cliente. Los 7 roles web aterrizan en /console tras el login. brigadista, security_guard y occupant ven la pantalla SIN SUPERFICIE WEB. El shell no tiene selector de tenant.

**Defectos confirmados en el código (P1):**
- El botón DESCARGAR CLIP de CCTV no hace nada: TriagePage nunca pasa `onDownloadClip`.
- CONFIRMAR ACUSE se lanza sin esperar respuesta y descarta cualquier error (403/409/500), pero el botón muestra EJECUTADO igual.
- La consola selecciona por SITIO y no por incidente: si un sitio tiene 2 o más incidentes abiertos, el acuse, el reubicar y el dictamen pueden caer en el incidente equivocado.
- Casi seguro (análisis estático, pendiente de probar en navegador): el Modal le roba el foco a los campos cada segundo en Reubicar, Comparativa y Simulacro, porque ConsoleWall se redibuja cada segundo y el Modal vuelve a llamar a `focus()`.

**Sospechas P1:**
- takab_superadmin puede lanzar un simulacro sobre los gabinetes de TODOS los tenants dejando la selección vacía, mientras el texto dice «DEL TENANT».
- La firma del dictamen solo aparece si ya existe un dictamen previo, aunque la API permite firmar el primero.

**P2:**
- La consulta de comandos de quórum da 403 cada 15 s a soc_operator, gov_operator y takab_support, así que el SOC nunca ve el aviso QUÓRUM RED.
- El panel CCTV muestra error permanente a gov_operator y takab_support.
- El verificador de huella del dictamen PDF da 404 a 5 roles.
- Se puede BORRAR una plantilla sin confirmar.
- EJECUTAR AHORA / INICIAR AHORA de un simulacro (vocea en edificios reales) va con un solo clic.
- Encender el modo demostración no existe en la UI; el hook existe pero nadie lo llama.
- ScopeBadge dice «TODO EL TENANT» a roles internos que ven todos los clientes.
- La cola de incidentes no muestra el estado (acusado / en revisión).

**Sesión:** hoy la web dura 8 h y se guarda en sessionStorage, es decir, una pestaña y fuera. La app táctica dura 24 h y la de ocupantes 90 días. La política pedida (1 mes para brigadista/inspector/ocupante, 1 día para el resto) no se puede expresar por rol en Cognito, porque la duración va por app client.

### Web · flota/tenants/edificio · 39 hallazgos

Auditoría en SOLO LECTURA de la consola web (Flota Edge, Multi-Tenant/Usuarios, Dash Edificio, Auditoría, Privacidad, Telemetría) en /home/maubautista/Documentos/Desarrollo/Alertamiento_Sismico. Me orienté primero con graphify y después contrasté cada control con su endpoint (shared/sdk-ts/src/gen/sdk.gen.ts ↔ api/src/takab_api/routers) y con los permisos de api/src/takab_api/auth/matrix.py. Todas las funciones del SDK que se usan existen.

Lo que está bien: los permisos de la interfaz están bien aplicados. FleetAdmin, VisibilityCard, UsersCard, SirenTestPanel y el control VENTANA solo se muestran si el rol tiene la acción. El retiro exige teclear el identificador y además el código del cliente. APLICAR Y SINCRONIZAR usa ConfirmButton. Casi todo dato del servidor pasa por StateFrame (cargando/error/vacío/datos viejos). Auditoría tiene paginación con CARGAR MÁS.

Defectos confirmados en el código (13):
- (P1) gov_operator ve en /fleet una alerta roja permanente, «PUEDE HABER GABINETES CON LA ALARMA MUDA», porque recibe 403 al leer las ventanas de mantenimiento y FleetPage no revisa `forbidden`.
- (P1) Después de SILENCIAR SIRENA, el panel dice «SIRENA SONANDO · ACUSADA POR EL EDGE», porque la fase no distingue activar de desactivar.
- (P1) La tarjeta de Usuarios, vista por el superadmin, lista los usuarios de TODOS los clientes, sin filtrar por el cliente seleccionado.
- (P2) Otros diez defectos: el error al abrir una ventana nunca se ve (el diálogo se cierra antes de la respuesta); los errores de RESTAURAR y del autodiagnóstico se pierden sin aviso; el aviso de código de retiro revisa el cliente de la sesión y no el del objeto; un gabinete «fantasma» no tiene ningún botón para restaurarlo; AÑADIR SENSOR no confirma nada; los rangos del historial desaparecen cuando el rango está vacío; el historial y la cabecera del edificio marcan DATOS RETENIDOS a los 3 y 5 minutos aunque el sistema esté sano; la invalidación de config-state usa una clave que no coincide; y la lista de usuarios ignora la paginación.

Acciones destructivas sin confirmación: DAR DE BAJA usuario (irreversible), cambio de rol al instante, deshabilitar la propia cuenta sin protección del servidor, VOLVER A vN de umbrales y conceder visibilidad a TODOS los clientes.

Sin interfaz web todavía: rotar el código de retiro, desplegar firmware (rollouts), publicar el aviso de privacidad, solicitudes ARCO, listar/editar/borrar sensores y restaurar estaciones.

Las pruebas e2e (Playwright) solo entran con 3 roles (takab_superadmin, soc_operator, tenant_admin). No cubren takab_support, gov_operator, inspector, building_admin ni los roles solo-móvil.

Para recorrer la consola rol por rol: `make soc-local`, luego el panel LOGIN DEV en http://localhost:5173. `make dev` no activa /dev/token, y el rol occupant da 503 en local.

NO_MEDIDO (no se puede comprobar sin navegador): cómo se ve el diálogo de ventana (usa controles sin clases CSS), el pegado de «lat, lon» en campos numéricos, y el comportamiento real de la sirena en el edge después de la prueba.

### Móvil · 24 hallazgos

Auditoría de SOLO LECTURA de la app móvil (mobile/src) del repositorio /home/maubautista/Documentos/Desarrollo/Alertamiento_Sismico. Las rutas de la evidencia son relativas a esa raíz.

SESIÓN (crítico, CONFIRMADO con evidencia): la app guarda el refreshToken (useAuth.ts:48,76-81) pero ningún código lo usa. No aparece refreshAsync, grant_type ni TokenResponse en mobile/src. Tampoco hay tareas en segundo plano. El socket en vivo cierra la sesión con el código 4401, y el API cierra el WebSocket justo cuando caduca el token (ws.py:88-98). El REST cierra la sesión en el primer 401 (sdk.ts:46-51). El ID token dura 60 min y el API lo valida con leeway 0. Como mobile-state se consulta cada 30 s, la sesión muere en unos 60-61 min con la app abierta, o al volver al primer plano / arranque en frío pasado ese tiempo. Luego crisis.tsx:60 manda al login, en contra de la especificación (ESPECIFICACION-APP-MOVIL.md:417). La pantalla de login además promete lo contrario (login.tsx:64).

Terraform: el cliente de ocupantes da 90 días de refresh y el táctico 24 h. Ese cliente táctico lo comparten brigadista/inspector (piden 1 mes) y security_guard/building_admin (piden 1 día), así que hay que decidir la política por rol. Abajo va el diseño completo de la renovación (REST, socket, camino offline, arranque) y la parte de Terraform.

La matriz RBAC §3 cuadra celda por celda con las pestañas derivadas de allowed_actions. Aun así encontré callejones sin salida y defectos reales:
- La pestaña Cuenta sin red no deja cerrar sesión.
- «VER DICTAMEN» lleva a «Sin incidente activo» después del cierre automático D-33.
- La revisión de la cámara forense muestra el visor en vivo y no la foto tomada.
- El check-in delegado no se encola sin red, y el flujo Maestro 05b lo da por bueno de forma vacía.
- Cerrar sesión no revoca el token, no borra la cookie de la Hosted UI ni da de baja el token push.
- La cola offline y los consentimientos no tienen dueño, así que en un teléfono compartido pasan al siguiente usuario.
- Descargar el PDF del dictamen y guardar el perfil fallan en silencio.

Movimiento: hay 6 animaciones con Animated clásico y todas respetan «reducir movimiento». Reanimated 4.5 está instalado y no se usa. No hay feedback háptico, ningún botón da respuesta visual al pulsarlo y no hay pull-to-refresh.

### Sesiones por rol · 25 hallazgos

Duración de sesión por rol: sin cambios de por medio, el requisito (30 días para brigadista, inspector y occupant; 1 día para los demás) no se cumple. Además hay dos defectos que hoy acortan la sesión real a unos 60 minutos, sin importar lo que diga Terraform. Ninguno se comprobó en ejecución.
(1) Web: al llegar el `exp` del token del handshake, el WS cierra con 4401 (ws.py:88-99). `LiveSocket` no reintenta ante un 4401 (live.ts:219-222) y la consola responde con `logout()`, que redirige al /logout de Cognito (LiveSocketProvider.tsx:28-29). Como el shell monta el socket siempre (AppShell.tsx:10), la consola se cierra a los ~60 min aunque el silent renew ya haya traído un token nuevo.
(2) Móvil: guarda el `refreshToken` y nunca lo usa (useAuth.ts:48, 76-81). Al arrancar manda el ID token guardado, que dura 60 min (useAuth.ts:96-98). La API responde 401 y se ejecuta `signOut` (sdk.ts:47-48). El WS también lleva a `signOut` (socket.ts:24), y la pantalla de crisis redirige al login si no hay sesión (crisis.tsx:60-61). Esto choca con la aceptación §0.1 de la especificación móvil.
Diseño propuesto:
- La API impone una edad máxima de sesión por rol usando el claim `auth_time`, en los dos únicos puntos donde se decodifica el token: `deps.get_claims` (deps.py:86-95) y `ws._authenticate` (ws.py:125-128). La tabla por rol vive en `matrix.py`. Responde 401 con detail `sesion_expirada` y la cabecera `WWW-Authenticate` con `error_description="sesion_expirada"`; en el WS, cierre con un código propio (4440).
- Como la API corre antes que `require_mfa`, una sesión caducada da 401 antes de llegar al 403 por MFA.
- Terraform: `mobile_tactical` pasa a 30 d, `mobile_occupants` a 30 d y `web` a 24 h (o 30 d si el inspector debe tener 30 d también en web).
- Web: refresco real (usar el refresh token al arrancar en vez de caer al login), guardar la sesión en `localStorage` si se acepta el riesgo, y mostrar un motivo específico en `LoginPage`.
- Móvil: `refreshAsync` en una sola vía compartida.
- Documentación: D-38 y actualización de cognito-pool-v1.md, la especificación móvil y RBAC.
Lo que falta medir: si Cognito conserva `auth_time` al refrescar. La documentación de AWS no lo dice (NO_MEDIDO) y todo el tope por rol depende de ello. Lo que sí confirma AWS: la vida del refresh token se cuenta desde el inicio de sesión (con rotación, el token nuevo hereda lo que le quedaba al original), el rango permitido es de 60 min a 10 años y la cookie del login gestionado dura 1 h.
Riesgos principales:
- Regla 8: brigadista e inspector mueven actuadores y solo mostrarían MFA una vez al mes.
- Consola pública (D-22) sin CSP en el repo, con `localStorage` guardando el refresh token.
- Un corte de 24 h al SOC en plena emergencia, justo lo que ya advierte mfa.py §4.

### RBAC y flujos · 40 hallazgos

Auditoría estática (solo lectura) de los 10 roles contrastando tres fuentes: auth/matrix.py con las guardas de los routers, RBAC-TAKAB.md §2/§3/§4/§7, y la UI (web: navItems/RouteGuard/landing y botones gateados; móvil: profileGate/pestanasTacticas).

Lo que está bien: la matriz ejecutable coincide celda a celda con §3 (móvil) y con las rutas de §2. La navegación web sale del servidor (allowed_routes ∩ NAV_PRESENTATION) y las pestañas tácticas se derivan de allowed_actions. Casi todos los botones sensibles están gateados por acción.

Hallazgos principales:
(1) P0 · La app móvil guarda el refresh token pero nunca lo usa. Cualquier 401 o cierre de WS 4401 cierra la sesión, así que todos los roles móviles vuelven a meter contraseña (y el código MFA los tácticos) cada ~60 min. Esto choca con la spec §8 y con tu petición de 1 mes. En la web el refresh es de 8 h y la sesión se guarda en sessionStorage, por lo que no llega a 1 día.
(2) P1 · En Evaluación, takab_support y gov_operator ven un error «GET /incidents/{id}/cctv falló (403)»: el panel CCTV consulta sin comprobar cctv_read.
(3) P1 · El gov_operator sembrado vive en tenant-dev (privado). Ve los incidentes por ser su propio tenant y le sale el botón ACUSAR, pero gov_ack_incident exige gov_shared y responde 404. Tampoco se puede demostrar su aislamiento.
(4) P1 · Faltan usuarios de prueba: takab_support no está en el seed web, e inspector/building_admin no tienen identidad móvil (el seed web fija surface=web y el móvil los rechaza). security_guard solo existe si se siembra con argumento.
(5) P1 · building_admin tiene enrollment_manage y self_test, pero ninguna superficie donde usarlos: viven en /fleet, que no tiene, y el móvil no los ofrece.
(6) P1 · El SOC no ve en la web los check-ins de vida ni el pase de lista, aunque los datos existen.
(7) P1 · Un táctico dado de alta desde la consola queda con site_scope "*" por defecto y en la app aparece «sin sitio vigilado».
(8) P2/P3 · Hay varias acciones que solo se pueden hacer por API: encender el modo demo, firmware, ventana de plataforma, rotar el código de retiro, aviso de privacidad, ARCO y planos de evacuación. Además hay divergencias con el documento (classify_incident y demo_mode no aparecen en el RBAC; §7 pone a building_admin en /fleet y dice que ARCO vive en /tenants) y la escritura no aplica el site_scope.

Todo lo que depende de la nube, del Pixel o de Cognito real queda como NO_MEDIDO.

### PDF · 32 hallazgos

Auditoría de solo lectura de los PDF del sistema. Hay 4 generadores, todos en api/ con fpdf2 (web/, mobile/ y edge/ no generan PDF): (1) dictamen técnico o «informe del evento» (dictamen/pdf.py, 18 secciones); (2) resumen ejecutivo (la misma ruta con variant=executive); (3) reporte de simulacro (drill_report.py); (4) hoja membretada en blanco (documentos/hoja.py, está comiteada en shared/brand/membrete). No existe ningún PDF ni CSV de auditoría o compliance: el compliance va como §17 dentro del dictamen.

El chasis compartido (MembretePDF) está bien protegido. Usa papel Carta, DejaVu embebida (lo medí con fc-query: cubre ↳, →, ⇒, ⚠ y ↑), y el pie lleva folio, paginación, SHA-256 del contenido, el sello del evento y el emisor de D-36. Hay censo de avisos, espía del render y guarda geométrica de las figuras.

Defectos confirmados en el código que se verían en la presentación:
- En la §14, el pie de foto se pisa cuando un reporte trae una sola foto. Es el caso del 100 % de los incidentes reales con foto.
- Las fotos en vertical miden 117 mm y la reserva es de 98 mm, así que pueden pisar el pie de página.
- El botón «VERIFICAR HASH» del dictamen sale en Triage para todos los roles, pero solo verifica para inspector y building_admin. Con superadmin se pone en rojo: «NO SE PUDO VERIFICAR».
- La clasificación humana (reproducción, prueba, falso positivo) no se imprime. «REPRODUCCIÓN» solo sale en la §7 del técnico y solo si el evento es un replay; el ejecutivo nunca la lleva.
- El ejecutivo imprime los títulos como «. QUÉ PASÓ».
- Salen valores crudos en inglés: severidad, categorías de daño, papeles de CCTV.
- El firmante sale como un UUID.

Riesgos:
- El certificado del móvil descarga el último report_pdf aunque se generara antes de la firma, y lo deja en caché para siempre.
- El reporte de simulacro se sobrescribe en una clave fija, así que las filas de evidencia anteriores dejan de casar con su sha256.
- En el simulacro, las líneas con nombres de sitio largos se salen del margen.

Faltan en la interfaz: el resumen ejecutivo (no hay forma de pedirlo), volver a descargar un dictamen ya emitido (gov_operator no tiene ningún botón), el pase de lista dentro del informe y la hora local.

La meta F6 busca «Narrativa: openrouter» en el PDF, pero esa cadena no se imprime. No rasterizé nada (modo solo lectura): la revisión visual queda NO_MEDIDO, y los comandos para hacerla están en how_to_verify.

### Estatus visibles · 39 hallazgos

Revisé unos 30 estatus en el esquema de base de datos, la ingesta, los routers, el WebSocket, la consola web, la app móvil y el panel LAN del gabinete. Me orienté primero con graphify y luego con grep y lecturas puntuales. No ejecuté nada: todo lo que sigue sale de leer el código.

La cobertura es alta. La mayoría de las superficies usan StateFrame con su edad (staleSince), y el panel LAN del gabinete es la vista más completa del sistema.

Encontré 4 defectos y 2 faltas graves (P1):

1. **Evidencia y disco siempre vacíos en la API.** `GET /fleet/gateways` descarta `disk_used_pct`, `evidence_pending` y `evidence_oldest_age_s`: la consulta los trae y el schema los declara, pero el router no los pasa al construir la respuesta. Por eso la tarjeta de flota dice «s/d · el gabinete no pudo mirar» de todos los gabinetes, culpando al gabinete de algo que tira la API, y el disco no se ve en ningún sitio.
2. **La desconexión (LWT «offline») hace parecer vivo al gabinete.** El mensaje escribe una fila nueva en `device_health` sin métricas. Todas las lecturas del «último latido» (flota, mapa, app, sirena, fantasmas) la toman sin filtrar por tipo. Resultado: durante unos 5 min tras caerse, el gabinete aparece OPERATIVO, con métricas S/D y relés ARMADOS.
3. **Bitácora del gabinete sin lector (falta).** La tabla `actuation_records` se ingiere, pero no tiene endpoint, UI ni aparece en el PDF. Ahí quedan las actuaciones sin enlace, las acciones del panel LAN, el voceo y el armado del MODO PRUEBA WR-1.
4. **MODO PRUEBA WR-1 invisible para la nube (falta).** El estado «la nube no recibe alertas» sólo se ve en el panel LAN.

Hay más huecos donde existe el dato o el endpoint pero ninguna pantalla lo muestra:
- El nivel de alerta vigente por sitio (el WebSocket lo emite y la consola lo descarta).
- Temperatura de CPU, batería, minutos de UPS y certificado en la consola web (la app móvil sí los muestra).
- Despliegues canary y órdenes de actualización o rollback.
- Alarmas de CloudWatch y su cadena de acuse.
- El costo de IA (`ai_spend`) y si el reporte usó la IA o el texto de respaldo.
- La versión de firmware en el panel LAN.
- Contadores de SeedLink, LoRa, solicitudes ARCO e inventario de cámaras.

Dos defectos más de edad y semántica: en el panel de detalle de la consola, el SOH aparece sin su edad y se oculta cuando faltan features; y en simulacros un comando vencido (`expired`) se cuenta como «RECHAZADO».

Para la demo con clientes, lo primero son los P1: los dos primeros se ven en pantalla. Quedan sin medir: el comportamiento real del LWT, si el gabinete de desarrollo publica disco/evidencia, y si existe hardware LoRa o BACnet.

### Animaciones · 39 hallazgos

Auditoría estática de solo lectura de la capa de movimiento en las tres superficies. Me orienté primero con graphify (useReducedMotion, LatidoPunto, MapPanel/wavefront, LocalDashboard).

El sistema de movimiento está bien pensado. Los tokens `--tk-dur-*` y `--tk-ease*` se definen en shared/design-tokens. En la consola, `prefers-reduced-motion` funciona como interruptor derivado: los tokens de transición bajan a 0 y los selectores con keyframes se apagan dejando fijo su estado de reposo. Lo vigilan motionInvariants.test.ts y e2e/motion.spec.ts. Los latidos están condicionados a que el dato sea fresco: `liveFresh` en el detalle, `LinkPill` con 120 s de margen, `conn.kind==='live'` en el panel del gabinete y `late` en el móvil. La alerta respira según su estado, como piden D-30 y D-33.

Encontré 4 defectos y 4 sospechas:
- **(P1) Faro del mapa.** El anillo que pulsa sobre los edificios que dispararon sigue animándose con movimiento reducido. `reducedMotionRef` se declara y nunca se lee, y la leyenda del mapa dice «ANILLOS ESTÁTICOS».
- **(P1) Parpadeo del banner rojo del gabinete.** `tk-blink` cambia la opacidad de todo el contenedor, así que el texto «ALERTA SÍSMICA · PROTÉJASE» baja a ~1.6:1 de contraste (cálculo, no medición) durante la mitad del ciclo. D-30 heredó este parpadeo y el test sólo comprueba en qué selector está, no su efecto.
- **(P2) Botón de confirmación.** `ConfirmButton` pinta «EJECUTADO» en verde antes de que responda el servidor, incluso en PROBAR SIRENA y FIRMAR DICTAMEN.
- **(P3)** El resorte de regreso del deslizador de `ControlSheet` ignora el movimiento reducido. El `peakHold` del panel del gabinete decae por fotograma y por eso depende de la frecuencia del monitor.
- **Sospechas.** En las tres superficies la alerta sigue respirando o parpadeando con dato retenido. El faro del mapa sigue pulsando con el incidente en revisión. Con movimiento reducido, los anillos de arribo quietos van hasta 30 s por detrás. Las marcas SASMEX/TIER se deslizan sobre una traza congelada.

Lo que más falta para la demo:
- Ninguno de los 57 `Pressable` de la app móvil da respuesta visual al tocarlo.
- No hay háptica (expo-haptics no está instalado) ni gesto de deslizar para refrescar.
- Reanimated y Gesture Handler están instalados pero no se usan.
- En la web los modales, el menú del operador y los desplegables aparecen de golpe, y no hay avisos del resultado de una acción.
- En la web el bucle de animación del muro repinta a 20 fps sin nada que animar. En el panel del gabinete el lienzo repinta a 60 fps en el Pi 4 aunque los datos llegan a 1 Hz (coste no medido).

También dejo propuestas pasivas honestas: barra indeterminada en carga o subida, tinte al cambiar un KPI o una fila del pase de lista, y cabeza de escritura en la traza sólo con dato vivo. Y rechazos explícitos: no animar el texto de la crisis, no contar cifras hacia arriba, no animar datos retenidos ni poner shimmer en «DATO RETENIDO», no poner anillos en todas las estaciones, no hacer T-MINUS, no mover la cámara del mapa sola cuando llega una alerta.

### Funciones básicas · 46 hallazgos

Catálogo de funciones básicas de TAKAB Ailert revisado contra el código y los documentos. Todo es estático: no levanté nada, no corrí nada y no llamé a la nube. TASKS.md cuadra con su cabecera: 442 fichas, de las que 392 están hechas [x], 11 son parciales [~] y 39 siguen abiertas [ ].
El núcleo está implementado y probado: reflejo SASMEX en el gabinete, consola en vivo, ciclo de vida del incidente (D-33), dictamen firmado con PDF verificable, app de ocupante y táctica, simulacros con reporte PDF/CSV, flota, RBAC con RLS, auditoría inmutable, catálogo USGS, ShakeMap e IA de prosa encendida.
Lo más grave que encontré no está fichado:
(1) la app móvil guarda el refresh token pero nunca lo usa. Al vencer el id_token (60 min), cualquier 401 cierra la sesión y vuelve a pedir contraseña y MFA. Esto contradice la especificación de la app (sesión de ocupante de larga vida) y lo que el usuario pide (30 días).
(2) Cognito fija la duración de la sesión por app client, no por rol. Hoy hay tres: consola web 8 h (y por pestaña), táctico 24 h y ocupantes 90 días. Brigadista, inspector, security_guard y building_admin comparten el táctico, así que 30 días para unos y 1 día para otros exige separar clientes.
(3) Nada permite crear cuentas de ocupante: su pool no admite autorregistro y /users lo excluye. Tampoco se pueden dar de alta zonas/pisos (de ellas depende la instrucción EVACÚE/REPLIÉGUESE), revocar ocupantes ni subir planos.
(4) La gestión de usuarios en la nube corre SIMULADA (T-2.87) y la tarjeta lo dice en pantalla.
(5) Cuando la red corrobora, la consola y el teléfono se contradicen, y el apartado 14 del PDF sale mal maquetado en todos los incidentes con foto. Los dos solo están anotados en PLAN-REVISION, no en TASKS.
Lo que falta hacia un cliente real está casi todo bloqueado en persona, dinero o hardware (G-02/G-04, SMS/WhatsApp, iOS/APNs, RTO, marco legal). Del lado de software se puede hacer ya: reporte periódico, % de disponibilidad, prueba de canal, OTA desde la consola, QR del edificio, alta de zonas y ocupantes, renovación de sesión, driver BACnet real y el shadow-mode de la IA.

### Edge/nube/presentación · 39 hallazgos

Auditoría de solo lectura: edge, nube y preparación de la presentación (rama fix/instrumentos-y-documentos-de-la-presentacion, HEAD b804039, 1 commit por delante de main, ya subida a origin pero sin mergear).

Estado desplegado según el censo del 22-09 a las 17:18Z: la nube corre f63b38b. Entre f63b38b y HEAD solo cambian scripts de operador y documentación, y nada de eso entra en las imágenes, así que no hace falta redesplegar. El Pi corre la release 10a8b3b y desde entonces no hay cambios en edge/. Lo que no se puede saber desde el repo es qué código corre takab-gpio, el proceso dueño de los pines.

Hallazgos clave:
(1) EDGE: deploy.sh compara el código del dueño de los pines contra la release anterior del symlink, no contra la que el dueño cargó al arrancar. Un segundo despliegue sin ventana de mantenimiento pasa a verde aunque el dueño siga con código de dos versiones atrás, y la poda puede borrar su release. Además, la versión del dueño no se ve ni en el latido ni en el panel.
(2) EDGE: cloud.publish se ejecuta en el hilo de SeedLink con fsync y espera el PUBACK de forma síncrona (hasta 10 s). Es una sospecha: puede frenar la detección instrumental. El camino SASMEX→sirena no se ve afectado.
(3) NUBE: cada despliegue hace `compose down`+`up` sin descargar antes las imágenes, así que todo el stack cae mientras se descargan. No hay alarma sobre la edad de la cola principal de SQS ni healthchecks en los contenedores. El PDF se genera bloqueando el event loop de un uvicorn de un solo worker. No hay métrica de memoria.
(4) PRESENTACIÓN: guion.sh y el RUNBOOK siguen mandando `POST /api/reset` sin PIN, lo que da 401 en el último paso. Los dos incidentes del ensayo 1 siguen sin clasificar. Falta el ensayo 2 (el acto 4 duró 47 min). No hay guía sobre la caducidad de sesión: web 8 h y en sessionStorage, app táctica 24 h. El simulacro depende de command_enabled, que no se puede verificar desde el repo.

Lo que ya está bien: backoff/resume de SeedLink, durabilidad T-7.59/T-7.61, despliegue A/B con canary, 20 alarmas con vigilante (T-7.41), margen de disco (T-7.46), Plan B y la lista viva de «lo que NO debe decirse».

## 2 · Funciones básicas que el sistema debería tener a estas alturas

Estado por función, con la evidencia del código y su ficha. ✅ implementada · 🟠 parcial ·
⬜ falta · 🔴 implementada con defecto.

| ID | Dominio | Función | Estado | Evidencia | Ficha |
|---|---|---|---|---|---|
| A-009 | Móvil / sesión | La sesión móvil NO se renueva: el refresh token se guarda y nunca se usa | 🔴 DEFECTO | mobile/src/auth/useAuth.ts:48,76-81,88-117; mobile/src/auth/secureTokens.ts:25-32; mobile… | T-8.04 |
| A-063 | Alertamiento | Si la red corrobora (cuórum), la consola y el teléfono se contradicen | 🔴 DEFECTO | web/src/features/console/AlertBanner.tsx:73; mobile/src/features/alert/source.ts:79-80; t… | T-8.10 |
| A-064 | Alertamiento | La sirena NO suena con el Pi apagado (ruta de hardware paralela, G-02) | ⬜ FALTA | takab-docs/TASKS.md:10416-10432 (T-2.92); takab-docs/INFORME-V1-COMERCIAL.md:61 (H-05); e… | T-8.19 |
| A-065 | Reportes / PDF | El apartado 14 del PDF («DAÑOS REPORTADOS EN CAMPO») se rompe en todos los incidentes con foto, y no tiene ficha | 🟠 SOSPECHA | api/src/takab_api/dictamen/pdf.py:1540; takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:… | T-8.12 |
| A-066 | Reportes / PDF | Dictamen «completo» no demostrable con los datos de la nube de hoy | 🟠 SOSPECHA | takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:79-84; takab-docs/TASKS.md:15371 (T-7.28… | T-8.13 |
| A-067 | Multi-tenant / usuarios / RBAC | La duración de sesión por rol no se puede expresar con los app clients actuales | 🟠 SOSPECHA | infra/terraform/modules/identity/main.tf:160-168,629-635,665-671; web/src/auth/userManage… | T-8.05 |
| A-068 | Móvil | No hay app iOS ni publicación en tiendas | ⬜ FALTA | mobile/app.json (ios.bundleIdentifier=com.takab.ailert); takab-docs/TASKS.md:10476-10500 … | T-8.19 |
| A-069 | Onboarding de clientes / sitios | No existe camino para crear cuentas de ocupante | ⬜ FALTA | infra/terraform/modules/identity/main.tf:556-559; api/src/takab_api/schemas/users.py:26-2… | T-8.19 |
| A-070 | Onboarding de clientes / sitios | Zonas/pisos y su política EVACÚE/REPLIÉGUESE no se pueden dar de alta | ⬜ FALTA | api/src/takab_api/routers/sites.py:100-103; api/src/takab_api/schemas/sites.py:44; db/see… | T-8.19 |
| A-071 | Notificaciones | Cascada de notificación: solo webhook, correo verificado y push Android entregan de verdad | 🟠 SOSPECHA | api/src/takab_api/notify/providers.py:40-72; takab-docs/TASKS.md:7033,7218,7348; takab-do… | T-8.19 |
| A-072 | Multi-tenant / usuarios / RBAC | La gestión de usuarios de la consola corre SIMULADA en la nube (T-2.87) | ⬜ FALTA | deploy/cloud/deploy.sh:125-175 (sin COGNITO_USER_POOL_ID); infra/terraform/modules/databa… | T-8.19 |
| A-073 | Operación | Backups y DR: construidos, pero el RTO de producción no está medido y el WAL no se verifica en S3 | 🟠 SOSPECHA | api/src/takab_api/ops/restore_check.py; api/src/takab_api/ops/restore_drill.py; takab-doc… | T-8.16 |
| A-074 | Presentación a clientes | Lo que un cliente esperaría y hoy no se puede demostrar | ⬜ FALTA | takab-docs/INFORME-V1-COMERCIAL.md:120-138; takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE… | T-8.19 |
| A-075 | Backlog abierto (TASKS.md) · bloqueado en persona/dinero/hardware | Fichas que dependen de Mauricio (PENDIENTES: 30 puntos) | ⬜ FALTA | takab-docs/TASKS.md:1008,1071,5322,5940,6851,7033-7348,10347-10500,10682,11190,11337-1135… | T-8.19 |
| A-178 | Alertamiento | Feed externo CIRES/SSN y catálogo SSN | 🟠 SOSPECHA | api/src/takab_api/routers/catalog.py:30; api/src/takab_api/catalogo/fdsn.py; takab-docs/T… | T-8.19 |
| A-179 | Actuadores | Relés sirena/estrobo reales; gas, ascensores y puertas sin cablear; BACnet sin driver real | ⬜ FALTA | edge/takab_edge/actuators/__init__.py:12-13,183-192; edge/pyproject.toml:24-26; takab-doc… | T-8.19 |
| A-180 | Actuadores | Voceo/audio: no hay grabaciones y audio está deshabilitado | ⬜ FALTA | edge/takab_edge/config/settings.py:521; takab-docs/TASKS.md:10454-10461 (T-2.95); takab-d… | T-8.19 |
| A-181 | Reportes / PDF | No hay reporte periódico (mensual) por cliente o sitio | ⬜ FALTA | api/src/takab_api/routers/classification.py:238; api/src/takab_api/routers/fleet.py:148; … | T-8.19 |
| A-182 | Onboarding de clientes / sitios | Padrón de ocupantes: no se puede listar ni revocar quién está vinculado a un edificio | ⬜ FALTA | api/src/takab_api/queries/mobile.py:111-117,380-388; api/src/takab_api/routers/mobile_me.… | T-8.19 |
| A-183 | Onboarding de clientes / sitios | QR del edificio: la historia de usuario lo pide y solo existe el código tecleado | 🟠 SOSPECHA | takab-docs/USER-STORIES.md:141-145; takab-docs/RBAC-TAKAB.md:443-445,479; web/src/feature… | T-8.19 |
| A-184 | Onboarding de clientes / sitios | Planos y rutas de evacuación: la API de subida existe y ninguna pantalla la usa | ⬜ FALTA | api/src/takab_api/routers/mobile_site.py:381,394-412; mobile/src/app/(occupant)/rutas.tsx | T-8.19 |
| A-185 | Móvil | El directorio de emergencia no tiene números externos (911, Protección Civil) | 🔷 MEJORA | mobile/src/app/(occupant)/directorio.tsx:1-35; api/src/takab_api/queries/mobile.py:380-388 | T-8.19 |
| A-186 | Notificaciones | No hay «prueba de canal» (enviar un aviso de prueba al webhook, correo o teléfono configurado) | ⬜ FALTA | takab-docs/BLUEPRINT-TECNICO-TAKAB.md:440; web/src/features/tenants/NotificationChannels.… | T-8.19 |
| A-187 | Flota / OTA | La actualización remota con canary y rollback existe en la API y no tiene pantalla | 🟠 SOSPECHA | api/src/takab_api/routers/rollouts.py:202,317,383; api/src/takab_api/routers/updates.py:1… | T-8.19 |
| A-188 | Auditoría / compliance | Marco normativo citable y aviso de privacidad revisado | ⬜ FALTA | takab-docs/TASKS.md:10464-10474,12588; takab-docs/INFORME-V1-COMERCIAL.md:134-135 | T-8.19 |
| A-189 | IA asesora | Prosa asistida encendida; shadow-mode, priorización y evaluación sin hacer | 🟠 SOSPECHA | api/src/takab_api/narrative/; takab-docs/TASKS.md:10578-10598,15223,15312; takab-docs/PEN… | T-8.19 |
| A-190 | Operación | No hay disponibilidad (%) ni página de estado visible para el cliente | ⬜ FALTA | api/src/takab_api/routers/fleet.py:148; web/src/features/fleet/useFleetMutations.ts:17 | T-8.19 |
| A-191 | Operación | Un solo entorno Terraform (dev) hace de demo y de «producción» | ⬜ FALTA | infra/terraform/envs/ (solo dev); takab-docs/DECISIONES-MAURICIO.md:1534-1560 (D-31) | T-8.19 |
| A-192 | Landing / comercial | Landing nueva lista, sin publicar; sin formulario de demo ni canal de contacto | 🟠 SOSPECHA | landing/src/pages/index.astro; takab-docs/TASKS.md:10541,10550; takab-docs/PENDIENTES-MAU… | T-8.19 |
| A-193 | Backlog abierto (TASKS.md) · SOFTWARE hacible ya | Fichas abiertas que no esperan a nadie | ⬜ FALTA | takab-docs/TASKS.md:4283,5063,5859,6318,10578-10624,11277,11320-11357 | T-8.19 |
| A-276 | Flota / OTA | Inventario y salud de flota, versión contra releases, mantenimiento, alta de sitio, gabinete y sensor | 🟠 SOSPECHA | web/src/features/fleet/FleetPage.tsx; web/src/features/fleet/useFleetMutations.ts:248; ap… | T-8.19 |
| A-277 | Multi-tenant / usuarios / RBAC | Sin SSO corporativo ni credenciales de máquina para integraciones entrantes | ⬜ FALTA | infra/terraform/modules/identity/main.tf:153,622,658; takab-docs/BLUEPRINT-TECNICO-TAKAB.… | T-8.19 |
| A-278 | Auditoría / compliance | Bitácora inmutable, etiquetas normativas declaradas por el cliente, aviso versionado y ARCO | 🟠 SOSPECHA | api/src/takab_api/routers/audit.py:40; web/src/features/audit/AuditPage.tsx:22-37; api/sr… | T-8.19 |
| A-279 | Sismología | ShakeMap por evento, catálogo USGS e intensidad medida en el inmueble; MMI, Sa y deriva pendientes | 🟠 SOSPECHA | api/src/takab_api/shakemap/; api/src/takab_api/routers/shakemap.py:35; takab-docs/TASKS.m… | T-8.19 |
| A-280 | Operación | Medición de facturación y costos: el job no corre en la nube y no hay pantalla | 🟠 SOSPECHA | api/src/takab_api/billing/__init__.py:1; Makefile:89-90; deploy/cloud/docker-compose.yml:… | T-8.19 |
| A-281 | Operación | T-2.172: el fail-open del modo prueba escribe 24 errores en cada ventana de mantenimiento | 🔴 DEFECTO | takab-docs/TASKS.md:5859; edge/takab_edge/supervisor.py:592-600,677 | T-8.17 |
| A-282 | Backlog abierto (TASKS.md) · deriva documental | Fichas que el propio repositorio da por hechas y siguen abiertas | 🟠 SOSPECHA | takab-docs/TASKS.md:10365-10374,10318-10346,10624-10631; deploy/cloud/deploy.sh:149-151; … | T-8.19 |
| A-343 | Alertamiento | Reflejo SASMEX/WR-1 → sirena en el gabinete, sin nube ni IA | ✅ OK | edge/takab_edge/gpio/__init__.py:922-929; takab-docs/TASKS.md:1071 (T-1.42 [~]); takab-do… | T-8.01 |
| A-344 | Actuadores | Silencio y activación manual firmados (MFA + nonce + ack) y pánico por cuórum de ocupantes | ✅ OK | api/src/takab_api/routers/commands.py:139,307,375; takab-docs/TASKS.md:10434-10444 (T-2.9… | T-8.01 |
| A-345 | Monitoreo en vivo | Consola MONITOREO: mapa, KPIs, cola de incidentes por WS, ficha de estación, sismograma, epicentro, ondas y franjas de escena | ✅ OK | web/src/app/routes.tsx:27-33; web/src/features/console/ConsolePage.tsx; web/src/features/… | T-8.01 |
| A-346 | Incidentes | Ciclo de vida: fases, acuse con tiempo, destinatarios, clasificación y cierre | ✅ OK | api/src/takab_api/incident/lifecycle.py:67,246; api/src/takab_api/routers/classification.… | T-8.01 |
| A-347 | Evaluación estructural / dictamen | Dictamen semaforizado firmado, inmutable y con PDF verificable | ✅ OK | api/src/takab_api/routers/dictamens.py:77; api/src/takab_api/routers/reports.py:51; api/s… | T-8.01 |
| A-348 | Reportes / PDF | Informe del evento, reporte de simulacro PDF/CSV y membrete común | ✅ OK | api/src/takab_api/drill_report.py:43; api/src/takab_api/routers/drills.py:787; takab-docs… | T-8.01 |
| A-349 | Móvil | App de ocupante y app táctica: las 21 pantallas de la especificación | ✅ OK | mobile/src/app/(occupant)/; mobile/src/app/(brigadista)/; mobile/src/app/crisis.tsx; mobi… | T-8.01 |
| A-350 | Simulacros | Simulacros: agenda, disparo humano armado, plantillas, sonido auditado y reporte PDF/CSV | ✅ OK | api/src/takab_api/routers/drills.py:434-787; api/src/takab_api/routers/drill_templates.py… | T-8.01 |
| A-351 | Multi-tenant / usuarios / RBAC | Matriz de 10 roles ejecutable, RLS default-deny, alcance por sitio y visibilidad gov_shared | ✅ OK | api/src/takab_api/auth/matrix.py:55-80; api/src/takab_api/routers/visibility.py:36-85; ap… | T-8.01 |

## 3 · Matriz rol × flujo (10 roles)

### takab_superadmin — ✅ OK

Login: web, cliente takab-web del pool principal (MFA ON, refresh de 8 h); aterriza en /console. Pestañas: MONITOREO, FLOTA, EVALUACIÓN, MULTI-TENANT, AUDITORÍA (+ /building por enlace directo). Celdas: Acuse=OK · Solicitar dictamen=OK · Reubicar epicentro=OK · Clasificar=OK · Firmar dictamen=N/A (decisión: firma solo el inspector) · Prueba/activar/desactivar sirena en web=OK (/building) · Silenciar/activar desde móvil=N/A (sin superficie móvil) · Check-in/pánico/triage/cámara/pase de lista=N/A (acciones de campo) · Ver dictamen/PDF=OK (export + generate_report) · Alta de sitio=OK (/fleet) · Alta de usuario=OK (/tenants) · Códigos de enrolamiento=OK (/fleet) · Umbrales=OK solo en su tenant (tenant ajeno en lectura, declarado) · Auditoría=OK · Iniciar simulacro=OK · Autodiagnóstico=OK (/fleet SiteCard) · Ventana de gabinete=OK · Encender modo demo / firmware / ventana de plataforma / rotar código de retiro / aviso de privacidad / ARCO=FALTA UI (ver item aparte).

*Evidencia:* api/src/takab_api/auth/matrix.py:72,362-405; web/src/shell/navItems.ts:12-30; web/src/app/landing.ts:5-7; web/src/features/tenants/TenantsPage.tsx:180-193; web/src/features/building/useSirenTest.ts:96-130

### takab_support — ✅ OK

Login: web (MFA ON, 8 h); aterriza en /console con las 5 pestañas + /building. Solo tiene la acción read_audit. Celdas: Acuse/Solicitar/Reubicar/Clasificar/Firmar=N/A (lectura) · Sirena/Autodiagnóstico=N/A · Alta de sitio/usuario/códigos=N/A (decisiones T-1.32 y T-2.54: soporte lee, no provisiona) · Umbrales=N/A · Export=N/A · Auditoría=OK · Simulacro: lo ve y no lo inicia · CCTV en Evaluación=DEFECTO (403 visible) · Canales de aviso en /tenants=403 silencioso · Comandos del quórum en /console=403 silencioso · Usuario de prueba=FALTA. §2 le da «Total» en Flota Edge pero el código solo le deja leer; la divergencia está anotada en el documento (DECISION 2026-07-09).

*Evidencia:* api/src/takab_api/auth/matrix.py:73,406; takab-docs/RBAC-TAKAB.md:57,80-86

### tenant_admin — ✅ OK

Login: web (MFA ON, 8 h); aterriza en /console. Celdas: Acuse=OK · Solicitar dictamen=OK · Reubicar=OK · Clasificar=OK · Firmar=N/A · Prueba/activar/desactivar sirena=OK (/building) · Autodiagnóstico=OK (/fleet) · Alta/edición de sitio=OK · Retiro de estación=depende de que el superadmin haya configurado el código por API (409 si no existe; sin UI para rotarlo) · Alta de usuario=OK (acotado a su tenant; ver item de valores por defecto para tácticos) · Códigos de enrolamiento=OK (/fleet) · Umbrales=OK · Ventana de mantenimiento=OK · Iniciar simulacro=OK · Apagar modo demo=OK · Export/PDF=N/A (§2: Lectura) · Auditoría=OK · CCTV clip=OK · Aviso de privacidad/ARCO=FALTA UI.

*Evidencia:* api/src/takab_api/auth/matrix.py:74,407-434; web/src/features/fleet/FleetAdmin.tsx:71,107,135; web/src/features/tenants/TenantsPage.tsx:125-153; web/src/features/scene/DemoModeBanner.tsx:42

### soc_operator — ✅ OK

Login: web (MFA ON, 8 h); aterriza en /console (MONITOREO, FLOTA en lectura, EVALUACIÓN, /building). Emergencia: Acuse=OK → Reubicar epicentro=OK → Solicitar dictamen=OK (correo al inspector) → Clasificar/cerrar=OK · CCTV métricas y clip=OK · Sirena/Autodiagnóstico=N/A (§2, decisión T-1.59) · Iniciar simulacro=N/A (lo ve en el banner y en el historial) · Export/Auditoría=N/A · Ventanas de mantenimiento=solo lectura OK · Estado de check-in/pase de lista=FALTA en web · Comandos del quórum=403 silencioso.

*Evidencia:* api/src/takab_api/auth/matrix.py:75,438-445; web/src/features/console/ConsolePage.tsx:191,207-208; web/src/features/console/IncidentTable.tsx:65-87

### gov_operator — ✅ OK

Login: web (MFA ON, 8 h); aterriza en /console (MONITOREO, FLOTA, EVALUACIÓN, AUDITORÍA, /building en lectura). Celdas: Acuse=SOSPECHA (404 con el seed actual) · Solicitar/Reubicar/Clasificar=N/A (decisiones T-1.48 y T-5.12) · Firmar=N/A · Export miniSEED/PDF=OK · Generar reporte=N/A (decisión) · Sirena/Autodiagnóstico=N/A (§2: jamás actuadores ajenos) · Auditoría=OK · Simulacros (lectura)=OK · CCTV=DEFECTO (403 visible) · Ventanas de mantenimiento=no visibles (403 silencioso).

*Evidencia:* api/src/takab_api/auth/matrix.py:78,447; takab-docs/RBAC-TAKAB.md:60,69-75

### inspector — ✅ OK

WEB: pool principal, MFA ON, 8 h; aterriza en /console en lectura (MONITOREO, EVALUACIÓN, /building). Celdas web: Acuse=N/A · Recibe el correo de «solicitud de dictamen»=OK · Firmar dictamen=OK (solo en web) · Export/Generar PDF=OK · CCTV métricas=OK, clip=N/A (decisión) · Clasificar=N/A. MÓVIL: cliente mobile_tactical (MFA ON), grupo táctico; aterriza en PANEL. Pestañas: PANEL (lectura), TRIAGE (daños + cámara forense), RUTAS, DIRECTORIO, SYNC, CUENTA; sin LISTA. Celdas móvil: Check-in=OK · Activar manual=OK · Silenciar=N/A (§3) · Triage=OK pero sin firma · Cámara=OK · Pase de lista=N/A · Dictamen PDF=OK · Identidad de prueba=FALTA. En el dispositivo: NO_MEDIDO.

*Evidencia:* api/src/takab_api/auth/matrix.py:79,451-465; mobile/src/auth/pestanasTacticas.ts:41-49; mobile/src/auth/profileGate.ts:18-23; web/src/features/triage/TriagePage.tsx:251-254; takab-docs/RBAC-TAKAB.md:32,61,318-330

### building_admin — ✅ OK

WEB: aterriza en /console en lectura (MONITOREO, EVALUACIÓN, /building). A su edificio solo se llega por el enlace de DetailPanel o Triage, no hay pestaña. Celdas web: Prueba/activar/desactivar sirena=OK (/building) · Clasificar/cerrar incidente=OK (acción no documentada en RBAC) · CCTV métricas y clip=OK · Acuse/Solicitar/Reubicar=N/A · Autodiagnóstico=FALTA (inalcanzable) · Códigos de enrolamiento=FALTA (inalcanzable) · Export=N/A. MÓVIL (táctico): PANEL, LISTA, RUTAS, DIRECTORIO, SYNC, CUENTA; sin TRIAGE ni cámara (§3). Celdas móvil: Silenciar=OK · Activar=OK · Pase de lista=OK · Check-in=OK · Dictamen PDF=OK · Identidad de prueba=FALTA.

*Evidencia:* api/src/takab_api/auth/matrix.py:80,468-482; web/src/features/console/DetailPanel.tsx:206-210; web/src/features/triage/TriageDetail.tsx:287-295; web/src/features/building/BuildingPage.tsx:219; mobile/src/app/(brigadista)/panel.tsx:139-141

### brigadista — ✅ OK

Solo móvil. En la web ve MobileOnlyScreen (allowed_routes vacío). Login: cliente mobile_tactical del pool principal, MFA TOTP obligatorio. Aterriza en PANEL; tiene las 7 pestañas. Emergencia: CrisisWatcher → /crisis → check-in=OK · Activar manual (deslizar, intención firmada + MFA)=OK · Silenciar=OK · Acuse táctico de la alarma del inmueble (TacticalAckButton)=OK · Triage de daños=OK · Cámara forense con marca de agua=OK · Pase de lista con check-in delegado=OK · Dictamen PDF=OK · Canal WS en vivo=OK. Simulacro: aviso de simulacro en la franja. Pánico=N/A (tiene activación individual). Identidades sembradas: brigadista y brigadista-e2e (D-35), no verificadas hoy. En el dispositivo: NO_MEDIDO.

*Evidencia:* api/src/takab_api/auth/matrix.py:485-494; mobile/src/auth/pestanasTacticas.ts:41-49; api/src/takab_api/routers/ws.py:48-49; mobile/src/features/alert/CrisisWatcher.tsx:60-78; takab-docs/DECISIONES-MAURICIO.md:1732-1770

### security_guard — ❔ NO MEDIDO

Mismas acciones que brigadista (matrix.py:495-504) y mismas pestañas; en la web ve MobileOnlyScreen. Celdas: Check-in=OK · Activar=OK · Silenciar=OK · Triage=OK · Cámara=OK · Pase de lista=OK · Dictamen PDF=OK · WS=OK (lista escrita a mano en ws.py:48). Usuario de prueba: seed_mobile_users.sh lo acepta pero no lo crea por defecto, así que no se puede comprobar si existe en Cognito (NO_MEDIDO). Acción: sembrarlo con `seed_mobile_users.sh security_guard`.

*Evidencia:* api/src/takab_api/auth/matrix.py:495-504; api/src/takab_api/routers/ws.py:48-49; infra/scripts/seed_mobile_users.sh:79-87

### occupant — ✅ OK

Login: pool de ocupantes (MFA OPCIONAL), cliente mobile_occupants. Onboarding: permisos → aviso de privacidad → enrolamiento con código acotado al sitio (sin site_scope, R2). Aterriza en INICIO; pestañas INICIO, RUTAS, DIRECTORIO, CUENTA. Emergencia: crisis → check-in (a salvo / necesito ayuda)=OK · Pánico (voto, quórum 2/30 s, D-11 abre incidente manual)=OK · Aviso de reingreso=OK (reentry en HomeView) · Dictamen PDF=N/A (§3: solo aviso) · WS=N/A (push + REST, por construcción). En la web ve MobileOnlyScreen. TOTP opcional=FALTA. ARCO propio=FALTA. Sesión: ~60 min en la práctica (DEFECTO P0).

*Evidencia:* api/src/takab_api/auth/matrix.py:83,506; api/src/takab_api/auth/deps.py:91-94; mobile/src/app/(occupant)/inicio.tsx:53; mobile/src/app/checkin.tsx:70-78; api/src/takab_api/routers/commands.py:361-371; api/src/takab_api/routers/ws.py:81-86

## 4 · Todos los hallazgos

Ordenados por prioridad. `A-nnn` es el identificador estable de esta auditoría; las fichas
`T-8.xx` los citan.

| ID | P | Estado | Dimensión | Hallazgo | Roles | Evidencia | Ficha |
|---|---|---|---|---|---|---|---|
| A-001 | P0 | 🔴 DEFECTO | Móvil | CONFIRMADO: el refreshToken se guarda pero nunca se usa; la sesión móvil muere a los ~60 min | occupant, brigadista, security_guard, inspector, building_a… | mobile/src/auth/useAuth.ts:48; mobile/src/auth/useAuth.ts:76-81; mobile/src/auth/secureTokens.ts:29; mobile/s… | T-8.04 |
| A-002 | P0 | ⬜ FALTA | Móvil | Diseño exacto de la renovación: REST, socket, camino offline y arranque (expo-auth-session) | todos los roles móviles | mobile/src/services/sdk.ts:39-51; mobile/src/live/socket.ts:21-25; shared/sdk-ts/src/live.ts:135-139; shared/… | T-8.04 |
| A-003 | P0 | ⬜ FALTA | Móvil | Política «1 mes» (brigadista, inspector, ocupante) / «1 día» (resto): Terraform no la puede expresar hoy | brigadista, inspector, occupant (30 d); security_guard, bui… | infra/terraform/modules/identity/main.tf:155-168; infra/terraform/modules/identity/main.tf:619-638; infra/ter… | T-8.04 |
| A-004 | P0 | 🔴 DEFECTO | Sesiones por rol | Web: el WS cierra la sesión a los ~60 min aunque el silent renew funcione | todos los roles web | api/src/takab_api/routers/ws.py:88-99; shared/sdk-ts/src/live.ts:42-45,156-162,215-225; web/src/live/LiveSock… | T-8.03 |
| A-005 | P0 | 🔴 DEFECTO | Sesiones por rol | Móvil: implementar el refresh (hoy la sesión real dura 60 min) | brigadista, inspector, security_guard, building_admin, occu… | mobile/src/auth/useAuth.ts:48,76-81,89-116; mobile/src/services/sdk.ts:46-48; mobile/src/live/socket.ts:24; m… | T-8.04 |
| A-006 | P0 | ❔ NO MEDIDO | Sesiones por rol | auth_time al refrescar: no documentado por AWS (todo el tope por rol depende de ello) | security_guard, building_admin, roles web | api/src/takab_api/auth/mfa.py:14-19,85-88; takab-docs/specs/cognito-pool-v1.md:195-197 | T-8.02 |
| A-007 | P0 | 🔴 DEFECTO | RBAC y flujos | La app móvil nunca renueva el token: la sesión dura unos 60 min y luego vuelve a pedir contraseña (y MFA a los tácticos) | occupant, brigadista, security_guard, inspector, building_a… | mobile/src/auth/useAuth.ts:36-48,76-81,89-117; mobile/src/services/sdk.ts:46-49; mobile/src/live/socket.ts:3,… | T-8.04 |
| A-008 | P0 | ⬜ FALTA | RBAC y flujos | Petición: 30 días sin contraseña ni MFA para brigadista, inspector y ocupante; 1 día para el resto. Estado actual y cómo cumplirlo | todos | infra/terraform/modules/identity/main.tf:42,142-168,535,611-643,645-679; web/src/auth/userManager.ts:24-26; a… | T-8.05 |
| A-009 | P0 | 🔴 DEFECTO | Funciones básicas | La sesión móvil NO se renueva: el refresh token se guarda y nunca se usa | occupant, brigadista, security_guard, inspector, building_a… | mobile/src/auth/useAuth.ts:48,76-81,88-117; mobile/src/auth/secureTokens.ts:25-32; mobile/src/services/sdk.ts… | T-8.04 |
| A-010 | P1 | ⬜ FALTA | Web · MONITOREO/EVALUACIÓN | Duración de sesión actual frente a la política pedida (1 mes tácticos/ocupante, 1 día el resto) | todos | web/src/auth/userManager.ts:24-26; web/src/auth/session.store.ts:136-139; infra/terraform/modules/identity/ma… | T-8.03 |
| A-011 | P1 | 🔴 DEFECTO | Web · MONITOREO/EVALUACIÓN | El acuse se lanza sin esperar respuesta: los errores se tragan y el botón dice EJECUTADO igual | takab_superadmin, tenant_admin, soc_operator, gov_operator | web/src/features/console/ConsolePage.tsx:191-201; web/src/features/console/IncidentTable.tsx:352-363; web/src… | T-8.07 |
| A-012 | P1 | 🔴 DEFECTO | Web · MONITOREO/EVALUACIÓN | La selección de la cola es por SITIO, no por incidente: con 2+ incidentes abiertos en un sitio se actúa sobre el equivocado | takab_superadmin, tenant_admin, soc_operator, gov_operator | web/src/features/console/ConsolePage.tsx:90-95,323-324; web/src/features/console/IncidentTable.tsx:248-253; d… | T-8.07 |
| A-013 | P1 | 🔴 DEFECTO | Web · MONITOREO/EVALUACIÓN | El Modal le roba el foco a los campos cada segundo en /console | superadmin, tenant_admin, soc_operator (reubicar); todos lo… | web/src/components/Modal.tsx:18-28; web/src/features/console/ConsolePage.tsx:62,346-354,357-371; web/src/feat… | T-8.07 |
| A-014 | P1 | 🔴 DEFECTO | Web · MONITOREO/EVALUACIÓN | El botón DESCARGAR CLIP no hace nada | takab_superadmin, tenant_admin, soc_operator, building_admin | web/src/features/triage/CctvPanel.tsx:133-140; web/src/features/triage/TriagePage.tsx:239-265 (sin onDownload… | T-8.08 |
| A-015 | P1 | 🟠 SOSPECHA | Web · MONITOREO/EVALUACIÓN | La firma solo aparece si ya hay un dictamen previo; la API permite firmar el primero | inspector | web/src/features/triage/TriageDetail.tsx:479-547; api/src/takab_api/routers/dictamens.py:72-97 | T-8.08 |
| A-016 | P1 | 🟠 SOSPECHA | Web · MONITOREO/EVALUACIÓN | El simulacro de takab_superadmin con selección vacía apunta a gabinetes de TODOS los tenants | takab_superadmin | web/src/features/console/DrillModal.tsx:298,381; api/src/takab_api/routers/drills.py:66-70,470-498,520-528; a… | T-8.07 |
| A-017 | P1 | 🔴 DEFECTO | Web · flota/tenants/edificio | gov_operator ve una alerta roja permanente 'VENTANAS DE MANTENIMIENTO SIN LECTURA' | gov_operator | web/src/features/fleet/FleetPage.tsx:257-269; web/src/features/console/useMaintenanceWindows.ts:27-38,78-90,1… | T-8.09 |
| A-018 | P1 | 🔴 DEFECTO | Web · flota/tenants/edificio | La tarjeta 'Usuarios del cliente' muestra los usuarios de TODOS los clientes cuando la ve un rol interno | takab_superadmin | web/src/features/tenants/UsersCard.tsx:84,118,151; web/src/features/tenants/useUsers.ts:65-93; api/src/takab_… | T-8.09 |
| A-019 | P1 | 🔴 DEFECTO | Web · flota/tenants/edificio | Después de SILENCIAR SIRENA el panel dice 'SIRENA SONANDO · ACUSADA POR EL EDGE' | takab_superadmin, tenant_admin, building_admin | web/src/features/building/useSirenTest.ts:48-60,106-110,123-130; web/src/features/building/SirenTestPanel.tsx… | T-8.09 |
| A-020 | P1 | 🔴 DEFECTO | Móvil | El logout no revoca el refresh, no cierra la cookie de la Hosted UI ni da de baja el token push | todos los móviles | mobile/src/auth/session.store.ts:41-45; mobile/src/auth/config.ts:22; mobile/src/auth/config.ts:45-57; api/sr… | T-8.04 |
| A-021 | P1 | 🔴 DEFECTO | Móvil | Pestaña CUENTA sin red o con /me/profile caído: sin botón de cerrar sesión ni de reintentar | todos los móviles | mobile/src/features/account/AccountScreen.tsx:95-101; mobile/src/ui/StateFrame.tsx:59-76; mobile/src/auth/pes… | T-8.11 |
| A-022 | P1 | 🔴 DEFECTO | Móvil | «VER DICTAMEN DE REINGRESO» lleva a «Sin incidente activo» después del cierre automático D-33 | brigadista, security_guard, inspector, building_admin | api/src/takab_api/routers/mobile_site.py:275-284; mobile/src/app/(brigadista)/panel.tsx:210-221; mobile/src/f… | T-8.11 |
| A-023 | P1 | 🔴 DEFECTO | Móvil | La revisión «USAR ESTA FOTO / Repetir» muestra el visor en vivo, no la foto tomada | brigadista, security_guard, inspector | mobile/src/app/camera.tsx:124; mobile/src/app/camera.tsx:168-185; mobile/src/app/camera.tsx:299-318; mobile/s… | T-8.11 |
| A-024 | P1 | 🔴 DEFECTO | Móvil | El check-in delegado (verify-*) no se encola sin red, y el E2E 05b lo acredita de forma vacía | brigadista, security_guard, building_admin | mobile/src/app/(brigadista)/lista.tsx:112-139; mobile/src/offline/queue.ts:22-33; mobile/src/app/(brigadista)… | T-8.11 |
| A-025 | P1 | 🟠 SOSPECHA | Móvil | En teléfono compartido la cola offline, el onboarding y el consentimiento GPS no tienen dueño | todos los móviles (crítico security_guard por turnos) | mobile/src/offline/queue.ts:68-87; mobile/src/offline/OfflineSyncGate.tsx:18-25; mobile/src/services/onboardi… | T-8.18 |
| A-026 | P1 | ⬜ FALTA | Sesiones por rol | Tabla SESSION_MAX_AGE_S por rol en la matriz ejecutable | todos | api/src/takab_api/auth/matrix.py:68-71; api/tests/auth/test_matrix.py:53 | T-8.02 |
| A-027 | P1 | ⬜ FALTA | Sesiones por rol | Exigir auth_time en la verificación y guardarlo en Claims | todos | api/src/takab_api/auth/tokens.py:68-77; api/src/takab_api/auth/claims.py:47-90; takab-docs/specs/cognito-pool… | T-8.02 |
| A-028 | P1 | ⬜ FALTA | Sesiones por rol | Punto exacto del tope: función enforce_session_age llamada desde get_claims | todos | api/src/takab_api/auth/deps.py:46,71-99; api/src/takab_api/auth/mfa.py:132-150; api/src/takab_api/routers/com… | T-8.02 |
| A-029 | P1 | ⬜ FALTA | Sesiones por rol | WS: plazo = min(exp, auth_time+max_age) y código de cierre propio | soc_operator, gov_operator, tenant_admin, takab_*, inspecto… | api/src/takab_api/routers/ws.py:37,80-82,88-99,113-130 | T-8.02 |
| A-030 | P1 | 🟠 SOSPECHA | Sesiones por rol | Móvil: la caducidad de la sesión no debe tapar la pantalla de crisis | occupant, brigadista | mobile/src/app/crisis.tsx:60-61; mobile/src/auth/secureTokens.ts:71-79; takab-docs/design/app/ESPECIFICACION-… | T-8.18 |
| A-031 | P1 | ⬜ FALTA | Sesiones por rol | Terraform: validez del refresh por app client | todos | infra/terraform/modules/identity/main.tf:142-168,611-643,647-679; infra/terraform/envs/dev/.terraform.lock.hc… | T-8.05 |
| A-032 | P1 | ⬜ FALTA | Sesiones por rol | Web: persistencia de la sesión (sessionStorage vs localStorage) | roles web + inspector | web/src/auth/userManager.ts:13-27; web/src/features/fleet/GatewayAcuse.tsx:79; takab-docs/DECISIONES-MAURICIO… | T-8.03 |
| A-033 | P1 | ⬜ FALTA | Sesiones por rol | Web: el arranque descarta sesiones con access token vencido aunque haya refresh | roles web | web/src/auth/session.store.ts:142-165 | T-8.03 |
| A-034 | P1 | 🔷 MEJORA | Sesiones por rol | Web: mostrar 'sesión expirada por tope' distinto del 401 genérico | roles web | web/src/auth/session.store.ts:54-66,242-254; web/src/auth/apiClient.ts:26-31; web/src/auth/me.ts:7-18; web/sr… | T-8.03 |
| A-035 | P1 | ⬜ FALTA | Sesiones por rol | Fábricas de tokens de test y /dev/token deben emitir auth_time | n/a | api/tests/auth_utils.py:81-120; api/src/takab_api/routers/dev_token.py:27-43,73-88 | T-8.02 |
| A-036 | P1 | 🔷 MEJORA | Sesiones por rol | Kill switch administrativo para sesiones de 30 días | tenant_admin, takab_superadmin (acción); brigadista/inspect… | api/src/takab_api/users/directory.py:382-387 | T-8.02 |
| A-037 | P1 | ⬜ FALTA | Sesiones por rol | D-38 en DECISIONES-MAURICIO.md (con cabecera y reparto) | n/a | takab-docs/DECISIONES-MAURICIO.md:14-17,36,1832; api/tests/test_docs_consistency.py:2060-2101 | T-8.05 |
| A-038 | P1 | 🟠 SOSPECHA | Sesiones por rol | Regla de oro 8: los roles con actuadores mostrarían MFA una vez al mes | brigadista, inspector | takab-docs/RBAC-TAKAB.md:345-378; api/src/takab_api/routers/commands.py:84-104; api/src/takab_api/auth/mfa.py… | T-8.05 |
| A-039 | P1 | 🟠 SOSPECHA | Sesiones por rol | Corte de 24 h en plena emergencia para el SOC | soc_operator, gov_operator, tenant_admin, takab_* | api/src/takab_api/auth/mfa.py:85-88; web/src/shell/Topbar.tsx | T-8.03 |
| A-040 | P1 | 🟠 SOSPECHA | Sesiones por rol | Refresh de larga vida en localStorage de una consola pública sin CSP | roles web, inspector | takab-docs/DECISIONES-MAURICIO.md:924-947; web/src/auth/userManager.ts:24; infra/terraform/modules/site/main.… | T-8.03 |
| A-041 | P1 | ⬜ FALTA | RBAC y flujos | No hay usuario de prueba takab_support | takab_support | infra/scripts/seed_console_users.sh:30-33 | T-8.13 |
| A-042 | P1 | 🔴 DEFECTO | RBAC y flujos | El panel CCTV de EVALUACIÓN muestra un error 403 a support y a gov | takab_support, gov_operator | web/src/features/triage/useCctv.ts:31-44; web/src/features/triage/TriagePage.tsx:97; web/src/features/triage/… | T-8.08 |
| A-043 | P1 | ⬜ FALTA | RBAC y flujos | La consola no muestra check-ins de vida ni el pase de lista aunque los datos existen | soc_operator, tenant_admin, takab_superadmin, building_admi… | api/src/takab_api/routers/mobile_incident.py:52-65,182-199; api/src/takab_api/auth/matrix.py:164-165; web/src… | T-8.14 |
| A-044 | P1 | 🟠 SOSPECHA | RBAC y flujos | El gov_operator sembrado vive en un tenant privado: ve el botón ACUSAR y la API responde 404; su aislamiento no se puede demostrar | gov_operator | infra/scripts/seed_console_users.sh:28,60-63; db/seeds/prod_fleet.sql:24-26; db/schema.sql:119,795-799,887-88… | T-8.13 |
| A-045 | P1 | ⬜ FALTA | RBAC y flujos | Inspector y building_admin no tienen identidad para móvil (el documento dice Web + Móvil) | inspector, building_admin | infra/scripts/seed_console_users.sh:30-33,62-63,73-74; infra/scripts/seed_mobile_users.sh:79-87,123-128; mobi… | T-8.13 |
| A-046 | P1 | ⬜ FALTA | RBAC y flujos | enrollment_manage y self_test de building_admin no se pueden usar desde ninguna pantalla | building_admin | api/src/takab_api/auth/matrix.py:468-482; web/src/features/fleet/FleetAdmin.tsx:135,219; web/src/features/fle… | T-8.19 |
| A-047 | P1 | 🟠 SOSPECHA | RBAC y flujos | Si la app arranca sin red, desaparecen PANEL, TRIAGE y LISTA y se apagan los controles tácticos | brigadista, security_guard, inspector, building_admin | mobile/src/auth/useAuth.ts:85-117; mobile/src/auth/pestanasTacticas.ts:51-63; mobile/src/app/(brigadista)/pan… | T-8.18 |
| A-048 | P1 | 🔴 DEFECTO | RBAC y flujos | Un táctico creado desde la consola queda sin edificio en la app (site_scope '*' y surface 'web' por defecto) | brigadista, security_guard, inspector, building_admin | web/src/features/tenants/UsersCard.tsx:91,321-332; mobile/src/services/mySite.ts:1-5,109-124; mobile/src/auth… | T-8.19 |
| A-049 | P1 | ❔ NO MEDIDO | RBAC y flujos | No se puede comprobar si las identidades sembradas existen hoy en Cognito ni su estado de MFA | todos | infra/scripts/seed_console_users.sh:93-101; infra/scripts/seed_mobile_users.sh:240-261; takab-docs/DECISIONES… | T-8.13 |
| A-050 | P1 | 🔴 DEFECTO | PDF | §14 DAÑOS: con UNA foto (o con un número impar) lo siguiente se pinta encima del pie de foto | todos los que reciben el PDF | api/src/takab_api/dictamen/pdf.py:1592-1616,1575-1578; takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:171-1… | T-8.12 |
| A-051 | P1 | 🔴 DEFECTO | PDF | Las fotos en vertical superan la reserva de página y pueden pisar el pie (hash, paginación, razón social) | todos los que reciben el PDF | api/src/takab_api/documentos/fotos.py:157-161; api/src/takab_api/dictamen/pdf.py:1511-1518,1592-1600; api/tes… | T-8.12 |
| A-052 | P1 | 🔴 DEFECTO | PDF | «VERIFICAR HASH» del dictamen en Triage da 404 (rojo «NO SE PUDO VERIFICAR») para superadmin, support, tenant_admin, soc_operator y gov_operator | takab_superadmin, takab_support, tenant_admin, soc_operator… | api/src/takab_api/routers/mobile_incident.py:619-629,646-649; api/src/takab_api/auth/matrix.py:361-400,459,47… | T-8.08 |
| A-053 | P1 | ⬜ FALTA | PDF | El papel no rotula la clasificación humana del incidente (reproducción, prueba, falso positivo); «REPRODUCCIÓN» solo sale en la §7 si el evento es un replay | todos los que reciben el PDF | api/src/takab_api/dictamen/model.py:1006-1013,166-177; api/src/takab_api/dictamen/pdf.py:183-194,759-764; db/… | T-8.12 |
| A-054 | P1 | 🟠 SOSPECHA | PDF | El certificado de reingreso del móvil puede abrir un PDF PRELIMINAR (anterior a la firma) | inspector, building_admin, brigadista, security_guard | api/src/takab_api/queries/mobile.py:198-202; api/src/takab_api/routers/mobile_incident.py:379-425; api/src/ta… | T-8.12 |
| A-055 | P1 | ❔ NO MEDIDO | PDF | Revisión visual real de cada PDF y datos de la nube | todos | takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:66-84,124-135 | T-8.12 |
| A-056 | P1 | 🔴 DEFECTO | Estatus visibles | GET /fleet/gateways descarta disco y evidencia retenida: siempre null | takab_superadmin, takab_support, tenant_admin, soc_operator… | api/src/takab_api/routers/fleet.py:284-353; api/src/takab_api/queries/fleet.py:48-52,58-62; api/src/takab_api… | T-8.09 |
| A-057 | P1 | 🔴 DEFECTO | Estatus visibles | El LWT 'offline' hace que el gabinete parezca vivo durante sin_enlace_min | todos (consola: mapa/flota/edificio; móvil: estado del siti… | api/src/takab_api/ingest/handlers.py:927-931,994-1013; api/src/takab_api/queries/fleet.py:58-66; api/src/taka… | T-8.09 |
| A-058 | P1 | ⬜ FALTA | Estatus visibles | actuation_records (bitácora del gabinete) sin endpoint, sin UI y fuera del PDF | tenant_admin, soc_operator, gov_operator, inspector, buildi… | db/schema.sql:724-808; api/src/takab_api/ingest/handlers.py:683-739; edge/takab_edge/local_api/__init__.py:14… | T-8.14 |
| A-059 | P1 | ⬜ FALTA | Estatus visibles | MODO PRUEBA WR-1 («la nube no recibe alertas») invisible desde la nube | soc_operator, tenant_admin, takab_superadmin/support | edge/takab_edge/local_api/__init__.py:1595-1602; shared/schemas/health_snapshot.schema.json (sin campo); web/… | T-8.14 |
| A-060 | P1 | 🔴 DEFECTO | Animaciones | El faro sobre los edificios que DISPARARON sigue pulsando con prefers-reduced-motion | roles de consola web (soc_operator, gov_operator, tenant_ad… | web/src/features/console/MapPanel.tsx:486-488,677-690,1064-1068,1379-1381; web/e2e/motion.spec.ts:60-150 | T-8.09 |
| A-061 | P1 | 🔴 DEFECTO | Animaciones | El parpadeo del banner rojo atenúa TAMBIÉN la instrucción: ~1.6:1 de contraste medio ciclo | personas en el inmueble frente al kiosco, security_guard, b… | edge/takab_edge/local_api/index.html:55,107-108,418-422; edge/tests/test_local_api_panel.py:1030-1045; takab-… | T-8.15 |
| A-062 | P1 | 🔷 MEJORA | Animaciones | Ningún botón de la app responde visualmente al toque | occupant, brigadista, security_guard, inspector, building_a… | mobile/src (grep '<Pressable' = 57, 'pressed' = 0); mobile/src/features/checkin/CheckinView.tsx:28-64; mobile… | T-8.11 |
| A-063 | P1 | 🔴 DEFECTO | Funciones básicas | Si la red corrobora (cuórum), la consola y el teléfono se contradicen | soc_operator, gov_operator, tenant_admin, occupant, brigadi… | web/src/features/console/AlertBanner.tsx:73; mobile/src/features/alert/source.ts:79-80; takab-docs/PLAN-REVIS… | T-8.10 |
| A-064 | P1 | ⬜ FALTA | Funciones básicas | La sirena NO suena con el Pi apagado (ruta de hardware paralela, G-02) | building_admin, occupant, cliente | takab-docs/TASKS.md:10416-10432 (T-2.92); takab-docs/INFORME-V1-COMERCIAL.md:61 (H-05); edge/takab_edge/confi… | T-8.19 |
| A-065 | P1 | 🟠 SOSPECHA | Funciones básicas | El apartado 14 del PDF («DAÑOS REPORTADOS EN CAMPO») se rompe en todos los incidentes con foto, y no tiene ficha | inspector, cliente receptor del PDF | api/src/takab_api/dictamen/pdf.py:1540; takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:171-172 | T-8.12 |
| A-066 | P1 | 🟠 SOSPECHA | Funciones básicas | Dictamen «completo» no demostrable con los datos de la nube de hoy | inspector, soc_operator | takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:79-84; takab-docs/TASKS.md:15371 (T-7.28 [~]) | T-8.13 |
| A-067 | P1 | 🟠 SOSPECHA | Funciones básicas | La duración de sesión por rol no se puede expresar con los app clients actuales | todos | infra/terraform/modules/identity/main.tf:160-168,629-635,665-671; web/src/auth/userManager.ts:24-26; takab-do… | T-8.05 |
| A-068 | P1 | ⬜ FALTA | Funciones básicas | No hay app iOS ni publicación en tiendas | occupant, brigadista, security_guard, inspector, building_a… | mobile/app.json (ios.bundleIdentifier=com.takab.ailert); takab-docs/TASKS.md:10476-10500 (T-2.97, T-2.98); ta… | T-8.19 |
| A-069 | P1 | ⬜ FALTA | Funciones básicas | No existe camino para crear cuentas de ocupante | occupant, building_admin, tenant_admin | infra/terraform/modules/identity/main.tf:556-559; api/src/takab_api/schemas/users.py:26-29; takab-docs/specs/… | T-8.19 |
| A-070 | P1 | ⬜ FALTA | Funciones básicas | Zonas/pisos y su política EVACÚE/REPLIÉGUESE no se pueden dar de alta | tenant_admin, building_admin, takab_support, occupant (afec… | api/src/takab_api/routers/sites.py:100-103; api/src/takab_api/schemas/sites.py:44; db/seeds/e2e_harness.sql:48 | T-8.19 |
| A-071 | P1 | 🟠 SOSPECHA | Funciones básicas | Cascada de notificación: solo webhook, correo verificado y push Android entregan de verdad | tenant_admin, soc_operator, gov_operator, occupant | api/src/takab_api/notify/providers.py:40-72; takab-docs/TASKS.md:7033,7218,7348; takab-docs/PENDIENTES-MAURIC… | T-8.19 |
| A-072 | P1 | ⬜ FALTA | Funciones básicas | La gestión de usuarios de la consola corre SIMULADA en la nube (T-2.87) | tenant_admin, takab_superadmin | deploy/cloud/deploy.sh:125-175 (sin COGNITO_USER_POOL_ID); infra/terraform/modules/database/main.tf:532-537; … | T-8.19 |
| A-073 | P1 | 🟠 SOSPECHA | Funciones básicas | Backups y DR: construidos, pero el RTO de producción no está medido y el WAL no se verifica en S3 | takab_superadmin, takab_support | api/src/takab_api/ops/restore_check.py; api/src/takab_api/ops/restore_drill.py; takab-docs/TASKS.md:6318,6851… | T-8.16 |
| A-074 | P1 | ⬜ FALTA | Funciones básicas | Lo que un cliente esperaría y hoy no se puede demostrar | todos | takab-docs/INFORME-V1-COMERCIAL.md:120-138; takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:66-139; takab-do… | T-8.19 |
| A-075 | P1 | ⬜ FALTA | Funciones básicas | Fichas que dependen de Mauricio (PENDIENTES: 30 puntos) | n/a | takab-docs/TASKS.md:1008,1071,5322,5940,6851,7033-7348,10347-10500,10682,11190,11337-11357,12762,15371; takab… | T-8.19 |
| A-076 | P1 | 🔴 DEFECTO | Edge/nube/presentación | El paso 7.b de deploy.sh «blanquea» el rojo del dueño de los pines en el segundo despliegue, y la poda puede borrar la release que el dueño está corriendo | n/a (operación/despliegue) | deploy/edge/deploy.sh:459; deploy/edge/deploy.sh:993-1034; deploy/edge/deploy.sh:721-737; edge/takab_edge/gpi… | T-8.17 |
| A-077 | P1 | ⬜ FALTA | Edge/nube/presentación | La versión que corre el dueño de los pines (takab-gpio) no se ve en ningún sitio | takab_superadmin, takab_support (flota) | edge/takab_edge/health/__init__.py:466-470; edge/takab_edge/version.py:106-113; edge/takab_edge/contracts.py:… | T-8.17 |
| A-078 | P1 | 🟠 SOSPECHA | Edge/nube/presentación | cloud.publish() hace fsync y espera el PUBACK (hasta 10 s) en el hilo de SeedLink: puede cegar la detección instrumental | todos (detección) | edge/takab_edge/supervisor.py:598-614; edge/takab_edge/supervisor.py:850; edge/takab_edge/telemetry/__init__.… | T-8.17 |
| A-079 | P1 | 🔷 MEJORA | Edge/nube/presentación | Cada despliegue tira el stack entero: se reinicia con `compose down`+`up` y sin descargar antes las imágenes | todos (indisponibilidad durante el despliegue) | deploy/cloud/deploy.sh:339-355; deploy/cloud/deploy.sh:417-429; deploy/cloud/deploy.sh:520-523; deploy/cloud/… | T-8.16 |
| A-080 | P1 | 🟠 SOSPECHA | Edge/nube/presentación | Generar el PDF bloquea el event loop de un uvicorn de un solo worker | inspector, takab_superadmin (generan); todos (sufren el con… | api/src/takab_api/routers/reports.py:50-136; api/src/takab_api/routers/drills.py:852-855; api/src/takab_api/d… | T-8.12 |
| A-081 | P1 | ⬜ FALTA | Edge/nube/presentación | No hay alarma de edad o profundidad de la cola PRINCIPAL de SQS ni healthcheck en los contenedores | todos (alertamiento) | infra/terraform/modules/observability/main.tf:166-186; infra/terraform/modules/observability/main.tf:354-376;… | T-8.16 |
| A-082 | P1 | ⬜ FALTA | Edge/nube/presentación | Backups y DR: el restore real con RTO medido y la comprobación del WAL en S3 siguen abiertos; una sola instancia | n/a | takab-docs/TASKS.md:6318-6328; takab-docs/TASKS.md:6851; takab-docs/PENDIENTES-MAURICIO.md:338-356; infra/ter… | T-8.16 |
| A-083 | P1 | 🔷 MEJORA | Edge/nube/presentación | Sesiones: la duración pedida (30 días campo/ocupante, 1 día resto) choca con cómo está montado Cognito | brigadista, inspector, occupant (30 d); tenant_admin, soc_o… | infra/terraform/modules/identity/main.tf:160-167; infra/terraform/modules/identity/main.tf:629-636; infra/ter… | T-8.05 |
| A-084 | P1 | 🔴 DEFECTO | Edge/nube/presentación | El guion y el RUNBOOK siguen mandando `POST /api/reset` SIN PIN, y en el último paso eso da 401 | building_admin/presentador (panel) | deploy/demo/guion.sh:713; deploy/demo/guion.sh:143; takab-docs/runbooks/RUNBOOK-demo-cliente.md:366-368; taka… | T-8.13 |
| A-085 | P1 | ⬜ FALTA | Edge/nube/presentación | Los dos incidentes del ensayo 1 siguen sin clasificar, y el Goal de la fase no puede pasar | soc_operator / inspector (clasificar) | takab-docs/runbooks/RUNBOOK-demo-cliente.md:554-565; takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:292-303… | T-8.13 |
| A-086 | P1 | ⬜ FALTA | Edge/nube/presentación | F7 / T-7.28 sigue abierta: faltan el ensayo 2, las capturas, el vídeo y el veredicto de flujos; el ensayo 1 duró 59 min | todos (presentador, brigadista, inspector, occupant) | takab-docs/TASKS.md:15371-15444; takab-docs/runbooks/RUNBOOK-demo-cliente.md:486-587; takab-docs/PLAN-PROTOTI… | T-8.13 |
| A-087 | P1 | 🔷 MEJORA | Edge/nube/presentación | Mergear la rama de instrumentos antes del día: en main, goal-presentacion.sh todavía da veredictos ciegos | n/a (presentador) | git log main..HEAD (b804039); deploy/demo/goal-presentacion.sh; deploy/cloud/conformidad.sh | T-8.01 |
| A-088 | P1 | ⬜ FALTA | Edge/nube/presentación | Ningún documento de la demo dice cómo evitar que la sesión caduque o haya que repetir el MFA a mitad de la presentación | los 6 roles web, brigadista, inspector | infra/terraform/modules/identity/main.tf:160-167; infra/terraform/modules/identity/main.tf:665-672; web/src/a… | T-8.13 |
| A-089 | P2 | 🟠 SOSPECHA | Web · MONITOREO/EVALUACIÓN | ScopeBadge dice 'TODO EL TENANT' a roles internos que ven TODOS los tenants | takab_superadmin, takab_support, gov_operator | web/src/auth/useSiteScope.ts:34-44; web/src/components/ScopeBadge.tsx:7-16; db/schema.sql:887-889,960-962; we… | T-8.07 |
| A-090 | P2 | 🔴 DEFECTO | Web · MONITOREO/EVALUACIÓN | GET /sites/{id}/commands da 403 al SOC cada 15 s: QUÓRUM RED nunca se muestra | soc_operator, gov_operator, takab_support | web/src/features/console/useQuorumCommands.ts:60-61; web/src/features/console/DetailPanel.tsx:422-430; api/sr… | T-8.08 |
| A-091 | P2 | 🔴 DEFECTO | Web · MONITOREO/EVALUACIÓN | El panel CCTV muestra error permanente a gov_operator y takab_support | gov_operator, takab_support | web/src/features/triage/useCctv.ts:26-43; web/src/features/triage/TriageDetail.tsx:344; api/src/takab_api/rou… | T-8.08 |
| A-092 | P2 | 🔴 DEFECTO | Web · MONITOREO/EVALUACIÓN | El verificador de huella del dictamen PDF falla con 404 para 5 roles | takab_superadmin, takab_support, tenant_admin, soc_operator… | web/src/features/triage/TriageDetail.tsx:392-399; web/src/features/triage/EvidenceVerifier.tsx:11-46; api/src… | T-8.08 |
| A-093 | P2 | 🔴 DEFECTO | Web · MONITOREO/EVALUACIÓN | BORRAR plantilla de simulacro sin confirmación | takab_superadmin, tenant_admin | web/src/features/console/DrillModal.tsx:199-210; web/src/features/console/useDrillTemplates.ts; api/src/takab… | T-8.08 |
| A-094 | P2 | 🟠 SOSPECHA | Web · MONITOREO/EVALUACIÓN | INICIAR AHORA y EJECUTAR AHORA vocean en edificios reales con un solo clic | takab_superadmin, tenant_admin | web/src/features/console/DrillModal.tsx:376-383; web/src/features/scene/DrillBanner.tsx:213-229; web/src/comp… | T-8.07 |
| A-095 | P2 | ⬜ FALTA | Web · MONITOREO/EVALUACIÓN | No hay control en la UI para ENCENDER el modo demostración | takab_superadmin | web/src/features/console/useDemoMode.ts:27,48,72; web/src/features/scene/DemoModeBanner.tsx:84-92; api/src/ta… | T-8.19 |
| A-096 | P2 | 🔷 MEJORA | Web · MONITOREO/EVALUACIÓN | La cola no muestra el ESTADO del incidente (abierto / acusado / en revisión) | los 7 roles web | web/src/features/console/IncidentTable.tsx:233-241,244-290; web/src/features/console/useLiveIncidents.ts:69,8… | T-8.07 |
| A-097 | P2 | 🟠 SOSPECHA | Web · MONITOREO/EVALUACIÓN | Las ventanas de mantenimiento no se muestran a gov_operator, inspector ni building_admin (contradice el comentario de la API) | gov_operator, inspector, building_admin | api/src/takab_api/routers/maintenance.py:111-116; web/src/features/scene/SceneStrip.tsx:116-119; web/src/feat… | T-8.09 |
| A-098 | P2 | 🔴 DEFECTO | Web · flota/tenants/edificio | El error al abrir una ventana nunca se ve: el diálogo se cierra antes de la respuesta | takab_superadmin, tenant_admin | web/src/features/fleet/FleetPage.tsx:386-398; web/src/features/console/useMaintenanceWindows.ts:107-133; web/… | T-8.09 |
| A-099 | P2 | 🟠 SOSPECHA | Web · flota/tenants/edificio | OpenWindowDialog usa controles HTML sin clases ni estilos y un aria-describedby roto | takab_superadmin, tenant_admin | web/src/features/fleet/OpenWindowDialog.tsx:63-118,74; web/src/styles/soc.css:1256-1280; web/src/styles/soc-t… | T-8.09 |
| A-100 | P2 | 🔴 DEFECTO | Web · flota/tenants/edificio | RESTAURAR gabinete no muestra el error si falla | takab_superadmin, tenant_admin | web/src/features/fleet/FleetPage.tsx:171,315-316; web/src/features/fleet/SiteCard.tsx:139-149; web/src/featur… | T-8.09 |
| A-101 | P2 | 🔴 DEFECTO | Web · flota/tenants/edificio | Un gabinete 'fantasma' (retirado pero reportando) no se puede restaurar desde la web | takab_superadmin, tenant_admin | web/src/features/fleet/FleetPage.tsx:64-90,190-194,244-246; web/src/features/fleet/FleetPage.test.tsx:650-658… | T-8.09 |
| A-102 | P2 | 🔴 DEFECTO | Web · flota/tenants/edificio | Si el POST de autodiagnóstico falla, el motivo no se muestra | takab_superadmin, tenant_admin | web/src/features/fleet/SiteCard.tsx:355-391; web/src/features/fleet/useSelfTest.ts:98-101,109; api/src/takab_… | T-8.09 |
| A-103 | P2 | 🔴 DEFECTO | Web · flota/tenants/edificio | El aviso de 'código de retiro configurado' revisa el cliente de la SESIÓN, no el del objeto | takab_superadmin | web/src/features/fleet/FleetPage.tsx:153-154; web/src/features/fleet/FleetAdmin.tsx:106-107; web/src/features… | T-8.09 |
| A-104 | P2 | 🔴 DEFECTO | Web · flota/tenants/edificio | AÑADIR SENSOR no confirma el alta ni limpia el formulario (riesgo de duplicados) | takab_superadmin, tenant_admin | web/src/features/fleet/FleetAdmin.tsx:189-207; web/src/features/fleet/HardwareForm.tsx:212-226 | T-8.09 |
| A-105 | P2 | 🟠 SOSPECHA | Web · flota/tenants/edificio | Una estación nueva se puede crear en la coordenada por defecto (Puebla), o en 0 si se borra el campo | takab_superadmin, tenant_admin | web/src/features/fleet/SiteForm.tsx:92,271,281; web/src/features/fleet/geo.ts:8,23-25 | T-8.09 |
| A-106 | P2 | 🔴 DEFECTO | Web · flota/tenants/edificio | La lista de usuarios ignora next_cursor: se trunca a 50 y el cliente puede ver 'SIN USUARIOS' con usuarios existentes | takab_superadmin, tenant_admin | web/src/features/tenants/useUsers.ts:73-93; api/src/takab_api/routers/users.py:236-246; api/src/takab_api/rou… | T-8.09 |
| A-107 | P2 | 🔴 DEFECTO | Web · flota/tenants/edificio | Acciones sobre usuarios sin confirmación: DAR DE BAJA (irreversible), cambio de rol inmediato, deshabilitar | takab_superadmin, tenant_admin | web/src/features/tenants/UsersCard.tsx:169-181,186-203,266-289 | T-8.09 |
| A-108 | P2 | 🔴 DEFECTO | Web · flota/tenants/edificio | Un admin puede deshabilitarse o quitarse su propio rol, y el 409 de 'darse de baja a sí mismo' aparece como 'YA EXISTE' | takab_superadmin, tenant_admin | api/src/takab_api/routers/users.py:296-345,437-438; web/src/features/tenants/useUsers.ts:26-53 | T-8.09 |
| A-109 | P2 | 🔷 MEJORA | Web · flota/tenants/edificio | 'VOLVER A vN' cambia los umbrales de disparo en producción con un solo clic | takab_superadmin, tenant_admin | web/src/features/tenants/RuleSetHistory.tsx:57-70; web/src/features/tenants/SyncFooter.tsx:130-137 | T-8.09 |
| A-110 | P2 | 🔷 MEJORA | Web · flota/tenants/edificio | Conceder visibilidad a TODOS los clientes (incluidos datos en vivo) sin confirmación; el formulario se vacía aunque falle | takab_superadmin | web/src/features/tenants/VisibilityCard.tsx:33-46,76-84,93; web/src/features/tenants/useVisibility.ts:10-15 | T-8.09 |
| A-111 | P2 | 🔴 DEFECTO | Web · flota/tenants/edificio | Si el rango del historial está vacío desaparecen los botones de rango y no se puede cambiar a otro | todos los que ven /building | web/src/features/building/BuildingPage.tsx:156-173; web/src/features/telemetry/HistoryChart.tsx:54-63; web/sr… | T-8.09 |
| A-112 | P2 | 🔴 DEFECTO | Web · flota/tenants/edificio | El historial y la cabecera del sitio pasan a 'DATOS RETENIDOS' a los 3 y 5 minutos aunque todo funcione | todos los que ven /building | web/src/features/telemetry/useSiteMetrics.ts:45-63; web/src/features/building/BuildingPage.tsx:43-44,52-59,84… | T-8.09 |
| A-113 | P2 | ⬜ FALTA | Web · flota/tenants/edificio | Sin interfaz para publicar el aviso de privacidad ni para gestionar solicitudes ARCO | takab_superadmin, tenant_admin | api/src/takab_api/auth/matrix.py:240,260; api/src/takab_api/routers/privacy.py:91-105,241,317,545,611,690 | T-8.19 |
| A-114 | P2 | ⬜ FALTA | Web · flota/tenants/edificio | Funciones de la API/matriz sin interfaz web: código de retiro, firmware, sensores, restaurar estación | takab_superadmin (1-3), takab_superadmin/tenant_admin (4-6) | api/src/takab_api/routers/tenants.py:177-200; api/src/takab_api/routers/rollouts.py; api/src/takab_api/router… | T-8.19 |
| A-115 | P2 | ⬜ FALTA | Web · flota/tenants/edificio | Specs de Playwright en web/e2e y qué cubre cada una | takab_superadmin, soc_operator, tenant_admin cubiertos; los… | web/e2e/helpers.ts:11-30,85-98; web/e2e/screens.spec.ts:74-140,428-660; web/e2e/smoke.spec.ts:23-70; web/e2e/… | T-8.06 |
| A-116 | P2 | 🔷 MEJORA | Móvil | Las sesiones de 30 días quedan mitigadas en los comandos, pero falta poder revocar un dispositivo perdido | todos los móviles; tenant_admin/takab_support para revocar | mobile/src/features/control/service.ts:37-80; mobile/src/features/control/ControlSheet.tsx:163-167; api/src/t… | T-8.04 |
| A-117 | P2 | ⬜ FALTA | Móvil | mobile-state no se guarda en disco: en arranque en frío sin red, inicio/crisis/panel quedan en error | todos los móviles | mobile/src/features/alert/useAlertState.ts:48-62; mobile/src/offline/useCachedQuery.ts:21-69; takab-docs/desi… | T-8.18 |
| A-118 | P2 | 🔴 DEFECTO | Móvil | Descargar el PDF del dictamen y guardar el perfil fallan en silencio | tácticos (dictamen); todos (perfil) | mobile/src/app/dictamen.tsx:72-88; api/src/takab_api/routers/_s3.py:19; mobile/src/features/account/AccountSc… | T-8.12 |
| A-119 | P2 | ⬜ FALTA | Móvil | El cierre de headcount va sin firma, y la «firma» del inspector en triage no existe en la app | brigadista, security_guard, building_admin (headcount); ins… | mobile/src/app/(brigadista)/lista.tsx:170-197; api/src/takab_api/routers/mobile_incident.py:270-305; api/src/… | T-8.18 |
| A-120 | P2 | ⬜ FALTA | Móvil | La marca de agua forense va sin GPS ni desfase NTP | brigadista, security_guard, inspector | mobile/src/app/camera.tsx:136-149; mobile/src/features/forensic/watermark.ts:45-55; takab-docs/RBAC-TAKAB.md:… | T-8.18 |
| A-121 | P2 | 🔷 MEJORA | Móvil | Estados con dato disponible que la app no muestra | todos | mobile/src/app/_layout.tsx:60-64; mobile/src/services/push.ts:116-160; api/src/takab_api/schemas/mobile.py:11… | T-8.18 |
| A-122 | P2 | 🔷 MEJORA | Móvil | Dónde añadir animación, hápticos y animación pasiva (propuesta concreta) | todos | mobile/src/ui/useReduceMotion.ts:8; mobile/src/ui/StateFrame.tsx:52-57; mobile/src/ui/StateFrame.tsx:86-92; m… | T-8.15 |
| A-123 | P2 | ⬜ FALTA | Sesiones por rol | Nuevo tftest que ancle la duración de sesión | n/a | infra/terraform/modules/identity/tests/mfa.tftest.hcl:168,184-190 | T-8.05 |
| A-124 | P2 | 🔷 MEJORA | Sesiones por rol | /me expone session_expires_at | todos | api/src/takab_api/schemas/me.py:104-130 | T-8.02 |
| A-125 | P2 | ⬜ FALTA | Sesiones por rol | Docs y specs que citan las duraciones actuales | n/a | takab-docs/specs/cognito-pool-v1.md:105,229; takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md:414-418,668-66… | T-8.05 |
| A-126 | P2 | 🟠 SOSPECHA | Sesiones por rol | Occupant: bajar de 90 a 30 días contradice la 'sesión de larga vida' | occupant | infra/terraform/modules/identity/main.tf:608-611,629-637; takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md:4… | T-8.05 |
| A-127 | P2 | ❔ NO MEDIDO | Sesiones por rol | Cambios de rol o alcance y bajas con sesiones largas | todos | takab-docs/PENDIENTES-MAURICIO.md:314-317; api/src/takab_api/users/directory.py:382-387 | T-8.02 |
| A-128 | P2 | ⬜ FALTA | RBAC y flujos | Acciones del superadmin sin ninguna superficie en la UI (solo API) | takab_superadmin, tenant_admin (aviso de privacidad/ARCO/pl… | web/src/features/console/useDemoMode.ts:47-55,72; web/src/features/scene/SceneStrip.tsx:51-61; api/src/takab_… | T-8.07 |
| A-129 | P2 | 🔷 MEJORA | RBAC y flujos | El administrador del cliente no puede descargar el PDF de dictamen ni el miniSEED de su propio edificio | tenant_admin, building_admin | api/src/takab_api/auth/matrix.py:407-434; web/src/features/triage/TriagePage.tsx:251-254; takab-docs/RBAC-TAK… | T-8.19 |
| A-130 | P2 | 🔴 DEFECTO | RBAC y flujos | useQuorumCommands da 403 al SOC, a gov y a soporte: el estado de la actuación por quórum no se ve | soc_operator, gov_operator, takab_support | api/src/takab_api/routers/commands.py:83-97,336-340; web/src/features/console/useQuorumCommands.ts:44-62; web… | T-8.08 |
| A-131 | P2 | 🔴 DEFECTO | RBAC y flujos | Leer ventanas de mantenimiento no se permite a gov, inspector ni building_admin, aunque el comentario y el documento dicen «cualquiera de consola» | gov_operator, inspector, building_admin | api/src/takab_api/routers/maintenance.py:110-116; takab-docs/RBAC-TAKAB.md:190-192; web/src/features/console/… | T-8.09 |
| A-132 | P2 | 🟠 SOSPECHA | RBAC y flujos | §3 dice que el formulario de triage móvil del inspector lleva «(firma)»; el móvil no firma | inspector | takab-docs/RBAC-TAKAB.md:328; api/src/takab_api/auth/matrix.py:448-450; api/src/takab_api/routers/dictamens.p… | T-8.19 |
| A-133 | P2 | 🔴 DEFECTO | RBAC y flujos | La web no comprueba la superficie: un inspector o building_admin con surface=mobile entra al shell y todo le da 403 | inspector, building_admin | web/src/app/RequireSession.tsx:32-37; api/src/takab_api/auth/deps.py:123-127; web/src/features/tenants/UsersC… | T-8.07 |
| A-134 | P2 | 🟠 SOSPECHA | RBAC y flujos | Las escrituras no aplican site_scope: roles «de su sitio» pueden actuar en cualquier sitio del tenant vía API | building_admin, inspector, soc_operator | api/src/takab_api/routers/classification.py:130-155; api/src/takab_api/routers/incidents_ack.py:57-66; api/sr… | T-8.19 |
| A-135 | P2 | 🔷 MEJORA | RBAC y flujos | building_admin aterriza en MONITOREO; su superficie principal («Dash Edificio Total») no tiene pestaña | building_admin | web/src/app/landing.ts:3-7; web/src/shell/navItems.ts:9-11; takab-docs/RBAC-TAKAB.md:62 | T-8.07 |
| A-136 | P2 | ❔ NO MEDIDO | RBAC y flujos | MATRIZ rol×flujo · security_guard | security_guard | api/src/takab_api/auth/matrix.py:495-504; api/src/takab_api/routers/ws.py:48-49; infra/scripts/seed_mobile_us… | T-8.01 |
| A-137 | P2 | ⬜ FALTA | RBAC y flujos | El ocupante no tiene UI para ejercer su propio ARCO (POST /privacy/erasure) | occupant (y cualquier titular) | api/src/takab_api/routers/privacy.py:391,508; mobile/src/services/privacy.ts:70-141; takab-docs/RBAC-TAKAB.md… | T-8.19 |
| A-138 | P2 | 🟠 SOSPECHA | RBAC y flujos | Todos los usuarios web sembrados tienen site_scope '*': no se ve el alcance «su sitio» de building_admin e inspector | building_admin, inspector | infra/scripts/seed_console_users.sh:62,73; takab-docs/RBAC-TAKAB.md:61-62,406-411 | T-8.13 |
| A-139 | P2 | 🟠 SOSPECHA | PDF | El resumen ejecutivo nunca dice REPRODUCCIÓN y afirma la medición del sensor | quien lea el ejecutivo (hoy solo por API) | api/tests/dictamen/test_avisos_impresos.py:245-251; api/src/takab_api/dictamen/pdf.py:1763-1782; api/src/taka… | T-8.12 |
| A-140 | P2 | 🔴 DEFECTO | PDF | El ejecutivo imprime los títulos como «. QUÉ PASÓ», «. QUÉ SIGNIFICA», … | quien lea el ejecutivo | api/src/takab_api/documentos/membrete.py:400-405; api/src/takab_api/dictamen/pdf.py:1763,1779,1785,1789,1818;… | T-8.12 |
| A-141 | P2 | 🔴 DEFECTO | PDF | PDF del móvil: caché eterna, errores silenciosos y URL presignada que caduca | inspector, building_admin, brigadista, security_guard | mobile/src/app/dictamen.tsx:21-38,51-95; mobile/src/features/dictamen/DictamenCertificate.tsx:35-58; api/src/… | T-8.12 |
| A-142 | P2 | 🔴 DEFECTO | PDF | Reporte de simulacro: la clave S3 FIJA se sobrescribe y deja inverificables las filas de evidencia anteriores | takab_superadmin, tenant_admin | api/src/takab_api/routers/drills.py:787-880 (807, 854-855); web/src/features/console/DrillHistory.tsx:127-138… | T-8.12 |
| A-143 | P2 | 🟠 SOSPECHA | PDF | Reporte de simulacro: con nombres largos las líneas por sitio se salen del margen derecho | takab_superadmin, tenant_admin | api/src/takab_api/drill_report.py:292-337; api/tests/documentos/test_geometria.py:185-207 | T-8.12 |
| A-144 | P2 | 🔴 DEFECTO | PDF | Se cuelan valores crudos en inglés en un papel en castellano | todos los que reciben el PDF | api/src/takab_api/dictamen/pdf.py:189,1545-1562,1684,1498-1504; db/schema.sql:296,3522; mobile/src/features/d… | T-8.12 |
| A-145 | P2 | 🔷 MEJORA | PDF | «FIRMÓ» imprime el UUID de Cognito del inspector | inspector (firmante) | api/src/takab_api/dictamen/pdf.py:1727-1741; api/src/takab_api/dictamen/builder.py:358; db/schema.sql:1785-17… | T-8.12 |
| A-146 | P2 | 🟠 SOSPECHA | PDF | Custodia del CCTV: el rótulo «<papel> · AAAA-MM-DD HH:MM:SS UTC» puede no caber en la celda de 52 mm | todos los que reciben el PDF | api/src/takab_api/documentos/membrete.py:412-425; api/src/takab_api/dictamen/pdf.py:1679-1690; api/src/takab_… | T-8.12 |
| A-147 | P2 | ⬜ FALTA | PDF | No hay forma de pedir el resumen ejecutivo desde la consola | takab_superadmin, inspector | web/src/features/triage/useIncidentDetail.ts:263-285; api/src/takab_api/routers/reports.py:46-56 | T-8.12 |
| A-148 | P2 | ⬜ FALTA | PDF | No se puede volver a descargar un dictamen ya emitido; gov_operator no tiene ningún botón para el PDF | gov_operator, inspector, takab_superadmin | web/src/features/triage/TriageDetail.tsx:392-400,445-451; web/src/features/triage/model.ts:242-246; api/src/t… | T-8.12 |
| A-149 | P2 | 🔴 DEFECTO | PDF | La meta F6 exige «Narrativa: openrouter» en el pdftotext y el papel no imprime esa cadena | n/a | takab-docs/PLAN-PROTOTIPO-FUNCIONAL.md:342-344; api/src/takab_api/dictamen/pdf.py:1692-1706; api/src/takab_ap… | T-8.12 |
| A-150 | P2 | 🔷 MEJORA | PDF | Todas las fechas van en UTC; no hay hora local de México | todos | api/src/takab_api/dictamen/model.py:74; api/src/takab_api/drill_report.py:269-270; api/src/takab_api/document… | T-8.12 |
| A-151 | P2 | ⬜ FALTA | PDF | El informe del evento y el reporte de simulacro no traen el pase de lista (headcount) ni la participación | building_admin, tenant_admin, gov_operator | api/src/takab_api/dictamen/pdf.py:1664-1669; api/src/takab_api/drill_report.py:34-38; takab-docs/runbooks/RUN… | T-8.12 |
| A-152 | P2 | 🔷 MEJORA | PDF | Guardas existentes y sus huecos | n/a | api/tests/dictamen/; api/tests/documentos/; api/tests/narrative/; api/tests/api/test_reports.py:93-400; api/t… | T-8.12 |
| A-153 | P2 | 🔴 DEFECTO | Estatus visibles | SOH de DetailPanel sin edad propia y oculto cuando no hay features | roles con /console: superadmin, support, tenant_admin, soc_… | web/src/features/console/DetailPanel.tsx:143-151,188-191,324-385; web/src/features/building/BuildingPage.tsx:… | T-8.14 |
| A-154 | P2 | ⬜ FALTA | Estatus visibles | Nivel de alerta vigente por sitio (rule_evaluations) no se ve en la consola | roles de consola | db/schema.sql:576-592; api/src/takab_api/ingest/handlers.py:1030-1093; api/src/takab_api/ws/hub.py:103,144,52… | T-8.14 |
| A-155 | P2 | ⬜ FALTA | Estatus visibles | Temperatura CPU, batería %, minutos UPS y días de certificado no se pintan en la web | roles de consola | api/src/takab_api/ws/protocol.py:134-142; api/src/takab_api/ws/hub.py:136-137; web/src/features/building/Buil… | T-8.14 |
| A-156 | P2 | ⬜ FALTA | Estatus visibles | Rollouts canary y órdenes update/rollback sin UI ni listado | takab_superadmin (deploy_firmware); lectura: roles /fleet | db/schema.sql:1695-1720; api/src/takab_api/routers/rollouts.py:1-40,201,306-316,382; api/src/takab_api/router… | T-8.14 |
| A-157 | P2 | ⬜ FALTA | Estatus visibles | Alarmas de CloudWatch y su cadena de acuse sin pantalla | takab_superadmin, takab_support | db/schema.sql:3194-3220; api/src/takab_api/routers/ops_alerts.py:33-36,424-440; infra/terraform/modules/obser… | T-8.14 |
| A-158 | P2 | ⬜ FALTA | Estatus visibles | Costo IA (ai_spend) sin endpoint, y el reporte no dice si usó la IA | takab_superadmin, takab_support, tenant_admin; quienes expo… | db/schema.sql:1325-1343; api/src/takab_api/narrative/quota.py:116-185; api/src/takab_api/routers/reports.py:1… | T-8.14 |
| A-159 | P2 | ⬜ FALTA | Estatus visibles | El panel LAN no muestra la versión de firmware (disco / proceso) | técnico en sitio / building_admin con acceso LAN | edge/takab_edge/local_api/__init__.py:1512-1593; edge/takab_edge/local_api/index.html:1687 | T-8.14 |
| A-160 | P2 | 🔷 MEJORA | Estatus visibles | Inspector y building_admin ven «SIN LATIDO» hasta el siguiente latido | inspector, building_admin | api/src/takab_api/auth/matrix.py:79-80; web/src/features/console/useSiteSoh.ts:12-27; web/src/features/buildi… | T-8.14 |
| A-161 | P2 | 🔷 MEJORA | Estatus visibles | El SOC no ve el conteo agregado del pase de lista | soc_operator, tenant_admin, gov_operator | api/src/takab_api/auth/matrix.py:466-497; takab-docs/RBAC-TAKAB.md:329; api/src/takab_api/routers/mobile_inci… | T-8.14 |
| A-162 | P2 | ❔ NO MEDIDO | Estatus visibles | Comportamiento en ejecución no comprobado | n/a | shared/schemas/health_snapshot.schema.json; api/src/takab_api/ingest/handlers.py:977-1013 | T-8.14 |
| A-163 | P2 | 🔴 DEFECTO | Animaciones | «EJECUTADO» en verde antes de que responda el servidor | soc_operator, gov_operator, tenant_admin, building_admin, i… | web/src/components/ConfirmButton.tsx:67-72,76-81,109; web/src/features/building/SirenTestPanel.tsx:63-76; web… | T-8.07 |
| A-164 | P2 | 🟠 SOSPECHA | Animaciones | La carcasa de la alerta sigue respirando/parpadeando cuando la fuente está retenida | todos los que ven alertas (consola, occupant, táctico, kios… | web/src/features/console/ConsolePage.tsx:183-189,295-300; web/src/features/console/AlertBanner.tsx:76-79; web… | T-8.15 |
| A-165 | P2 | 🟠 SOSPECHA | Animaciones | El faro pulsa también con el incidente en revisión (in_review), a diferencia de la tarjeta | roles de consola web | api/src/takab_api/queries/telemetry.py:170-185; api/src/takab_api/routers/telemetry.py:142-182; web/src/featu… | T-8.09 |
| A-166 | P2 | 🔷 MEJORA | Animaciones | No hay háptica: añadir expo-haptics en las confirmaciones críticas | occupant, brigadista, security_guard | mobile/package.json:11-46; mobile/src/features/panic/PanicButton.tsx:79-85; mobile/src/features/control/Contr… | T-8.15 |
| A-167 | P2 | 🔷 MEJORA | Animaciones | La toma de crisis hereda la transición nativa por defecto del Stack | occupant, táctico | mobile/src/app/_layout.tsx:71-81; mobile/src/features/alert/CrisisWatcher.tsx:62,68,78; takab-docs/design/PLA… | T-8.15 |
| A-168 | P2 | 🔷 MEJORA | Animaciones | No hay gesto de refresco: añadir RefreshControl en inicio, panel, lista, sync y directorio | occupant, táctico | mobile/src (grep 'RefreshControl' vacío); mobile/src/app/(brigadista)/sync.tsx:83; mobile/src/app/(brigadista… | T-8.15 |
| A-169 | P2 | 🔷 MEJORA | Animaciones | Tinte único de fila cuando llega o cambia un check-in por WS | brigadista, security_guard, building_admin | mobile/src/app/(brigadista)/lista.tsx:1-4,65; web/src/styles/soc.css:1756-1794 | T-8.15 |
| A-170 | P2 | 🔷 MEJORA | Animaciones | Entrada/salida del modal: hoy aparece de golpe | soc_operator, gov_operator (reubicar epicentro), roles de c… | web/src/components/Modal.tsx:30-50; web/src/styles/soc.css:1256-1279 | T-8.15 |
| A-171 | P2 | 🔷 MEJORA | Animaciones | Popover del operador y desplegables abren sin transición; chevrón sólo en 2 de 5 | todos los de consola | web/src/shell/OperatorMenu.tsx:61-77; web/src/features/console/DrillHistory.tsx:122-127; web/src/features/ten… | T-8.15 |
| A-172 | P2 | 🔷 MEJORA | Animaciones | Sólo existe 1 :active en todas las hojas | todos los de consola | web/src/styles/soc.css:855-876,202-219 (grep ':active' = 1 en web/src/styles) | T-8.15 |
| A-173 | P2 | 🔷 MEJORA | Animaciones | Tinte único al cambiar un KPI; nunca contar hacia arriba | soc_operator, gov_operator, tenant_admin | web/src/features/console/KpiStrip.tsx:42-44; web/src/styles/soc.css:1775-1794,1832-1839 | T-8.15 |
| A-174 | P2 | 🔷 MEJORA | Animaciones | No existe un canal de confirmación de acciones: añadir región role=status animada | todos los de consola | web/src (grep 'toast\|sonner' vacío); web/src/features/console/ConsolePage.tsx:192-201 | T-8.15 |
| A-175 | P2 | 🔷 MEJORA | Animaciones | El rAF de 20 fps corre siempre y repinta el mapa sin nada que animar | roles de consola (videowall) | web/src/features/console/MapPanel.tsx:1056-1113 | T-8.15 |
| A-176 | P2 | 🔷 MEJORA | Animaciones | Ondas y rosa se redibujan a 60 fps con datos que llegan a 1 Hz | operador local del gabinete | edge/takab_edge/local_api/index.html:2446-2452,2505-2516,3338-3369 | T-8.15 |
| A-177 | P2 | ❔ NO MEDIDO | Animaciones | FPS y coste de CPU/GPU de las animaciones en el Pixel, el Pi 4 y el videowall | n/a | web/src/features/console/MapPanel.tsx:1056-1113; edge/takab_edge/local_api/index.html:3338-3369; mobile/src/f… | T-8.15 |
| A-178 | P2 | 🟠 SOSPECHA | Funciones básicas | Feed externo CIRES/SSN y catálogo SSN | soc_operator, inspector, gov_operator | api/src/takab_api/routers/catalog.py:30; api/src/takab_api/catalogo/fdsn.py; takab-docs/TASKS.md:4283,5013,11… | T-8.19 |
| A-179 | P2 | ⬜ FALTA | Funciones básicas | Relés sirena/estrobo reales; gas, ascensores y puertas sin cablear; BACnet sin driver real | building_admin, tenant_admin, cliente corporativo/hospital | edge/takab_edge/actuators/__init__.py:12-13,183-192; edge/pyproject.toml:24-26; takab-docs/INFORME-V1-COMERCI… | T-8.19 |
| A-180 | P2 | ⬜ FALTA | Funciones básicas | Voceo/audio: no hay grabaciones y audio está deshabilitado | occupant, building_admin | edge/takab_edge/config/settings.py:521; takab-docs/TASKS.md:10454-10461 (T-2.95); takab-docs/PLAN-REVISION-PR… | T-8.19 |
| A-181 | P2 | ⬜ FALTA | Funciones básicas | No hay reporte periódico (mensual) por cliente o sitio | tenant_admin, building_admin, gov_operator, takab_superadmin | api/src/takab_api/routers/classification.py:238; api/src/takab_api/routers/fleet.py:148; api/src/takab_api/na… | T-8.19 |
| A-182 | P2 | ⬜ FALTA | Funciones básicas | Padrón de ocupantes: no se puede listar ni revocar quién está vinculado a un edificio | building_admin, tenant_admin | api/src/takab_api/queries/mobile.py:111-117,380-388; api/src/takab_api/routers/mobile_me.py:165-210 | T-8.19 |
| A-183 | P2 | 🟠 SOSPECHA | Funciones básicas | QR del edificio: la historia de usuario lo pide y solo existe el código tecleado | occupant, building_admin | takab-docs/USER-STORIES.md:141-145; takab-docs/RBAC-TAKAB.md:443-445,479; web/src/features/fleet/EnrollmentCo… | T-8.19 |
| A-184 | P2 | ⬜ FALTA | Funciones básicas | Planos y rutas de evacuación: la API de subida existe y ninguna pantalla la usa | building_admin, tenant_admin, occupant (afectado) | api/src/takab_api/routers/mobile_site.py:381,394-412; mobile/src/app/(occupant)/rutas.tsx | T-8.19 |
| A-185 | P2 | 🔷 MEJORA | Funciones básicas | El directorio de emergencia no tiene números externos (911, Protección Civil) | occupant, brigadista | mobile/src/app/(occupant)/directorio.tsx:1-35; api/src/takab_api/queries/mobile.py:380-388 | T-8.19 |
| A-186 | P2 | ⬜ FALTA | Funciones básicas | No hay «prueba de canal» (enviar un aviso de prueba al webhook, correo o teléfono configurado) | tenant_admin, takab_superadmin | takab-docs/BLUEPRINT-TECNICO-TAKAB.md:440; web/src/features/tenants/NotificationChannels.tsx:1-40 | T-8.19 |
| A-187 | P2 | 🟠 SOSPECHA | Funciones básicas | La actualización remota con canary y rollback existe en la API y no tiene pantalla | takab_support, takab_superadmin | api/src/takab_api/routers/rollouts.py:202,317,383; api/src/takab_api/routers/updates.py:126,174; web/src/feat… | T-8.19 |
| A-188 | P2 | ⬜ FALTA | Funciones básicas | Marco normativo citable y aviso de privacidad revisado | tenant_admin, gov_operator, cliente | takab-docs/TASKS.md:10464-10474,12588; takab-docs/INFORME-V1-COMERCIAL.md:134-135 | T-8.19 |
| A-189 | P2 | 🟠 SOSPECHA | Funciones básicas | Prosa asistida encendida; shadow-mode, priorización y evaluación sin hacer | soc_operator, inspector | api/src/takab_api/narrative/; takab-docs/TASKS.md:10578-10598,15223,15312; takab-docs/PENDIENTES-MAURICIO.md:… | T-8.19 |
| A-190 | P2 | ⬜ FALTA | Funciones básicas | No hay disponibilidad (%) ni página de estado visible para el cliente | tenant_admin, building_admin, takab_support | api/src/takab_api/routers/fleet.py:148; web/src/features/fleet/useFleetMutations.ts:17 | T-8.19 |
| A-191 | P2 | ⬜ FALTA | Funciones básicas | Un solo entorno Terraform (dev) hace de demo y de «producción» | takab_superadmin | infra/terraform/envs/ (solo dev); takab-docs/DECISIONES-MAURICIO.md:1534-1560 (D-31) | T-8.19 |
| A-192 | P2 | 🟠 SOSPECHA | Funciones básicas | Landing nueva lista, sin publicar; sin formulario de demo ni canal de contacto | comercial/prospecto | landing/src/pages/index.astro; takab-docs/TASKS.md:10541,10550; takab-docs/PENDIENTES-MAURICIO.md:1066 | T-8.19 |
| A-193 | P2 | ⬜ FALTA | Funciones básicas | Fichas abiertas que no esperan a nadie | n/a | takab-docs/TASKS.md:4283,5063,5859,6318,10578-10624,11277,11320-11357 | T-8.19 |
| A-194 | P2 | ⬜ FALTA | Edge/nube/presentación | No hay watchdog de software, aunque el docstring y la unidad dicen que lo hay | n/a | edge/takab_edge/supervisor.py:1; edge/systemd/takab-edge.service:3; edge/systemd/takab-gpio.service:106-109; … | T-8.17 |
| A-195 | P2 | 🔷 MEJORA | Edge/nube/presentación | El remojo del canary no comprueba que SeedLink ni la nube funcionen | n/a | deploy/edge/canary.sh:25-43; deploy/edge/canary.sh:453-476; edge/takab_edge/health/__init__.py:52 | T-8.17 |
| A-196 | P2 | 🔷 MEJORA | Edge/nube/presentación | Al latido le faltan señales que ya costaron incidentes: memoria, subtensión, uptime, cola MQTT, reconexiones, command_enabled | takab_superadmin, takab_support, soc_operator | edge/takab_edge/contracts.py:447-557; edge/takab_edge/local_api/sismografo.py:20-40; shared/schemas/health_sn… | T-8.17 |
| A-197 | P2 | 🟠 SOSPECHA | Edge/nube/presentación | Reloj: el Pi 4 no tiene RTC, y takab-gpio se ordena After=time-sync.target | todos (evidencia con sello de tiempo) | edge/takab_edge/reloj.py:1-15; edge/systemd/takab-gpio.service:7; edge/systemd/takab-edge.service:29 | T-8.17 |
| A-198 | P2 | ⬜ FALTA | Edge/nube/presentación | No hay métrica de memoria del EC2 compartido ni límites de memoria por servicio | todos | deploy/cloud/docker-compose.yml:1-7; deploy/cloud/docker-compose.yml:23-29 | T-8.16 |
| A-199 | P2 | ⬜ FALTA | Edge/nube/presentación | No hay comprobación externa de disponibilidad de la consola ni de la API | todos | infra/terraform/modules/observability/main.tf:188-212; deploy/cloud/deploy.sh:546-558 | T-8.16 |
| A-200 | P2 | 🔷 MEJORA | Edge/nube/presentación | Los logs solo viven en el host (json-file de 10 MB × 3 por servicio) | takab_superadmin, takab_support | deploy/cloud/docker-compose.yml:27-29; deploy/cloud/docker-compose.yml:134-136; infra/terraform/modules/iot-c… | T-8.16 |
| A-201 | P2 | 🔷 MEJORA | Edge/nube/presentación | Seguridad del borde HTTP: sin CSP y sin límite de peticiones genérico en una consola pública | todos | deploy/cloud/Caddyfile; api/src/takab_api/routers/reports.py:217-234; takab-docs/DECISIONES-MAURICIO.md:80 | T-8.16 |
| A-202 | P2 | 🔷 MEJORA | Edge/nube/presentación | Cadena de suministro: el plugin de docker compose se descarga de GitHub sin verificar su checksum | n/a | deploy/cloud/deploy.sh:322-337 | T-8.16 |
| A-203 | P2 | ❔ NO MEDIDO | Edge/nube/presentación | Rendimiento de los endpoints de sondeo móvil y detalles baratos | occupant, brigadista (en crisis) | api/src/takab_api/routers/mobile_site.py:194-253; api/src/takab_api/routers/reports.py:67; api/src/takab_api/… | T-8.16 |
| A-204 | P2 | 🔴 DEFECTO | Edge/nube/presentación | guion.sh convierte «no pude preguntar a la base» en veredicto, el mismo defecto que b804039 corrigió en los otros instrumentos | n/a (presentador) | deploy/demo/guion.sh:124; deploy/demo/guion.sh:248-256; deploy/demo/guion.sh:339; deploy/demo/guion.sh:344-35… | T-8.13 |
| A-205 | P2 | 🔷 MEJORA | Edge/nube/presentación | Al preflight le faltan comprobaciones de cosas que se ven mal delante del cliente | n/a (presentador) | deploy/demo/guion.sh:258-276; takab-docs/runbooks/GUIA-DEMOSTRACION-POR-ROLES.md:54-79; takab-docs/PLAN-REVIS… | T-8.13 |
| A-206 | P2 | 🟠 SOSPECHA | Edge/nube/presentación | El simulacro aparece como «✅ se enseña» pero no está guionizado y depende de command_enabled, que no se puede ver | soc_operator, tenant_admin, building_admin (programan o lan… | takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:75; takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:163-166… | T-8.13 |
| A-207 | P2 | 🔷 MEJORA | Edge/nube/presentación | Datos que en pantalla se ven viejos o vacíos si no se preparan | inspector, soc_operator | takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:79-117; takab-docs/runbooks/GUIA-DEMOSTRACION-POR-ROLES.md:5… | T-8.13 |
| A-208 | P2 | 🟠 SOSPECHA | Edge/nube/presentación | El PDF del acto 4 puede congelar unos segundos la consola y el teléfono | inspector, occupant, brigadista | api/src/takab_api/routers/reports.py:130-136; deploy/cloud/docker-compose.yml:41-47 | T-8.12 |
| A-209 | P2 | 🔷 MEJORA | Edge/nube/presentación | Límites de canales que hay que decir antes de que el cliente pida recibirlo en su propio teléfono | occupant, brigadista, tenant_admin | takab-docs/runbooks/RUNBOOK-demo-cliente.md:79; takab-docs/runbooks/RUNBOOK-demo-cliente.md:114-121; takab-do… | T-8.13 |
| A-210 | P2 | ❔ NO MEDIDO | Edge/nube/presentación | Reflejo de 0,22 ms frente a 4,96 ms: el código del reflejo no cambió entre ensayos; hipótesis verificable | n/a | takab-docs/runbooks/RUNBOOK-demo-cliente.md:506-510; takab-docs/TASKS.md:15390-15393; edge/systemd/takab-edge… | T-8.13 |
| A-211 | P2 | 🔷 MEJORA | Edge/nube/presentación | Riesgos físicos del gabinete el día de la demo: eth0 que se cae, sin RTC y DHCP | n/a (presentador) | deploy/demo/guion.sh:51-55; takab-docs/runbooks/RUNBOOK-demo-cliente.md:154-167; edge/takab_edge/reloj.py:1-1… | T-8.13 |
| A-212 | P2 | ✅ OK | Sesiones por rol | Clients compartidos: la diferencia por rol depende al 100 % de la API | security_guard, building_admin, roles web | infra/terraform/modules/identity/main.tf:142,647; api/src/takab_api/auth/deps.py:86; api/src/takab_api/router… | T-8.02 |
| A-213 | P2 | ✅ OK | Sesiones por rol | Tests que se romperán con el cambio | n/a | api/tests/auth_utils.py:97-120; api/tests/ws/test_ws_auth.py:22-66; api/tests/test_docs_consistency.py:2079-2… | T-8.02 |
| A-214 | P3 | 🔷 MEJORA | Web · MONITOREO/EVALUACIÓN | SIN ACCESO no ofrece salida | los 7 roles web al abrir un enlace directo no permitido (p.… | web/src/pages/NoAccessPage.tsx:8-20; web/src/app/RouteGuard.tsx:17-19 | T-8.07 |
| A-215 | P3 | 🔷 MEJORA | Web · MONITOREO/EVALUACIÓN | Pantalla de roles solo-móvil | brigadista, security_guard, occupant | web/src/pages/MobileOnlyScreen.tsx:6-22; web/src/app/RequireSession.tsx:35-37 | T-8.07 |
| A-216 | P3 | 🔷 MEJORA | Web · MONITOREO/EVALUACIÓN | Select de orden, filas clicables y botones de REUBICAR y SOLICITAR DICTAMEN | reubicar/solicitar: takab_superadmin, tenant_admin, soc_ope… | web/src/features/console/IncidentTable.tsx:176-196,248-253,321-347; web/src/features/console/ConsolePage.tsx:… | T-8.07 |
| A-217 | P3 | 🔷 MEJORA | Web · MONITOREO/EVALUACIÓN | Modal de reubicar epicentro | takab_superadmin, tenant_admin, soc_operator | web/src/features/console/EpicenterModal.tsx:23-145; web/src/features/console/useEpicenter.ts; api/src/takab_a… | T-8.07 |
| A-218 | P3 | 🔷 MEJORA | Web · MONITOREO/EVALUACIÓN | Panel de detalle del sitio: tarjetas, enlaces y textos de estado vacío | los 7 roles web | web/src/features/console/DetailPanel.tsx:207-229,478-531,543-564,566-592; web/src/features/fleet/useFleet.ts:… | T-8.07 |
| A-219 | P3 | 🔷 MEJORA | Web · MONITOREO/EVALUACIÓN | Franja de escena en las seis rutas | los 7 roles web | web/src/features/scene/SceneStrip.tsx:39-122; web/src/features/scene/scene.ts; web/src/features/scene/AlertLi… | T-8.07 |
| A-220 | P3 | 🔷 MEJORA | Web · MONITOREO/EVALUACIÓN | Filtros e historial de EVALUACIÓN | los 7 roles web | web/src/features/triage/TriagePage.tsx:45-236; web/src/features/triage/useTriage.ts:52-62,128-145; web/src/fe… | T-8.08 |
| A-221 | P3 | 🔷 MEJORA | Web · MONITOREO/EVALUACIÓN | Movimiento que ya existe y huecos donde añadir animación pasiva | n/a | web/src/features/console/IncidentTable.tsx:157-167,250,267-271; web/src/features/console/DetailPanel.tsx:318,… | T-8.15 |
| A-222 | P3 | 🔷 MEJORA | Web · flota/tenants/edificio | Controles deshabilitados sin title y acciones irreversibles sin confirmación en códigos de alta | takab_superadmin, tenant_admin | web/src/features/fleet/EnrollmentCodes.tsx:182-183,224-230; web/src/features/fleet/FleetAdmin.tsx:309-315; we… | T-8.09 |
| A-223 | P3 | 🟠 SOSPECHA | Web · flota/tenants/edificio | Un gabinete retirado sigue ofreciendo VENTANA y AUTODIAGNÓSTICO; y se puede restaurar aunque su estación esté retirada | takab_superadmin, tenant_admin | web/src/features/fleet/SiteCard.tsx:75,190-200,314; api/src/takab_api/routers/fleet.py:555-575; web/src/featu… | T-8.09 |
| A-224 | P3 | 🔴 DEFECTO | Web · flota/tenants/edificio | Publicar o volver atrás invalida la clave ['config-state'], que no existe | takab_superadmin, tenant_admin | web/src/features/tenants/useRuleSetPublish.ts:78; web/src/features/tenants/useRuleSetRollback.ts:54; web/src/… | T-8.09 |
| A-225 | P3 | 🔴 DEFECTO | Web · flota/tenants/edificio | El alta de cliente muestra 'GET /tenants falló (409)' en un POST y sin detalle | takab_superadmin | web/src/features/tenants/useTenants.ts:29-34,223-231,247-260 | T-8.09 |
| A-226 | P3 | 🟠 SOSPECHA | Web · flota/tenants/edificio | takab_support provoca 403 en /notify/channels en cada carga de /tenants | takab_support | web/src/features/tenants/useNotifyChannels.ts:27-45; web/src/features/tenants/TenantsPage.tsx:229; api/src/ta… | T-8.09 |
| A-227 | P3 | 🔷 MEJORA | Web · flota/tenants/edificio | Comentarios desactualizados y sliders sin motivo al estar deshabilitados | takab_support, tenant_admin | web/src/features/tenants/TenantsPage.tsx:111-121,614-619; web/src/features/tenants/ThresholdSlider.tsx:45,84-… | T-8.09 |
| A-228 | P3 | 🔷 MEJORA | Web · flota/tenants/edificio | Incidentes del sitio sin enlace a Triage ni paginación; no hay autodiagnóstico en la ficha | building_admin, soc_operator, inspector | web/src/features/building/BuildingPage.tsx:221-257; web/src/features/building/useSiteIncidents.ts:28; api/src… | T-8.09 |
| A-229 | P3 | 🔷 MEJORA | Web · flota/tenants/edificio | Actor y Verbo son filtros EXACTOS pero no lo dicen; no hay exportación; el refresco recarga todas las páginas | takab_superadmin, takab_support, tenant_admin, gov_operator | web/src/features/audit/AuditPage.tsx:88-92,151-158; web/src/features/audit/useAudit.ts:29-38,88-102; api/src/… | T-8.09 |
| A-230 | P3 | 🟠 SOSPECHA | Web · flota/tenants/edificio | Con `make dev` (el del README) no se monta /dev/token, y occupant da 503 en local | occupant (y cualquier recorrido con make dev) | README.md:40-43; api/src/takab_api/settings.py:215,251-255; api/src/takab_api/routers/dev_token.py:64-67; api… | T-8.06 |
| A-231 | P3 | 🔷 MEJORA | Web · flota/tenants/edificio | Dónde añadir movimiento en estas pantallas, respetando T-6.10 ('el movimiento solo confirma') | todos | web/src/styles/soc.css:300-302,1256-1270,1776-1790,1838; web/e2e/motion.spec.ts:104-150; web/src/features/fle… | T-8.15 |
| A-232 | P3 | 🔴 DEFECTO | Móvil | Error sin «REINTENTAR» en 10 de las 15 pantallas con StateFrame | todos | mobile/src/app/checkin.tsx:124; mobile/src/app/crisis.tsx:105; mobile/src/app/(occupant)/inicio.tsx:38-44; mo… | T-8.18 |
| A-233 | P3 | 🔴 DEFECTO | Móvil | Deslizar para confirmar: sin guarda de 'busy' y la perilla no vuelve tras un error | brigadista, security_guard, inspector, building_admin | mobile/src/features/control/ControlSheet.tsx:46-69; mobile/src/app/(brigadista)/panel.tsx:180-195 | T-8.18 |
| A-234 | P3 | 🔷 MEJORA | Móvil | Texto técnico interno visible para el cliente | todos | mobile/src/features/panel/PanelView.tsx:126; mobile/src/features/account/AccountView.tsx:108-117; mobile/src/… | T-8.11 |
| A-235 | P3 | ⬜ FALTA | Móvil | El TOTP opcional del ocupante sigue siendo un placeholder (declara su tarea, T-2.14) | occupant | mobile/src/features/account/AccountView.tsx:108-117; takab-docs/RBAC-TAKAB.md:366-371 | T-8.18 |
| A-236 | P3 | 🟠 SOSPECHA | RBAC y flujos | §4.2 dice que los «superiores TAKAB» silencian; la matriz no da siren_silence al superadmin | takab_superadmin | takab-docs/RBAC-TAKAB.md:354; api/src/takab_api/auth/matrix.py:381-384; api/src/takab_api/routers/commands.py… | T-8.19 |
| A-237 | P3 | 🟠 SOSPECHA | RBAC y flujos | /tenants pide /notify/channels sin edit_thresholds: 403 silencioso para soporte | takab_support | web/src/features/tenants/TenantsPage.tsx:229,606-612; web/src/features/tenants/useNotifyChannels.ts:27-38; ap… | T-8.19 |
| A-238 | P3 | 🟠 SOSPECHA | RBAC y flujos | classify_incident y demo_mode_on/off no aparecen en RBAC-TAKAB.md | tenant_admin, building_admin, soc_operator, takab_superadmin | api/src/takab_api/auth/matrix.py:107-118,363-365,408-410,439,469; takab-docs/RBAC-TAKAB.md:58,62,67-112; taka… | T-8.19 |
| A-239 | P3 | 🔷 MEJORA | RBAC y flujos | El inspector aterriza en MONITOREO, en lectura, en vez de en EVALUACIÓN | inspector | web/src/app/landing.ts:5-7; api/src/takab_api/auth/matrix.py:57-60,79 | T-8.07 |
| A-240 | P3 | 🟠 SOSPECHA | RBAC y flujos | §7 sigue poniendo a building_admin en /fleet (divergencia conocida y abierta) | building_admin | takab-docs/RBAC-TAKAB.md:493; api/src/takab_api/auth/matrix.py:16-18,80 | T-8.19 |
| A-241 | P3 | ⬜ FALTA | RBAC y flujos | La activación de TOTP opcional del ocupante es un marcador de posición | occupant | mobile/src/features/account/AccountView.tsx:1-4,109-115; mobile/src/features/account/AccountScreen.tsx:3-4; t… | T-8.19 |
| A-242 | P3 | 🟠 SOSPECHA | RBAC y flujos | Quedan listas de roles escritas a mano en routers, pese a que matrix.py dice que «ningún router vuelve a listar roles a mano» | takab_superadmin, takab_support, brigadista, security_guard | api/src/takab_api/auth/matrix.py:41-45; api/src/takab_api/routers/demo_mode.py:135; api/src/takab_api/routers… | T-8.19 |
| A-243 | P3 | ⬜ FALTA | PDF | No hay PDF ni exportación de compliance o auditoría; web y edge no generan PDF | tenant_admin, gov_operator, takab_support (lectores de audi… | api/src/takab_api/dictamen/pdf.py:1709-1724,1818-1823; api/src/takab_api/compliance.py:1-60; api/src/takab_ap… | T-8.19 |
| A-244 | P3 | 🔴 DEFECTO | PDF | El error del reporte de simulacro dice «LA PESTAÑA QUE SE ABRIÓ SE CERRÓ SOLA», y ya no se cierra | takab_superadmin, tenant_admin, inspector | web/src/features/console/DrillHistory.tsx:174-178; web/src/lib/download.ts:96-107; web/src/features/triage/us… | T-8.12 |
| A-245 | P3 | 🔷 MEJORA | PDF | El filete del recuadro de ausencia (callout) mide 8 mm fijos, sea cual sea el alto del texto | todos | api/src/takab_api/documentos/membrete.py:430-445 | T-8.12 |
| A-246 | P3 | 🔴 DEFECTO | PDF | Hay un comentario obsoleto en pdf.py sobre la verificación del archivo | n/a | api/src/takab_api/dictamen/pdf.py:207-213; api/tests/dictamen/test_que_identifica_la_huella.py:282-313 | T-8.12 |
| A-247 | P3 | 🔷 MEJORA | PDF | Los PDF de ejemplo comiteados en runbooks/evidencia son del formato viejo (A4, sin membrete D-36) | n/a | takab-docs/runbooks/evidencia/report-technical-20260913T050713Z.pdf; takab-docs/runbooks/evidencia/report-tec… | T-8.12 |
| A-248 | P3 | 🔷 MEJORA | PDF | La hoja en blanco lleva «EVIDENCIA INMUTABLE» en el pie | n/a | api/src/takab_api/documentos/membrete.py:346-348; shared/brand/membrete/carta.pdf | T-8.12 |
| A-249 | P3 | 🔷 MEJORA | PDF | La pestaña de espera «Generando el documento» es HTML estático durante 10-30 s | takab_superadmin, inspector, tenant_admin | web/src/lib/download.ts:37-49,66-85; web/src/features/triage/TriageDetail.tsx:452-464; takab-docs/DECISIONES-… | T-8.12 |
| A-250 | P3 | 🔴 DEFECTO | Estatus visibles | Un comando de simulacro vencido (expired) se cuenta como «RECHAZADO» | tenant_admin, soc_operator (drill_start), lectores de /cons… | web/src/features/console/drill.ts:64,75-76; web/src/features/console/DrillHistory.tsx:50; web/src/features/sc… | T-8.14 |
| A-251 | P3 | ⬜ FALTA | Estatus visibles | La historia de salud sólo grafica el RTT; lag, NTP y batería viajan sin pintarse | roles /fleet | api/src/takab_api/routers/fleet.py:148-201; web/src/features/fleet/SiteCard.tsx:273-293 | T-8.14 |
| A-252 | P3 | ⬜ FALTA | Estatus visibles | Reconexiones, huecos y duplicados de SeedLink sólo en el panel LAN | soc_operator, takab_support | edge/takab_edge/local_api/__init__.py:1180-1197; shared/schemas/health_snapshot.schema.json (sin campos) | T-8.14 |
| A-253 | P3 | ⬜ FALTA | Estatus visibles | Estado de los gabinetes secundarios LoRa sólo en el panel LAN | soc_operator, tenant_admin | edge/takab_edge/lora/__init__.py:1-18,214; edge/takab_edge/schemas.py:58,160; edge/takab_edge/local_api/__ini… | T-8.14 |
| A-254 | P3 | 🟠 SOSPECHA | Estatus visibles | BACnet sin estado en ninguna superficie y con un rótulo que confunde | roles /fleet | edge/takab_edge/actuators/__init__.py:1-13,36; web/src/features/fleet/SiteCard.tsx:257; web/src/features/flee… | T-8.14 |
| A-255 | P3 | ⬜ FALTA | Estatus visibles | No hay vista del historial de comandos firmados por sitio | tenant_admin, soc_operator, building_admin | api/src/takab_api/routers/commands.py:336; db/schema.sql:1127-1153; web/src/features/building/useSirenTest.ts… | T-8.14 |
| A-256 | P3 | ⬜ FALTA | Estatus visibles | gateway_catalog_state (catálogo de tonos empujado) sin GET | takab_superadmin, tenant_admin | api/src/takab_api/routers/commands.py:524-541,602-615; api/tests/contracts/test_todo_campo_del_latido_tiene_d… | T-8.14 |
| A-257 | P3 | ⬜ FALTA | Estatus visibles | Solicitudes ARCO, historial de consentimiento y publicación de aviso sin UI | tenant_admin, takab_superadmin | api/src/takab_api/routers/privacy.py:179,317,391,508,545,611; api/src/takab_api/auth/matrix.py (tenant_admin:… | T-8.14 |
| A-258 | P3 | ⬜ FALTA | Estatus visibles | IncidentOut no expone opened_trigger ni cierre_sin_hora | roles de consola | db/schema.sql:289-306; api/src/takab_api/schemas/incidents.py:12-27; web/src/features/building/BuildingPage.t… | T-8.14 |
| A-259 | P3 | ⬜ FALTA | Estatus visibles | Inventario de cámaras sin lectura; la salud de cámara no se produce | tenant_admin, soc_operator, building_admin (cctv_read) | db/schema.sql:3449-3470; api/src/takab_api/routers/cctv.py:43-66; web/src/features/triage/CctvPanel.tsx:48-57 | T-8.14 |
| A-260 | P3 | ⬜ FALTA | Estatus visibles | billing_meters_daily, notify_template_quarantine y pii_retention_runs sin endpoint | takab_superadmin, takab_support | db/schema.sql:1441,1748,3374; api/src/takab_api/billing/meters.py; api/src/takab_api/notify/state.py; api/src… | T-8.14 |
| A-261 | P3 | ⬜ FALTA | Estatus visibles | RSS/memoria y carga de CPU del Pi no se producen | takab_support | shared/schemas/health_snapshot.schema.json; edge/takab_edge/local_api/__init__.py:1502-1549 | T-8.14 |
| A-262 | P3 | 🟠 SOSPECHA | Estatus visibles | test_mode sin lectura GPIO se reporta como inactivo en vez de S/D | técnico en sitio | edge/takab_edge/local_api/__init__.py:1595-1602 vs 1552-1558 | T-8.14 |
| A-263 | P3 | 🟠 SOSPECHA | Estatus visibles | relays_state=None: el schema dice S/D y la consola pinta ARMADO | roles /fleet y /console | api/src/takab_api/schemas/fleet.py:469-477; web/src/features/fleet/useFleet.ts:137-142 | T-8.14 |
| A-264 | P3 | 🔴 DEFECTO | Animaciones | El resorte de regreso ignora reduce-motion y corre en el hilo JS | brigadista, security_guard, building_admin (táctico) | mobile/src/features/control/ControlSheet.tsx:44-85; mobile/package.json:40-41 | T-8.15 |
| A-265 | P3 | 🔴 DEFECTO | Animaciones | La retención de pico decae por FOTOGRAMA: escala y línea de pico dependen del monitor | operador local del gabinete | edge/takab_edge/local_api/index.html:2475-2481,2611-2614,3352 | T-8.15 |
| A-266 | P3 | 🟠 SOSPECHA | Animaciones | Con reducción, los anillos 'ya llegó' sólo se recalculan con cada snapshot (hasta ~30 s tarde) | roles de consola web con reduce-motion | web/src/features/console/MapPanel.tsx:1149-1153,1201-1211 | T-8.15 |
| A-267 | P3 | 🟠 SOSPECHA | Animaciones | Las marcas se deslizan con el reloj de pared mientras la traza se congela al perder conexión | operador local del gabinete | edge/takab_edge/local_api/index.html:1223-1229,2482-2494,2639-2659 | T-8.15 |
| A-268 | P3 | 🔷 MEJORA | Animaciones | Barra indeterminada mientras hay consulta en vuelo (en vez de sólo 'CARGANDO · X…') | todos los de consola | web/src/components/StateFrame.tsx:164-172; web/src/styles/app.css:129 | T-8.15 |
| A-269 | P3 | 🔷 MEJORA | Animaciones | Cabeza de escritura que late sólo con dato vivo | soc_operator, gov_operator, inspector | web/src/features/console/FeatureStrip.tsx:32,69; web/src/features/console/DetailPanel.tsx:182-183,318 | T-8.15 |
| A-270 | P3 | 🔷 MEJORA | Animaciones | Tres animaciones mueven propiedades de layout o de pintura | tenant_admin, takab_* (flota), soc_operator | web/src/styles/soc-tabs.css:469-473,1190-1200,142-152 | T-8.15 |
| A-271 | P3 | 🔷 MEJORA | Animaciones | easeTo sólo por acción del operador; nunca automático al llegar una alerta | soc_operator, gov_operator | web/src/features/console/MapPanel.tsx (grep easeTo/flyTo vacío); web/src/features/console/IncidentTable.tsx:2… | T-8.15 |
| A-272 | P3 | 🔷 MEJORA | Animaciones | Mismo período de latido que las otras superficies y punto de BACKFILL EN CURSO | operador local del gabinete | edge/takab_edge/local_api/index.html:84,1908,3355-3358; mobile/src/ui/theme.ts:36-43; edge/tests/test_local_a… | T-8.15 |
| A-273 | P3 | 🔷 MEJORA | Animaciones | Barra indeterminada por fila en 'ENVIANDO…' y tinte al pasar a OK | brigadista, inspector, security_guard | mobile/src/features/sync/syncView.ts:58-60,84; mobile/src/app/(brigadista)/sync.tsx:118-160; mobile/src/offli… | T-8.15 |
| A-274 | P3 | 🔷 MEJORA | Animaciones | Duraciones a mano y sin censo que obligue a consultar reduce-motion | desarrollo (afecta a occupant y táctico) | mobile/src/ui/theme.ts:42-51; mobile/src/features/notices/SiteNoticeStrip.tsx:25; mobile/src/features/panic/P… | T-8.15 |
| A-275 | P3 | 🔷 MEJORA | Animaciones | Cambio de pestaña sin transición | occupant, táctico | mobile/src/app/(occupant)/_layout.tsx:23-61; mobile/src/app/(brigadista)/_layout.tsx:57 | T-8.15 |
| A-276 | P3 | 🟠 SOSPECHA | Funciones básicas | Inventario y salud de flota, versión contra releases, mantenimiento, alta de sitio, gabinete y sensor | takab_support, takab_superadmin, tenant_admin (lectura) | web/src/features/fleet/FleetPage.tsx; web/src/features/fleet/useFleetMutations.ts:248; api/src/takab_api/rout… | T-8.19 |
| A-277 | P3 | ⬜ FALTA | Funciones básicas | Sin SSO corporativo ni credenciales de máquina para integraciones entrantes | tenant_admin, cliente corporativo/universidad | infra/terraform/modules/identity/main.tf:153,622,658; takab-docs/BLUEPRINT-TECNICO-TAKAB.md:520; takab-docs/T… | T-8.19 |
| A-278 | P3 | 🟠 SOSPECHA | Funciones básicas | Bitácora inmutable, etiquetas normativas declaradas por el cliente, aviso versionado y ARCO | tenant_admin, gov_operator, takab_superadmin, occupant (ARC… | api/src/takab_api/routers/audit.py:40; web/src/features/audit/AuditPage.tsx:22-37; api/src/takab_api/routers/… | T-8.19 |
| A-279 | P3 | 🟠 SOSPECHA | Funciones básicas | ShakeMap por evento, catálogo USGS e intensidad medida en el inmueble; MMI, Sa y deriva pendientes | inspector, soc_operator, gov_operator | api/src/takab_api/shakemap/; api/src/takab_api/routers/shakemap.py:35; takab-docs/TASKS.md:10612-10622,15113 | T-8.19 |
| A-280 | P3 | 🟠 SOSPECHA | Funciones básicas | Medición de facturación y costos: el job no corre en la nube y no hay pantalla | takab_superadmin | api/src/takab_api/billing/__init__.py:1; Makefile:89-90; deploy/cloud/docker-compose.yml:36-124; infra/terraf… | T-8.19 |
| A-281 | P3 | 🔴 DEFECTO | Funciones básicas | T-2.172: el fail-open del modo prueba escribe 24 errores en cada ventana de mantenimiento | takab_support | takab-docs/TASKS.md:5859; edge/takab_edge/supervisor.py:592-600,677 | T-8.17 |
| A-282 | P3 | 🟠 SOSPECHA | Funciones básicas | Fichas que el propio repositorio da por hechas y siguen abiertas | n/a | takab-docs/TASKS.md:10365-10374,10318-10346,10624-10631; deploy/cloud/deploy.sh:149-151; takab-docs/PLAN-REVI… | T-8.19 |
| A-283 | P3 | 🔷 MEJORA | Edge/nube/presentación | El resume de SeedLink solo vive en memoria: cada reinicio del canary pierde los segundos de onda del reinicio | inspector (evidencia/helicorder) | edge/takab_edge/seedlink/__init__.py:272; edge/takab_edge/seedlink/__init__.py:300-302 | T-8.17 |
| A-284 | P3 | 🔷 MEJORA | Edge/nube/presentación | temperature_c devuelve 0.0 cuando no hay dato, contra la regla de oro 7 | n/a | edge/takab_edge/health/__init__.py:1-12; edge/takab_edge/health/__init__.py:192-196; edge/takab_edge/health/_… | T-8.17 |
| A-285 | P3 | 🔷 MEJORA | Edge/nube/presentación | Panel LAN: el bloqueo por PIN es global y el PIN viaja por HTTP en claro | building_admin, security_guard (operan el panel) | edge/takab_edge/local_api/__init__.py:61; edge/takab_edge/local_api/__init__.py:557-577; edge/takab_edge/loca… | T-8.17 |
| A-286 | P3 | ✅ OK | Web · MONITOREO/EVALUACIÓN | Inventario de rutas, roles y aterrizaje tras el login | todos | web/src/app/routes.tsx:17-79; web/src/app/landing.ts:5-7; web/src/app/RouteGuard.tsx:16-20; web/src/shell/nav… | T-8.07 |
| A-287 | P3 | ✅ OK | Web · MONITOREO/EVALUACIÓN | Topbar: pestañas, estado de conexión, MQTT, alcance y reloj | los 7 roles web | web/src/shell/Topbar.tsx:46-130 | T-8.07 |
| A-288 | P3 | ✅ OK | Web · MONITOREO/EVALUACIÓN | Menú del operador: editar nombre y SALIR | los 7 roles web | web/src/shell/OperatorMenu.tsx:14-118; web/src/auth/useProfile.ts:27-41; web/src/auth/session.store.ts:229-240 | T-8.07 |
| A-289 | P3 | ✅ OK | Web · MONITOREO/EVALUACIÓN | Tira de KPIs con el filtro OCULTAR SIN ENLACE | los 7 roles web | web/src/features/console/KpiStrip.tsx:54-135; web/src/features/console/ConsolePage.tsx:132-148,261-266 | T-8.07 |
| A-290 | P3 | ✅ OK | Web · MONITOREO/EVALUACIÓN | Mapa: clic en sitios y en el catálogo, capas, comparativa y leyendas | los 7 roles web | web/src/features/console/MapPanel.tsx:400-407,1025-1039,1296-1304,1327-1365,1456-1480,1492-1563 | T-8.07 |
| A-291 | P3 | ✅ OK | Web · MONITOREO/EVALUACIÓN | Modal de comparativa histórica | los 7 roles web | web/src/features/console/ComparePanel.tsx:64-144; web/src/features/console/ConsolePage.tsx:341-356 | T-8.07 |
| A-292 | P3 | ✅ OK | Web · MONITOREO/EVALUACIÓN | Tira de simulacro e historial | iniciar/exportar: takab_superadmin, tenant_admin; historial… | web/src/features/console/DrillControls.tsx:22-67; web/src/features/console/DrillHistory.tsx:61-190; api/src/t… | T-8.07 |
| A-293 | P3 | ✅ OK | Web · MONITOREO/EVALUACIÓN | Botones de los banners de escena | takab_superadmin, tenant_admin (acciones); lectura: roles d… | web/src/features/scene/DrillBanner.tsx:42-117,175-229; web/src/features/scene/MaintenanceBanner.tsx:40-100; w… | T-8.07 |
| A-294 | P3 | ✅ OK | Web · MONITOREO/EVALUACIÓN | miniSEED, DICTAMEN PDF, firma, clasificación y enlaces de navegación | los 7 roles web (acciones según la matriz) | web/src/features/triage/TriageDetail.tsx:251-258,267-299,339-465,477-555; web/src/features/triage/useIncident… | T-8.08 |
| A-295 | P3 | ✅ OK | Web · flota/tenants/edificio | Inventario de controles de /fleet (FleetPage + FleetToolbar + SiteCard) | ve la página: takab_superadmin, takab_support, tenant_admin… | web/src/features/fleet/FleetPage.tsx:139-401; web/src/features/fleet/FleetToolbar.tsx:29-86; web/src/features… | T-8.09 |
| A-296 | P3 | ✅ OK | Web · flota/tenants/edificio | Inventario de FleetAdmin (estaciones, hardware y códigos de alta) | takab_superadmin, tenant_admin (CÓDIGOS: enrollment_manage,… | web/src/features/fleet/FleetAdmin.tsx:70-355; web/src/features/fleet/SiteForm.tsx; web/src/features/fleet/Har… | T-8.09 |
| A-297 | P3 | ✅ OK | Web · flota/tenants/edificio | Inventario de /tenants | ve la página: takab_superadmin, takab_support, tenant_admin… | web/src/features/tenants/TenantsPage.tsx:123-657; web/src/features/tenants/TenantEditForm.tsx; web/src/featur… | T-8.09 |
| A-298 | P3 | ✅ OK | Web · flota/tenants/edificio | Inventario de /building/:siteId | ve la página: takab_superadmin, takab_support, tenant_admin… | web/src/features/building/BuildingPage.tsx:47-261; web/src/features/building/SirenTestPanel.tsx:33-86; web/sr… | T-8.09 |
| A-299 | P3 | ✅ OK | Web · flota/tenants/edificio | Inventario de /audit | takab_superadmin, takab_support, tenant_admin, gov_operator | web/src/features/audit/AuditPage.tsx:39-175; web/src/features/audit/useAudit.ts:57-121; api/src/takab_api/rou… | T-8.09 |
| A-300 | P3 | ✅ OK | Web · flota/tenants/edificio | Banner de aviso de privacidad (en el shell, todas las pantallas web) | todos los roles web (takab_superadmin, takab_support, tenan… | web/src/features/privacy/PrivacyConsentBanner.tsx:83-235; web/src/features/privacy/usePrivacyConsent.ts:95-14… | T-8.19 |
| A-301 | P3 | ✅ OK | Web · flota/tenants/edificio | Componentes de telemetría: solo lectura, con insignia de 'sin calibrar' | todos los que ven /building | web/src/features/telemetry/HistoryChart.tsx:54-73; web/src/features/telemetry/MultiChannelStrip.tsx:59; web/s… | T-8.09 |
| A-302 | P3 | ✅ OK | Web · flota/tenants/edificio | Cómo levantar la consola local y entrar rol por rol con dev-token | todos | Makefile:112-117,131-135; demo/soc_local.sh:1-60; api/scripts/dev_auth_env.py:1-50; web/src/pages/LoginPage.t… | T-8.09 |
| A-303 | P3 | ✅ OK | Móvil | Matriz RBAC §3 contra la UI: cada ✅ tiene su entrada y no sobra nada | occupant, brigadista, security_guard, inspector, building_a… | mobile/src/auth/pestanasTacticas.ts:41-63; mobile/src/app/(brigadista)/_layout.tsx:103-157; api/src/takab_api… | T-8.18 |
| A-304 | P3 | ✅ OK | Móvil | Inventario de pantallas, controles, endpoints y estados | todos | mobile/src/app/login.tsx:29-57; mobile/src/app/onboarding/permisos.tsx:75-105; mobile/src/app/onboarding/priv… | T-8.18 |
| A-305 | P3 | ✅ OK | Móvil | Movimiento existente: 6 animaciones con Animated clásico, todas respetan «reducir movimiento»; no hay hápticos | todos | mobile/src/features/alert/CrisisView.tsx:100-128; mobile/src/features/panic/PanicButton.tsx:28-95; mobile/src… | T-8.15 |
| A-306 | P3 | ✅ OK | Móvil | Las credenciales de Firebase y el .env móvil están correctamente ignorados | n/a | mobile/.gitignore:34; mobile/.gitignore:46-53 | T-8.18 |
| A-307 | P3 | ✅ OK | RBAC y flujos | MATRIZ rol×flujo · takab_superadmin | takab_superadmin | api/src/takab_api/auth/matrix.py:72,362-405; web/src/shell/navItems.ts:12-30; web/src/app/landing.ts:5-7; web… | T-8.01 |
| A-308 | P3 | ✅ OK | RBAC y flujos | MATRIZ rol×flujo · takab_support | takab_support | api/src/takab_api/auth/matrix.py:73,406; takab-docs/RBAC-TAKAB.md:57,80-86 | T-8.01 |
| A-309 | P3 | ✅ OK | RBAC y flujos | MATRIZ rol×flujo · tenant_admin | tenant_admin | api/src/takab_api/auth/matrix.py:74,407-434; web/src/features/fleet/FleetAdmin.tsx:71,107,135; web/src/featur… | T-8.01 |
| A-310 | P3 | ✅ OK | RBAC y flujos | MATRIZ rol×flujo · soc_operator | soc_operator | api/src/takab_api/auth/matrix.py:75,438-445; web/src/features/console/ConsolePage.tsx:191,207-208; web/src/fe… | T-8.01 |
| A-311 | P3 | ✅ OK | RBAC y flujos | MATRIZ rol×flujo · gov_operator | gov_operator | api/src/takab_api/auth/matrix.py:78,447; takab-docs/RBAC-TAKAB.md:60,69-75 | T-8.01 |
| A-312 | P3 | ✅ OK | RBAC y flujos | MATRIZ rol×flujo · inspector (web + móvil) | inspector | api/src/takab_api/auth/matrix.py:79,451-465; mobile/src/auth/pestanasTacticas.ts:41-49; mobile/src/auth/profi… | T-8.01 |
| A-313 | P3 | ✅ OK | RBAC y flujos | MATRIZ rol×flujo · building_admin (web + móvil) | building_admin | api/src/takab_api/auth/matrix.py:80,468-482; web/src/features/console/DetailPanel.tsx:206-210; web/src/featur… | T-8.01 |
| A-314 | P3 | ✅ OK | RBAC y flujos | MATRIZ rol×flujo · brigadista | brigadista | api/src/takab_api/auth/matrix.py:485-494; mobile/src/auth/pestanasTacticas.ts:41-49; api/src/takab_api/router… | T-8.01 |
| A-315 | P3 | ✅ OK | RBAC y flujos | MATRIZ rol×flujo · occupant | occupant | api/src/takab_api/auth/matrix.py:83,506; api/src/takab_api/auth/deps.py:91-94; mobile/src/app/(occupant)/inic… | T-8.01 |
| A-316 | P3 | ✅ OK | RBAC y flujos | Paridad matriz ↔ §3 móvil ↔ pestañas: OK celda a celda | todos | api/src/takab_api/auth/matrix.py:71-84,448-506; takab-docs/RBAC-TAKAB.md:54-65,318-339; mobile/src/auth/pesta… | T-8.01 |
| A-317 | P3 | ✅ OK | RBAC y flujos | Guards y navegación de la web: dirigidos por el servidor y con default-deny: OK | todos los web | web/src/shell/navItems.ts:12-30; web/src/app/RouteGuard.tsx:10-21; web/src/features/fleet/useFleet.ts:203-217… | T-8.01 |
| A-318 | P3 | ✅ OK | PDF | Generador 1 · Dictamen técnico = informe del evento (T-7.22) | generar: takab_superadmin, inspector (generate_report); des… | api/src/takab_api/dictamen/pdf.py:136-181; api/src/takab_api/routers/reports.py:39,50-184,217-234; api/pyproj… | T-8.12 |
| A-319 | P3 | ✅ OK | PDF | Generador 2 · Resumen ejecutivo (variant=executive) | takab_superadmin, inspector | api/src/takab_api/dictamen/pdf.py:1747-1827; api/src/takab_api/routers/reports.py:47,70-71 | T-8.12 |
| A-320 | P3 | ✅ OK | PDF | Generador 3 · Reporte de simulacro | takab_superadmin, tenant_admin (drill_start) | api/src/takab_api/drill_report.py:238-377; api/src/takab_api/routers/drills.py:51-53,786-880; web/src/feature… | T-8.12 |
| A-321 | P3 | ✅ OK | PDF | Generador 4 · Hoja membretada en blanco (carta.pdf y carta.svg) | n/a (artefacto comiteado) | api/src/takab_api/documentos/hoja.py:1-90; shared/brand/membrete/carta.pdf; Makefile:248-257; api/src/takab_a… | T-8.12 |
| A-322 | P3 | ✅ OK | PDF | Acentos y glifos especiales cubiertos por la tipografía embebida | todos | api/src/takab_api/documentos/fonts/; api/src/takab_api/documentos/membrete.py:219-236,325-330; api/pyproject.… | T-8.12 |
| A-323 | P3 | ✅ OK | Estatus visibles | Flota: estado derivado, enlace y versión con edad | roles /fleet | web/src/features/fleet/SiteCard.tsx:84-95,171-249,273-309; api/src/takab_api/routers/fleet.py:204-354; web/sr… | T-8.14 |
| A-324 | P3 | ✅ OK | Estatus visibles | Enlace en el mapa y KPIs dentro de StateFrame con staleSince | roles /console | web/src/features/console/link.ts:1-40; web/src/features/console/KpiStrip.tsx:1-52; web/src/features/console/C… | T-8.14 |
| A-325 | P3 | ✅ OK | Estatus visibles | Fases del incidente (D-33) en web y móvil | todos | takab-docs/DECISIONES-MAURICIO.md:1637-1678; web/src/features/scene/scene.ts:110-120; web/src/features/consol… | T-8.14 |
| A-326 | P3 | ✅ OK | Estatus visibles | Simulacros: estados y acuses visibles | roles /console; móvil táctico y ocupante | web/src/features/console/DrillHistory.tsx:36-58,88-97; web/src/features/scene/DrillBanner.tsx:63-115; api/src… | T-8.14 |
| A-327 | P3 | ✅ OK | Estatus visibles | Cadena de notificación distingue entregado, aceptado, simulado y fallido | roles /triage | db/schema.sql:1347-1400; web/src/features/triage/NotifyChain.tsx:1-41,61-114 | T-8.14 |
| A-328 | P3 | ✅ OK | Estatus visibles | Estado real del relé tras arbitraje (channel_state) en checklist y app | roles /console y tácticos móviles | api/src/takab_api/ingest/handlers.py:657-666,888-901; web/src/features/triage/IncidentTimeline.tsx:40-57; mob… | T-8.14 |
| A-329 | P3 | ✅ OK | Estatus visibles | Procedencia del catálogo sísmico desde el glosario compartido | roles /console y /triage | web/src/features/triage/procedencia.ts:1-60; web/src/features/console/EpicentroCard.tsx:23; db/schema.sql:210… | T-8.14 |
| A-330 | P3 | ✅ OK | Estatus visibles | El panel LAN es la superficie más completa y declara edades | técnico en sitio | edge/takab_edge/local_api/__init__.py:742-806,1180-1313,1483-1593 | T-8.14 |
| A-331 | P3 | ✅ OK | Estatus visibles | La app táctica muestra la salud con su edad y la del ocupante avisa si el gabinete calla | brigadista, security_guard, inspector, building_admin, occu… | mobile/src/features/panel/PanelView.tsx:76-87; mobile/src/features/home/health.ts:31-32; mobile/src/features/… | T-8.14 |
| A-332 | P3 | ✅ OK | Estatus visibles | Demo y mantenimiento: banners en las 6 rutas con StateFrame | roles de consola | web/src/features/scene/DemoModeBanner.tsx:52-96; web/src/features/scene/MaintenanceBanner.tsx:47-101; web/src… | T-8.14 |
| A-333 | P3 | ✅ OK | Estatus visibles | Perfil de audio y censo relé a relé no se persisten, por razón declarada | n/a | api/tests/contracts/test_todo_campo_del_latido_tiene_destino.py:68-89; api/src/takab_api/ingest/handlers.py:4… | T-8.14 |
| A-334 | P3 | ✅ OK | Animaciones | Inventario: tokens de duración/curva únicos para las tres superficies | todos | shared/design-tokens/tokens.json:118-129; shared/design-tokens/css/tokens.css:125-136; mobile/src/ui/theme.ts… | T-8.15 |
| A-335 | P3 | ✅ OK | Animaciones | Inventario: reducción DERIVADA (tokens a 0 + keyframes apagados por selector con reposo fijado) | roles de consola web (takab_superadmin, takab_support, tena… | web/src/styles/soc.css:1807-1849; web/src/styles/motionInvariants.test.ts:79-229; web/e2e/motion.spec.ts:60-1… | T-8.15 |
| A-336 | P3 | ✅ OK | Animaciones | Inventario: el halo soc-dot--pulse sólo late con frescura real | roles de consola web | web/src/features/console/DetailPanel.tsx:182-183,315-319; web/src/features/fleet/LinkPill.tsx:21,42-60 | T-8.15 |
| A-337 | P3 | ✅ OK | Animaciones | Inventario: frentes, dash y ráfaga apagados y DECLARADOS bajo reducción | roles de consola web | web/src/features/console/MapPanel.tsx:1056-1113,1166-1211,1238-1257,1372-1383; web/src/features/console/wavef… | T-8.15 |
| A-338 | P3 | ✅ OK | Animaciones | Inventario: 2 keyframes, 0 transiciones, reducción global, latido sólo con conexión viva | operador local del gabinete (LAN), building_admin, security… | edge/takab_edge/local_api/index.html:55-57,77-84,1233-1238,1278-1280,3341-3349; edge/tests/test_local_api_pan… | T-8.15 |
| A-339 | P3 | ✅ OK | Animaciones | Inventario: useReduceMotion consultado en LatidoPunto, CrisisView, PanicButton y SiteNoticeStrip | occupant, brigadista, security_guard, inspector, building_a… | mobile/src/ui/useReduceMotion.ts:8-27; mobile/src/features/panel/LatidoPunto.tsx:17-49; mobile/src/features/p… | T-8.15 |
| A-340 | P3 | ✅ OK | Animaciones | NO animar el texto ni la entrada de la instrucción de alerta; sólo la carcasa | todos | takab-docs/DECISIONES-MAURICIO.md:1504-1528; mobile/src/features/alert/CrisisView.primerFrame.test.tsx:1-40; … | T-8.15 |
| A-341 | P3 | ✅ OK | Animaciones | NO shimmer ni animación en DATO RETENIDO / stale, ni tween en cifras de dato | todos | web/src/styles/soc.css:1339-1344,1821-1826; edge/takab_edge/local_api/index.html:77-84,3342-3349 | T-8.15 |
| A-342 | P3 | ✅ OK | Animaciones | NO anillos en todas las estaciones activas, ni transiciones de ruta en /console, ni salida animada de filas | roles de consola, operador local | web/src/features/console/MapPanel.tsx:677-690; web/src/features/console/link.ts:82-97; web/src/styles/soc.css… | T-8.15 |
| A-343 | P3 | ✅ OK | Funciones básicas | Reflejo SASMEX/WR-1 → sirena en el gabinete, sin nube ni IA | todos (occupant, brigadista, soc_operator) | edge/takab_edge/gpio/__init__.py:922-929; takab-docs/TASKS.md:1071 (T-1.42 [~]); takab-docs/TASKS.md:12762 (T… | T-8.01 |
| A-344 | P3 | ✅ OK | Funciones básicas | Silencio y activación manual firmados (MFA + nonce + ack) y pánico por cuórum de ocupantes | brigadista, security_guard, building_admin, inspector, occu… | api/src/takab_api/routers/commands.py:139,307,375; takab-docs/TASKS.md:10434-10444 (T-2.93) | T-8.01 |
| A-345 | P3 | ✅ OK | Funciones básicas | Consola MONITOREO: mapa, KPIs, cola de incidentes por WS, ficha de estación, sismograma, epicentro, ondas y franjas de escena | soc_operator, tenant_admin, gov_operator, takab_superadmin,… | web/src/app/routes.tsx:27-33; web/src/features/console/ConsolePage.tsx; web/src/features/console/MapPanel.tsx… | T-8.01 |
| A-346 | P3 | ✅ OK | Funciones básicas | Ciclo de vida: fases, acuse con tiempo, destinatarios, clasificación y cierre | soc_operator, gov_operator (acuse), tenant_admin, inspector | api/src/takab_api/incident/lifecycle.py:67,246; api/src/takab_api/routers/classification.py:135,238; api/src/… | T-8.01 |
| A-347 | P3 | ✅ OK | Funciones básicas | Dictamen semaforizado firmado, inmutable y con PDF verificable | inspector, takab_superadmin; lectura: brigadista, security_… | api/src/takab_api/routers/dictamens.py:77; api/src/takab_api/routers/reports.py:51; api/src/takab_api/dictame… | T-8.01 |
| A-348 | P3 | ✅ OK | Funciones básicas | Informe del evento, reporte de simulacro PDF/CSV y membrete común | soc_operator, tenant_admin, gov_operator | api/src/takab_api/drill_report.py:43; api/src/takab_api/routers/drills.py:787; takab-docs/TASKS.md:14566,1466… | T-8.01 |
| A-349 | P3 | ✅ OK | Funciones básicas | App de ocupante y app táctica: las 21 pantallas de la especificación | occupant, brigadista, security_guard, inspector, building_a… | mobile/src/app/(occupant)/; mobile/src/app/(brigadista)/; mobile/src/app/crisis.tsx; mobile/src/app/checkin.t… | T-8.01 |
| A-350 | P3 | ✅ OK | Funciones básicas | Simulacros: agenda, disparo humano armado, plantillas, sonido auditado y reporte PDF/CSV | soc_operator, tenant_admin, building_admin, brigadista, occ… | api/src/takab_api/routers/drills.py:434-787; api/src/takab_api/routers/drill_templates.py; web/src/features/c… | T-8.01 |
| A-351 | P3 | ✅ OK | Funciones básicas | Matriz de 10 roles ejecutable, RLS default-deny, alcance por sitio y visibilidad gov_shared | todos | api/src/takab_api/auth/matrix.py:55-80; api/src/takab_api/routers/visibility.py:36-85; api/src/takab_api/rout… | T-8.01 |
| A-352 | P3 | ✅ OK | Edge/nube/presentación | Lo que ya está resuelto en robustez del edge | n/a | edge/takab_edge/seedlink/__init__.py:213-232; edge/takab_edge/cloud/__init__.py:48-60; edge/takab_edge/cloud/… | T-8.17 |
| A-353 | P3 | ✅ OK | Edge/nube/presentación | Alcance del CCTV, LoRa y G-04 | n/a | edge/systemd/takab-cctv.service:9-12; takab-docs/runbooks/RUNBOOK-demo-cliente.md:98-112; takab-docs/PENDIENT… | T-8.17 |
| A-354 | P3 | ✅ OK | Edge/nube/presentación | Lo que ya está bien en observabilidad y despliegue de la nube | n/a | infra/terraform/modules/observability/main.tf:166-946; infra/terraform/envs/dev/budget.tf:1-23; deploy/cloud/… | T-8.16 |
| A-355 | P3 | ✅ OK | Edge/nube/presentación | Costes | n/a | deploy/cloud/docker-compose.yml:3-6; infra/terraform/envs/dev/budget.tf:1-23; takab-docs/PLAN-REVISION-PRESEN… | T-8.16 |
| A-356 | P3 | ✅ OK | Edge/nube/presentación | Lo desplegado coincide con el repositorio, y el Plan B y las listas están al día | n/a | takab-docs/INFORME-CONFORMIDAD-DEMO.md:76-102; takab-docs/runbooks/RUNBOOK-demo-cliente.md:50-123; takab-docs… | T-8.13 |

## 5 · Detalle de los P0 y P1

### A-001 · P0 · CONFIRMADO: el refreshToken se guarda pero nunca se usa; la sesión móvil muere a los ~60 min

- **Estado:** 🔴 DEFECTO · **Dimensión:** Móvil · **Ficha:** `T-8.04`
- **Roles:** occupant, brigadista, security_guard, inspector, building_admin
- **Evidencia:** mobile/src/auth/useAuth.ts:48; mobile/src/auth/useAuth.ts:76-81; mobile/src/auth/secureTokens.ts:29; mobile/src/services/sdk.ts:46-51; mobile/src/live/socket.ts:23-24; api/src/takab_api/routers/ws.py:88-98; api/src/takab_api/auth/tokens.py:75; infra/terraform/modules/identity/main.tf:629-631; infra/terraform/modules/identity/main.tf:665-667; mobile/src/features/alert/useAlertState.ts:21; mobile/src/app/crisis.tsx:60; mobile/src/app/login.tsx:63-66; takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md:414-418

Refutación buscada sin éxito. En mobile/src no hay refreshAsync, grant_type, TokenResponse ni isTokenFresh, y el campo refreshToken sólo aparece en secureTokens.ts y en useAuth.ts. package.json no trae expo-task-manager ni background-fetch, así que no hay renovación en segundo plano. live/socket.ts lee useSessionStore.idToken y ante 4401 llama a signOut. offline/sync.ts sólo marca el 401 como reintentable (httpOutcome.ts:6-8), pero el interceptor ya cerró la sesión antes.

Cadena medida en el código:
1. El ID token dura 60 min (identity/main.tf:630 y 666) y el API lo valida con leeway=0 (tokens.py:75).
2. useAlertState consulta cada 30 s en reposo (useAlertState.ts:21) → llega un 401 → sdk.ts:47-48 hace signOut.
3. En paralelo, el API cierra el WebSocket al vencer el exp con 4401 (ws.py:88-98) → socket.ts:24 hace signOut.
4. En arranque en frío con el token vencido, bootstrapSession llama a /me → 401 → login (useAuth.ts:96-112).

Consecuencias:
- Cualquier rol vuelve a teclear contraseña (y TOTP si es táctico) cada hora.
- crisis.tsx:60, checkin.tsx:70, alarma-inmueble.tsx:60 y panic.tsx:79 redirigen a '/' en cuanto no hay sesión. Eso incumple la aceptación de la spec 0.1: «expiración del refresh NO bloquea la pantalla de crisis».
- clearSession borra el sitio vigilado (secureTokens.ts:78-79), así que CrisisWatcher deja de consultar el estado.
- login.tsx:64 afirma «SU SESIÓN DE OCUPANTE PERMANECE ACTIVA…», que hoy es falso.

### A-002 · P0 · Diseño exacto de la renovación: REST, socket, camino offline y arranque (expo-auth-session)

- **Estado:** ⬜ FALTA · **Dimensión:** Móvil · **Ficha:** `T-8.04`
- **Roles:** todos los roles móviles
- **Evidencia:** mobile/src/services/sdk.ts:39-51; mobile/src/live/socket.ts:21-25; shared/sdk-ts/src/live.ts:135-139; shared/sdk-ts/src/live.ts:156-161; shared/sdk-ts/src/live.ts:214-223; mobile/src/auth/useAuth.ts:89-117; mobile/src/offline/OfflineSyncGate.tsx:18-48; mobile/src/offline/httpOutcome.ts:6-8; mobile/src/auth/config.ts:45-57; mobile/src/services/sdk.test.ts:54

1) auth/secureTokens.ts — añadir a StoredSession: idTokenExp (segundos, del claim exp), authAt (ms del login real; NO se actualiza al renovar) y role (tomado de /me). El refreshToken ya está.

2) Nuevo auth/refresh.ts:
- refreshSession() de vuelo único: una promesa compartida para que varias llamadas concurrentes no gasten el mismo refresh.
- Llama a AuthSession.refreshAsync({clientId: POOLS[profile].clientId, refreshToken}, discoveryFor(POOLS[profile])). Sólo usa tokenEndpoint /oauth2/token, que Cognito acepta con y sin rotación.
- Si sale bien: nuevo idToken; nuevo refreshToken si la rotación está activa, si no se conserva el anterior. Luego saveSession, useSessionStore.setState({idToken}) y reconexión del socket con getLiveSocket().close() + connect(). close() no borra los listeners y al recibir 'ready' se vuelve a suscribir (live.ts:180-188).
- Devuelve tres estados: 'refreshed'; 'dead' (TokenError invalid_grant o NotAuthorized, refreshToken ausente, o authAt+maxAge del rol vencido); 'offline' (TypeError de fetch o 5xx).
- ensureFresh(margen=300 s) decodifica el exp con base64url, sin verificar la firma (eso lo hace el API), y renueva si faltan menos de 5 min.

3) services/sdk.ts:
- El interceptor de petición pasa a ser async (hey-api ReqInterceptor admite Promise: shared/sdk-ts/node_modules/@hey-api/client-fetch/dist/index.d.ts:112) y hace await ensureFresh() antes de poner el Bearer.
- En la respuesta, un 401 dispara await refreshSession(). Sólo 'dead' hace signOut. Con 'refreshed' se reintenta una vez: para POST, clonar la Request en el interceptor de petición (el body se consume); si no, dejar que React Query o la cola reintenten. 'offline' nunca expulsa.
- Se conserva la exención RUTAS_QUE_NO_CIERRAN_SESION.

4) live/socket.ts: onUnauthorized pasa a (a) refreshSession(); 'refreshed' → getLiveSocket().connect() (tras un 4401 ws=null, así que connect() reabre); 'dead' → signOut; 'offline' → reintento con backoff. Es imprescindible porque el servidor cierra el socket al exp del token del handshake aunque el REST ya se haya renovado.

5) bootstrapSession (useAuth.ts:89): ensureFresh() antes de /me. 'offline' conserva la sesión cacheada con me=null (ya existe en useAuth.ts:113-116); 'dead' manda al login.

6) _layout.tsx: ensureFresh() en AppState 'active' y cada 10 min en primer plano. OfflineSyncGate y drainQueue: ensureFresh() al empezar; si da 'dead' no se drena y los items quedan pending, sin perderse.

7) Camino offline: sin red no se renueva, y no hace falta hasta que vuelva la red. El listener de red de OfflineSyncGate (OfflineSyncGate.tsx:27-31) renueva primero y después drena. Un teléfono sin red 29 días vuelve sin pedir login.

8) Crisis: crisis/checkin/alarma deben tolerar un status 'expired' (dato retenido < 15 min + botón «volver a iniciar sesión») en lugar de Redirect.

9) Tests: sdk.test.ts:54 («401 cierra la sesión») pasa a «401 → refresh; sólo dead → signOut». Añadir tests de vuelo único, rotación, offline, socket 4401→refresh→connect y arranque con token vencido.

### A-003 · P0 · Política «1 mes» (brigadista, inspector, ocupante) / «1 día» (resto): Terraform no la puede expresar hoy

- **Estado:** ⬜ FALTA · **Dimensión:** Móvil · **Ficha:** `T-8.04`
- **Roles:** brigadista, inspector, occupant (30 d); security_guard, building_admin (1 d)
- **Evidencia:** infra/terraform/modules/identity/main.tf:155-168; infra/terraform/modules/identity/main.tf:619-638; infra/terraform/modules/identity/main.tf:655-674; api/src/takab_api/settings.py:249; api/src/takab_api/auth/tokens.py:38-48; api/src/takab_api/auth/mfa.py:85-88; mobile/src/app/login.tsx:29-57

Estado actual:
- mobile_occupants: refresh de 90 días (main.tf:631). Ya supera el mes; el problema es sólo que el cliente no renueva.
- mobile_tactical: 24 h (main.tf:667) y lo comparten los 4 roles tácticos del pool principal. Cognito no permite validez por grupo, y la app elige el cliente ANTES de conocer el rol (login.tsx: dos botones).

Recomendación (opción B):
- Subir mobile_tactical a refresh_token_validity=30 con unidades 'days'.
- Para security_guard y building_admin, imponer 1 día en DOS sitios: (a) en la app, refreshSession devuelve 'dead' si now − authAt > 24 h; (b) en el API, rechazar con 401 'reauth_required' el ID token de esos roles con auth_time de más de 86 400 s.
- Que Cognito conserve el auth_time original en los ID tokens renovados es NO_MEDIDO: hay que decodificar un token renovado. Si no lo conserva, la barrera sólo es de la app.
- Bajar mobile_occupants a 30 días si «1 mes» es literal.
- Activar la rotación con el bloque refresh_token_rotation { feature = "ENABLED"; retry_grace_period_seconds = 10 }. Obliga a QUITAR ALLOW_REFRESH_TOKEN_AUTH (main.tf:626 y 662), que es incompatible según la doc de AWS. El token rotado conserva el vencimiento ORIGINAL, así que la sesión dura exactamente 1 mes desde el login y no se alarga.
- La versión del provider que soporta el bloque es NO_MEDIDO; el lock tiene 6.53–6.62.

Opción A (alternativa): un tercer cliente 'takab-mobile-field' de 30 días y un botón de login aparte; hay que añadir su client_id a auth_audience (settings.py:249, lista separada por comas, tokens.py:38-48). Más fricción para el usuario.

MFA: la renovación no vuelve a pedir TOTP, así que cumple «sin código MFA durante 1 mes».

Web (fuera de esta dimensión): el cliente web tiene 8 h (main.tf:162) y web/src/auth tampoco renueva (grep sin resultados), así que la consola también dura ~60 min.

### A-004 · P0 · Web: el WS cierra la sesión a los ~60 min aunque el silent renew funcione

- **Estado:** 🔴 DEFECTO · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.03`
- **Roles:** todos los roles web
- **Evidencia:** api/src/takab_api/routers/ws.py:88-99; shared/sdk-ts/src/live.ts:42-45,156-162,215-225; web/src/live/LiveSocketProvider.tsx:28-29; web/src/shell/AppShell.tsx:10; web/src/auth/session.store.ts:229-239

Cadena medida en el código: el servidor cierra con 4401 al vencer el exp del token del handshake (ws.py:88-99, cierre intencional y documentado en ws.py:12-13); LiveSocket, ante 4401, no reintenta y llama onUnauthorized (live.ts:219-222); la consola conecta onUnauthorized a logout() (LiveSocketProvider.tsx:28-29), que borra la sesión y redirige al /logout de Cognito (session.store.ts:229-239), perdiendo además endedReason. El socket se monta siempre en el shell (AppShell.tsx:10). Hoy la sesión web efectiva es de unos 60 min, no de 8 h. Arreglo: (1) opción nueva en LiveSocket, renewToken?: () => Promise<string|null>: ante 4401, renovar una vez y reconectar, y solo si falla llamar onUnauthorized; (2) reconectar de forma proactiva cuando cambie idToken en el store (addUserLoaded, session.store.ts:131-135); (3) nuevo callback onSessionExpired para el 4440; (4) en web, onUnauthorized → handleUnauthorized() en vez de logout(). En ejecución: NO_MEDIDO.

### A-005 · P0 · Móvil: implementar el refresh (hoy la sesión real dura 60 min)

- **Estado:** 🔴 DEFECTO · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.04`
- **Roles:** brigadista, inspector, security_guard, building_admin, occupant
- **Evidencia:** mobile/src/auth/useAuth.ts:48,76-81,89-116; mobile/src/services/sdk.ts:46-48; mobile/src/live/socket.ts:24; mobile/src/auth/secureTokens.ts:26-33; mobile/src/auth/config.ts:47-55

useAuth.ts guarda refreshToken (líneas 48 y 76-81) y NUNCA lo usa: bootstrapSession manda el idToken guardado (useAuth.ts:96-98), que caduca a los 60 min. /me responde 401, el interceptor ejecuta signOut (sdk.ts:47-48) y el WS hace lo mismo (socket.ts:24). Diseño: refreshSession() de vuelo único (single-flight) con AuthSession.refreshAsync({clientId: POOLS[profile].clientId, refreshToken}, discoveryFor(pool)); config.ts:47-55 ya expone tokenEndpoint. Se llama al arrancar si al idToken le quedan menos de 5 min, al volver la app a primer plano, antes de conectar el WS y ante cualquier 401 que no sea sesion_expirada (un reintento). Persistir el idToken nuevo en SecureStore (secureTokens.ts:26-33; issuedAt pasa a ser la hora del login original). Ante 4401 del socket: refresh + reconectar. Ante sesion_expirada/4440: signOut con motivo visible en login.tsx. signOut debería además revocar el refresh token en revocationEndpoint (config.ts:55, hoy sin uso). Es requisito previo de los 30 días para brigadista, inspector y occupant.

### A-006 · P0 · auth_time al refrescar: no documentado por AWS (todo el tope por rol depende de ello)

- **Estado:** ❔ NO MEDIDO · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.02`
- **Roles:** security_guard, building_admin, roles web
- **Evidencia:** api/src/takab_api/auth/mfa.py:14-19,85-88; takab-docs/specs/cognito-pool-v1.md:195-197

La doc de Cognito define auth_time como 'The authentication time … that your user completed authentication' y su ejemplo tiene auth_time == iat (login fresco); NO dice qué pasa en un ID token emitido con el grant refresh_token. OIDC Core §12.2 (de memoria; no pude descargarla en esta sesión) exige que auth_time sea el de la autenticación original. Lo que AWS SÍ confirma: el refresh token caduca contando desde el sign-in y, con rotación, 'the new refresh token is valid for the remaining duration of the original'. Por tanto la validez por client ya es un tope absoluto, pero por CLIENT, no por rol. Si auth_time se renovara en cada refresh, el tope por rol de la API no se dispararía nunca, y security_guard/building_admin (mobile_tactical) y los roles web (si web = 30 d) heredarían 30 d. Alternativa si falla: registro en servidor del primer uso por origin_jti (ligado al refresh token según AWS; requiere enable_token_revocation), topando por rol desde ese primer uso.

### A-007 · P0 · La app móvil nunca renueva el token: la sesión dura unos 60 min y luego vuelve a pedir contraseña (y MFA a los tácticos)

- **Estado:** 🔴 DEFECTO · **Dimensión:** RBAC y flujos · **Ficha:** `T-8.04`
- **Roles:** occupant, brigadista, security_guard, inspector, building_admin
- **Evidencia:** mobile/src/auth/useAuth.ts:36-48,76-81,89-117; mobile/src/services/sdk.ts:46-49; mobile/src/live/socket.ts:3,24; api/src/takab_api/routers/ws.py:84-100; infra/terraform/modules/identity/main.tf:629-637,665-673; takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md:414-417,668-669

exchangeAndResolve guarda refreshToken en SecureStore, pero ningún código lo usa: en mobile/src no hay refreshAsync ni grant refresh_token. El ID token dura 60 min. Al caducar, cualquier 401 hace signOut() en el interceptor, el WS cierra con 4401 al llegar al exp y también hace signOut, y bootstrapSession reutiliza el idToken guardado sin renovarlo. Resultado: el refresh de 90 días (ocupantes) y el de 24 h (tácticos) son letra muerta. Contradice la spec móvil §8 («sesión de ocupante de larga vida… la app debe alertar sin pedir login») y tu petición de 1 mes. Acción: implementar AuthSession.refreshAsync contra el endpoint /oauth2/token de cada pool. Renovar antes del exp y, ante un 401, intentar refrescar una vez antes de hacer signOut. Aplicar lo mismo al WS (reconectar con el token nuevo).

### A-008 · P0 · Petición: 30 días sin contraseña ni MFA para brigadista, inspector y ocupante; 1 día para el resto. Estado actual y cómo cumplirlo

- **Estado:** ⬜ FALTA · **Dimensión:** RBAC y flujos · **Ficha:** `T-8.05`
- **Roles:** todos
- **Evidencia:** infra/terraform/modules/identity/main.tf:42,142-168,535,611-643,645-679; web/src/auth/userManager.ts:24-26; api/src/takab_api/auth/mfa.py:18,29,85-96,115; api/src/takab_api/auth/deps.py:71-99; takab-docs/RBAC-TAKAB.md:363-378

Hoy:
· Web: cliente takab-web, refresh de 8 h y userStore en sessionStorage (cerrar la pestaña obliga a volver a entrar).
· Táctico móvil: mobile_tactical, 24 h, sin usar.
· Ocupante: mobile_occupants, 90 días, sin usar.
La duración del refresh en Cognito es por app client, no por rol. mobile_tactical lo comparten 4 roles (brigadista, security_guard, inspector, building_admin) y takab-web los 7 roles web (el inspector también es web).
Camino compatible con la regla de oro 8: require_mfa comprueba de qué pool viene el token, no su frescura (mfa.py §4 lo declara), así que un refresh largo no rompe la guarda de comandos. Recordar dispositivos (device_configuration) está vetado por mfa.tftest.hcl.
Propuesta:
(a) refresh_token_validity = 30 d en takab-web y mobile_tactical, y 30 d (o dejar 90) en ocupantes.
(b) Un tope por rol en la API (get_claims) y en los clientes, usando el claim auth_time del ID token: 30 d para brigadista, inspector y occupant; 24 h para el resto.
(c) Web: pasar userStore a localStorage para que el día no se pierda al cerrar la pestaña.
(d) Implementar el refresh en móvil (item anterior).
Antes hace falta un D-xx: main.tf:646 y la spec §8 dicen «refresh corto — las acciones tácticas re-verifican token».

### A-009 · P0 · La sesión móvil NO se renueva: el refresh token se guarda y nunca se usa

- **Estado:** 🔴 DEFECTO · **Dimensión:** Funciones básicas · **Ficha:** `T-8.04`
- **Roles:** occupant, brigadista, security_guard, inspector, building_admin
- **Evidencia:** mobile/src/auth/useAuth.ts:48,76-81,88-117; mobile/src/auth/secureTokens.ts:25-32; mobile/src/services/sdk.ts:46-48; mobile/src/auth/session.store.ts:41-45; takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md:414-417,668-669

DEFECTO, verificado leyendo el código. `exchangeAndResolve` guarda `refreshToken` en el almacén seguro, pero ningún archivo de mobile/src lo usa para renovar (no hay refreshAsync ni grant_type=refresh_token). `bootstrapSession` reusa el idToken guardado. Pasados los 60 min que vive el id_token, `/me` responde 401, el interceptor llama a `signOut()` y se vuelven a pedir contraseña y MFA. Esto contradice la especificación de la app («sesión de ocupante de larga vida… la expiración del refresh NO bloquea la pantalla de crisis») y lo que pide el usuario (30 días sin contraseña ni MFA para brigadista, inspector y ocupante). Riesgo de seguridad de vida: un ocupante con la sesión caída abre la app en plena alerta y ve el login. NO_MEDIDO en el Pixel: qué pasa con el push después del signOut. Acción: renovar con AuthSession.refreshAsync antes de cada petición cuando el id_token esté por vencer y al arrancar, y cerrar sesión solo si la renovación falla con invalid_grant.

### A-010 · P1 · Duración de sesión actual frente a la política pedida (1 mes tácticos/ocupante, 1 día el resto)

- **Estado:** ⬜ FALTA · **Dimensión:** Web · MONITOREO/EVALUACIÓN · **Ficha:** `T-8.03`
- **Roles:** todos
- **Evidencia:** web/src/auth/userManager.ts:24-26; web/src/auth/session.store.ts:136-139; infra/terraform/modules/identity/main.tf:42,142-168,611-637,647-673; api/src/takab_api/auth/mfa.py:85-87

Hoy: cliente takab-web con access/id de 60 min y refresh de 8 HORAS; el UserManager guarda en sessionStorage (la sesión muere al cerrar la pestaña) con automaticSilentRenew. Pool principal con mfa_configuration=ON: cada login nuevo pide TOTP. Cliente móvil táctico: refresh de 24 h. Ocupantes: refresh de 90 días con MFA OPTIONAL. La API no exige frescura de auth_time (mfa.py lo deja como decisión de producto), así que la vigencia del refresh token decide cuánto tiempo no se pide MFA. Para '1 día' en web: refresh_token_validity=24 h en aws_cognito_user_pool_client.web, y pasar el userStore a localStorage (si no, cerrar la pestaña obliga a volver a entrar). Limitación: la vigencia es POR APP CLIENT, no por rol. El inspector usa takab-web y mobile_tactical, y mobile_tactical también lo usan security_guard y building_admin, que según la petición deberían durar 1 día. Hace falta separar app clients (p.ej. mobile_field_30d para brigadista e inspector) o hacer un control por rol en la API.

### A-011 · P1 · El acuse se lanza sin esperar respuesta: los errores se tragan y el botón dice EJECUTADO igual

- **Estado:** 🔴 DEFECTO · **Dimensión:** Web · MONITOREO/EVALUACIÓN · **Ficha:** `T-8.07`
- **Roles:** takab_superadmin, tenant_admin, soc_operator, gov_operator
- **Evidencia:** web/src/features/console/ConsolePage.tsx:191-201; web/src/features/console/IncidentTable.tsx:352-363; web/src/components/ConfirmButton.tsx:72-77; api/src/takab_api/routers/incidents_ack.py:56-66,99-101

onAck llama ackIncidentIncidentsIncidentIdAckPost sin throwOnError ni revisar {error, response}: el cliente hey-api no lanza excepción, así que un 403/404/409/500 se descarta en silencio. ConfirmButton.fire() pinta 'EJECUTADO' en cuanto se confirma, sin esperar la promesa. No hay estado pending, así que se puede re-acusar 1.5 s después; la API responde 409 'ya no está abierto' y también se pierde. Además la cola no muestra el estado de cada fila (ver el item de la columna ESTADO), así que el operador no puede comprobar en la tabla si el acuse entró. Acción: useMutation con throwOnError, deshabilitar mientras está pendiente, mostrar el error y resultado 'ACUSADO' solo tras 200; que ConfirmButton reciba pending/estado real.

### A-012 · P1 · La selección de la cola es por SITIO, no por incidente: con 2+ incidentes abiertos en un sitio se actúa sobre el equivocado

- **Estado:** 🔴 DEFECTO · **Dimensión:** Web · MONITOREO/EVALUACIÓN · **Ficha:** `T-8.07`
- **Roles:** takab_superadmin, tenant_admin, soc_operator, gov_operator
- **Evidencia:** web/src/features/console/ConsolePage.tsx:90-95,323-324; web/src/features/console/IncidentTable.tsx:248-253; db/schema.sql:311; web/src/features/console/useLiveIncidents.ts:69

Hacer clic en una fila llama openDetail(incident.site_id); focusIncident = incidents.find(i => i.site_id === focusSiteId), es decir, el PRIMERO del sitio. selectedId (fila resaltada y objetivo de ACUSE, REUBICAR y SOLICITAR DICTAMEN) sale de focusIncident. La base no impide varios incidentes abiertos por sitio (solo un índice no único), y la cola incluye open, acked e in_review. Si hay dos en el mismo sitio (p.ej. pánico + sísmico), la segunda fila no se puede seleccionar y el acuse cae en la primera. Acción: guardar selectedIncidentId aparte de selectedSiteId.

### A-013 · P1 · El Modal le roba el foco a los campos cada segundo en /console

- **Estado:** 🔴 DEFECTO · **Dimensión:** Web · MONITOREO/EVALUACIÓN · **Ficha:** `T-8.07`
- **Roles:** superadmin, tenant_admin, soc_operator (reubicar); todos los de /console (comparativa, historial); superadmin, tenant_admin (simulacro)
- **Evidencia:** web/src/components/Modal.tsx:18-28; web/src/features/console/ConsolePage.tsx:62,346-354,357-371; web/src/features/console/DrillControls.tsx:54-65; web/src/lib/useNow.ts

Modal ejecuta dialogRef.current.focus() dentro de un useEffect con deps [onClose]. ConsoleWall se redibuja cada 1 s (useNow(1000)) y pasa onClose como arrow inline a EpicenterModal y ComparePanel. DrillControls (hijo sin memo) también pasa arrows inline a DrillModal y DrillHistory. Resultado: cada segundo cambia la identidad de onClose, el efecto se re-ejecuta y el foco salta del input (LAT, LON MANUAL, NOTA, nombre de plantilla, fecha) o del select de la comparativa al contenedor del diálogo. Escribir en esos modales sería prácticamente imposible. No hay test de foco en Modal.test.tsx. Acción: separar el focus inicial (efecto con []) del listener de Esc (guardar onClose en un ref), o envolver los onClose en useCallback.

### A-014 · P1 · El botón DESCARGAR CLIP no hace nada

- **Estado:** 🔴 DEFECTO · **Dimensión:** Web · MONITOREO/EVALUACIÓN · **Ficha:** `T-8.08`
- **Roles:** takab_superadmin, tenant_admin, soc_operator, building_admin
- **Evidencia:** web/src/features/triage/CctvPanel.tsx:133-140; web/src/features/triage/TriagePage.tsx:239-265 (sin onDownloadClip); web/src/features/triage/TriageDetail.tsx:121,344; api/src/takab_api/routers/cctv.py:66-75

CctvPanel pinta 'DESCARGAR CLIP' si canDownloadClip (cctv_video) y llama onDownloadClip?.(clip_id). TriagePage pasa canDownloadClip pero NUNCA onDownloadClip a TriageDetail, así que el optional chaining no hace nada. El endpoint existe (POST /cctv/clips/{clip_id}/download, URL prefirmada de 300 s con auditoría) y está en el SDK, pero ningún código web lo llama. Acción: crear una mutación con openPendingDownload(), igual que downloadEvidence, y pasarla desde TriagePage.

### A-015 · P1 · La firma solo aparece si ya hay un dictamen previo; la API permite firmar el primero

- **Estado:** 🟠 SOSPECHA · **Dimensión:** Web · MONITOREO/EVALUACIÓN · **Ficha:** `T-8.08`
- **Roles:** inspector
- **Evidencia:** web/src/features/triage/TriageDetail.tsx:479-547; api/src/takab_api/routers/dictamens.py:72-97

El bloque 'Firma del dictamen' (select de status + ConfirmButton FIRMAR DICTAMEN) está dentro de {verdict && head && …}. Sin cabeza de cadena se pinta 'SIN DICTAMEN REGISTRADO' y el inspector no tiene con qué firmar. POST /incidents/{id}/dictamens acepta head=None (supersedes=None). Si la pasada automática no generó el preliminar (worker caído, ventana vencida, incidente manual), el inspector que llega por el correo de dictamen_request no puede firmar desde la web. NO_MEDIDO: no puedo confirmar estáticamente que siempre exista un preliminar. Acción: mostrar la firma también con head === null.

### A-016 · P1 · El simulacro de takab_superadmin con selección vacía apunta a gabinetes de TODOS los tenants

- **Estado:** 🟠 SOSPECHA · **Dimensión:** Web · MONITOREO/EVALUACIÓN · **Ficha:** `T-8.07`
- **Roles:** takab_superadmin
- **Evidencia:** web/src/features/console/DrillModal.tsx:298,381; api/src/takab_api/routers/drills.py:66-70,470-498,520-528; api/src/takab_api/routers/_common.py:122-141; db/schema.sql:887-889

La UI dice 'SIN SELECCIÓN ⇒ TODOS LOS SITIOS CON GABINETE COMANDABLE DEL TENANT'. En la API, sin site_ids ni plantilla, targets = list(commandable) con _COMMANDABLE_SITES, que no filtra por tenant y corre bajo la RLS, que para roles internos abre todas las filas. La fila drills se inserta con claims.tenant_id y los comandos con el tenant de cada sitio. POST /drills no usa resolve_write_tenant (que exige tenant explícito a los internos). Además GET /sites en el modal lista sitios de todos los clientes. No encontré test de superadmin en api/tests/api/test_drills*.py. NO_MEDIDO en ejecución. Acción: exigir tenant_id explícito a roles internos, o limitar a un tenant elegido.

### A-017 · P1 · gov_operator ve una alerta roja permanente 'VENTANAS DE MANTENIMIENTO SIN LECTURA'

- **Estado:** 🔴 DEFECTO · **Dimensión:** Web · flota/tenants/edificio · **Ficha:** `T-8.09`
- **Roles:** gov_operator
- **Evidencia:** web/src/features/fleet/FleetPage.tsx:257-269; web/src/features/console/useMaintenanceWindows.ts:27-38,78-90,125-126; web/src/features/scene/SceneStrip.tsx:119; api/src/takab_api/routers/maintenance.py:114-116,489-493; api/src/takab_api/auth/matrix.py:78

GET /maintenance-windows solo lo pueden leer WINDOW_ROLES + soc_operator + takab_support. gov_operator entra a /fleet, recibe 403 (MaintenanceReadForbidden) y FleetPage pinta el aviso con role=alert solo mirando readError, sin revisar `maintenance.forbidden`. SceneStrip sí lo revisa. Resultado: 'PUEDE HABER GABINETES CON LA ALARMA MUDA Y SIN RÓTULO' + REINTENTAR VENTANAS, que siempre volverá a dar 403. Arreglo: condicionar a `maintenance.readError !== null && !maintenance.forbidden`, o no montar el hook sin permiso. Añadir un test con ME_FIXTURES.gov_operator.

### A-018 · P1 · La tarjeta 'Usuarios del cliente' muestra los usuarios de TODOS los clientes cuando la ve un rol interno

- **Estado:** 🔴 DEFECTO · **Dimensión:** Web · flota/tenants/edificio · **Ficha:** `T-8.09`
- **Roles:** takab_superadmin
- **Evidencia:** web/src/features/tenants/UsersCard.tsx:84,118,151; web/src/features/tenants/useUsers.ts:65-93; api/src/takab_api/routers/users.py:219-246; api/src/takab_api/schemas/users.py:71-86

GET /users solo filtra por tenant para roles no internos. Para takab_superadmin devuelve la página del pool completo. UsersCard recibe `tenant` pero pinta data.users sin filtrar por user.tenant_id, aunque el subtítulo dice 'QUIÉN ENTRA A {cliente}'. El comentario de useUsers ('el servidor ya acota') no aplica a roles internos. Arreglo: filtrar por tenant.tenant_id en el cliente, o pedir ?tenant_id al servidor.

### A-019 · P1 · Después de SILENCIAR SIRENA el panel dice 'SIRENA SONANDO · ACUSADA POR EL EDGE'

- **Estado:** 🔴 DEFECTO · **Dimensión:** Web · flota/tenants/edificio · **Ficha:** `T-8.09`
- **Roles:** takab_superadmin, tenant_admin, building_admin
- **Evidencia:** web/src/features/building/useSirenTest.ts:48-60,106-110,123-130; web/src/features/building/SirenTestPanel.tsx:18-25,63-77; web/src/features/building/SirenTestPanel.test.tsx:86-89

phaseOf solo mira command.status, no command.action. deactivate reemplaza el commandId y, al recibir el acuse, la fase vuelve a 'acked', que se muestra como 'SIRENA SONANDO' en rojo y ofrece otra vez SILENCIAR SIRENA. Mientras está pendiente dice 'COMANDO EMITIDO · ESPERANDO ACUSE'. Frente al cliente, la pantalla afirma lo contrario de lo que pasó. Hay que separar las fases por acción (p. ej. 'SIRENA SILENCIADA · ACUSADA'). No hay test del estado posterior a deactivate. Además, al recargar la página se pierde commandId y el panel dice 'SIRENA EN REPOSO' sin saberlo realmente.

### A-020 · P1 · El logout no revoca el refresh, no cierra la cookie de la Hosted UI ni da de baja el token push

- **Estado:** 🔴 DEFECTO · **Dimensión:** Móvil · **Ficha:** `T-8.04`
- **Roles:** todos los móviles
- **Evidencia:** mobile/src/auth/session.store.ts:41-45; mobile/src/auth/config.ts:22; mobile/src/auth/config.ts:45-57; api/src/takab_api/routers/mobile_me.py:109; mobile/src/features/account/AccountScreen.tsx:107

signOut sólo borra SecureStore y el estado (session.store.ts:41-45). LOGOUT_URI, revocationEndpoint y endSessionEndpoint están definidos (config.ts:22,48-56) pero no se usan.

Efectos:
- El refresh token sigue vivo en Cognito (grave con 30 días).
- La cookie de la Hosted UI sobrevive y el siguiente «INICIAR SESIÓN» entra con la identidad anterior. Está medido en el Pixel según la memoria correr-los-e2e-en-el-pixel §2, que run.sh esquiva abriendo /logout.
- El token push sigue ligado al usuario y al sitio: el endpoint DELETE /me/push-tokens/{id} existe (mobile_me.py:109) y nadie lo llama.

Arreglo, en este orden y todo best-effort:
1. DELETE del push token propio.
2. AuthSession.revokeAsync({token: refreshToken, clientId}, discovery).
3. WebBrowser.openAuthSessionAsync(`https://${domain}/logout?client_id=…&logout_uri=takab://auth/logout`).
4. clearSession.

Cerrar sesión por un 401 'dead' NO debe dar de baja el push: ahí interesa que el teléfono siga despertando.

### A-021 · P1 · Pestaña CUENTA sin red o con /me/profile caído: sin botón de cerrar sesión ni de reintentar

- **Estado:** 🔴 DEFECTO · **Dimensión:** Móvil · **Ficha:** `T-8.11`
- **Roles:** todos los móviles
- **Evidencia:** mobile/src/features/account/AccountScreen.tsx:95-101; mobile/src/ui/StateFrame.tsx:59-76; mobile/src/auth/pestanasTacticas.ts:31

AccountScreen envuelve TODA la pantalla en StateFrame con error='No se pudo cargar su perfil.' y sin onRetry. El estado error sustituye a los children (StateFrame.tsx:59-76), así que desaparecen CERRAR SESIÓN, Vincular, Permisos y Privacidad.

El propio pestanasTacticas.ts:31 dice que CUENTA es «sin ella no hay forma de cerrar sesión ni de reintentar». Con el arranque en frío sin red (me=null, sin caché de perfil) es un callejón real.

Arreglo: pintar sólo la tarjeta PERFIL como error o retenida, y dejar siempre visibles las filas locales y el logout.

### A-022 · P1 · «VER DICTAMEN DE REINGRESO» lleva a «Sin incidente activo» después del cierre automático D-33

- **Estado:** 🔴 DEFECTO · **Dimensión:** Móvil · **Ficha:** `T-8.11`
- **Roles:** brigadista, security_guard, inspector, building_admin
- **Evidencia:** api/src/takab_api/routers/mobile_site.py:275-284; mobile/src/app/(brigadista)/panel.tsx:210-221; mobile/src/features/panel/PanelView.tsx:119-128; mobile/src/app/dictamen.tsx:22-24; mobile/src/app/dictamen.tsx:98-102; mobile/tests/app/dictamen-states.test.tsx:69

Desde D-33 el motor cierra el incidente unos 3 s después de firmar el dictamen (memoria correr-los-e2e §4). mobile-state devuelve entonces incident=None con reentry.dictamen_signed=true (mobile_site.py:275-284, bloque T-7.55).

PanelView pinta el botón porque dictamenSigned=true (panel.tsx:210, PanelView.tsx:119-128). Pero dictamen.tsx toma incidentId de state.incident (dictamen.tsx:24) y muestra el vacío «Sin incidente activo: no hay dictamen que consultar» (dictamen.tsx:98-102).

Resultado: brigadista, security_guard, inspector y building_admin no pueden descargar el PDF que la RBAC §3 les concede (✅ PDF). Ningún test cubre este caso: dictamen-states.test.tsx sólo usa incidente abierto.

Arreglo: añadir incident_id a MobileReentryOut (desde REENTRY_STILL_DECLARED) y usarlo en dictamen.tsx cuando incident sea null.

### A-023 · P1 · La revisión «USAR ESTA FOTO / Repetir» muestra el visor en vivo, no la foto tomada

- **Estado:** 🔴 DEFECTO · **Dimensión:** Móvil · **Ficha:** `T-8.11`
- **Roles:** brigadista, security_guard, inspector
- **Evidencia:** mobile/src/app/camera.tsx:124; mobile/src/app/camera.tsx:168-185; mobile/src/app/camera.tsx:299-318; mobile/src/features/forensic/capture.ts

take() guarda shot.uri en photoUri (camera.tsx:173-176), pero photoUri sólo se usa como bandera (camera.tsx:265 y 299). La vista que se compone y sella monta un <CameraView> NUEVO en vivo (camera.tsx:309-310), no un <Image source={{uri: photoUri}}>.

Lo que se hornea y se hashea es el fotograma que haya en el visor en el instante de «USAR ESTA FOTO»; la foto disparada se descarta. «Repetir» engaña: la persona cree revisar una toma fija.

NO_MEDIDO: si view-shot de un CameraView (SurfaceView) en el Pixel da píxeles reales o negro. La memoria sólo acredita que la evidencia se sube con sha256, no qué contiene.

Arreglo: dentro de composeRef, <Image source={{uri: photoUri}}/> más la marca de agua.

### A-024 · P1 · El check-in delegado (verify-*) no se encola sin red, y el E2E 05b lo acredita de forma vacía

- **Estado:** 🔴 DEFECTO · **Dimensión:** Móvil · **Ficha:** `T-8.11`
- **Roles:** brigadista, security_guard, building_admin
- **Evidencia:** mobile/src/app/(brigadista)/lista.tsx:112-139; mobile/src/offline/queue.ts:22-33; mobile/src/app/(brigadista)/sync.tsx:86; mobile/src/app/(brigadista)/sync.tsx:120; mobile/.maestro/05b-offline-cola.yaml:11-27

markVerified hace un POST directo (lista.tsx:112-139). Sin red muestra «No se pudo verificar…», no encola nada. CheckinPayload ni siquiera tiene subject_user_id (queue.ts:22-33).

.maestro/05b-offline-cola.yaml:11-27 declara «Sin red, esto tiene que quedar encolado» y comprueba el texto '.*PENDIENTE.*'. Esa regex casa SIEMPRE con la cabecera de SYNC «SINCRONIZACIÓN · N PENDIENTE(S)» (sync.tsx:86), aunque N sea 0, y con el contador «PENDIENTES» (sync.tsx:120). El flujo sale verde sin probar el encolado.

Arreglo: añadir subject_user_id al payload del check-in, encolar el delegado y comprobar en el E2E un item concreto (testID sync-<id>).

### A-025 · P1 · En teléfono compartido la cola offline, el onboarding y el consentimiento GPS no tienen dueño

- **Estado:** 🟠 SOSPECHA · **Dimensión:** Móvil · **Ficha:** `T-8.18`
- **Roles:** todos los móviles (crítico security_guard por turnos)
- **Evidencia:** mobile/src/offline/queue.ts:68-87; mobile/src/offline/OfflineSyncGate.tsx:18-25; mobile/src/services/onboarding.ts; mobile/src/auth/secureTokens.ts:73-80; mobile/src/services/mySite.ts

QueueItemBase no guarda el sub del autor (queue.ts:68-87). clearSession no toca la cola, y OfflineSyncGate drena con el token de quien entre después (OfflineSyncGate.tsx:18-25). Un check-in o reporte pendiente del usuario A se enviaría como el usuario B.

ONBOARDING_KEY y GPS_CONSENT_KEY son del dispositivo (onboarding.ts) y clearSession no los borra (secureTokens.ts:73-80). El siguiente usuario hereda el consentimiento GPS de otro, que es personal (LFPDPPP), y se salta aviso y enrolamiento.

Es realista con guardias por turno. Arreglo: sellar el sub en cada item y drenar sólo los del sub vigente; guardar onboarding y consentimiento por sub, igual que T-2.114 hizo con el sitio vigilado.

### A-026 · P1 · Tabla SESSION_MAX_AGE_S por rol en la matriz ejecutable

- **Estado:** ⬜ FALTA · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.02`
- **Roles:** todos
- **Evidencia:** api/src/takab_api/auth/matrix.py:68-71; api/tests/auth/test_matrix.py:53

Añadir en api/src/takab_api/auth/matrix.py un dict SESSION_MAX_AGE_S: brigadista, inspector, occupant = 30*86400; takab_superadmin, takab_support, tenant_admin, soc_operator, gov_operator, building_admin, security_guard = 86400. Con un censo que exija que las claves sean exactamente los 10 roles de ROLE_ROUTE_MATRIX (un rol nuevo entra en rojo). Espejarla en RBAC-TAKAB.md (sección nueva §5.x 'Duración de sesión por rol') y añadir un test gemelo de test_route_matrix_matches_rbac_section_2 que cruce la tabla del doc con la del código.

### A-027 · P1 · Exigir auth_time en la verificación y guardarlo en Claims

- **Estado:** ⬜ FALTA · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.02`
- **Roles:** todos
- **Evidencia:** api/src/takab_api/auth/tokens.py:68-77; api/src/takab_api/auth/claims.py:47-90; takab-docs/specs/cognito-pool-v1.md:195

tokens._decode hoy exige solo exp/iat: options={'require': ['exp','iat']} (tokens.py:76). Añadir 'auth_time' a esa lista, porque Cognito lo emite siempre en el ID token (doc AWS 'ID token default payload'). NO recurrir a iat cuando falte: iat se renueva en cada refresh y el tope no se dispararía nunca. Añadir el campo auth_time:int a Claims (claims.py:47-63) y rellenarlo en from_verified (claims.py:81-90), para que el WS pueda calcular el plazo sin decodificar otra vez.

### A-028 · P1 · Punto exacto del tope: función enforce_session_age llamada desde get_claims

- **Estado:** ⬜ FALTA · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.02`
- **Roles:** todos
- **Evidencia:** api/src/takab_api/auth/deps.py:46,71-99; api/src/takab_api/auth/mfa.py:132-150; api/src/takab_api/routers/commands.py:104

Nuevo módulo api/src/takab_api/auth/session_age.py con session_deadline(claims) = auth_time + SESSION_MAX_AGE_S[role] y enforce_session_age(claims, now). Si now >= deadline lanza AuthError('sesion_expirada'); un rol desconocido cuenta como caducado (default-deny). Se llama en deps.get_claims DESPUÉS del ancla pool→rol (deps.py:91-94), dentro del mismo try, así que sale como 401 por el except existente (deps.py:96-99). La cabecera se vuelve distinguible: WWW-Authenticate: Bearer error="invalid_token", error_description="sesion_expirada" (RFC 6750). Solo en este caso; los demás 401 conservan _BEARER_CHALLENGE (deps.py:46). La API es same-origin (web/vite.config.ts:22, sin CORS), así que el interceptor puede leer la cabecera sin consumir el body. Convivencia con MFA: require_mfa envuelve get_claims (mfa.py:144; commands.py:104; updates.py:57; rollouts.py:67), por eso una sesión vieja da 401 (volver a entrar) antes que el 403 por falta de MFA. Es el orden correcto y mfa.py no necesita cambiar de código. Grep medido: solo hay dos sitios que decodifican tokens (deps.py:86 y ws.py:125); no hay un tercer camino que se salte el tope.

### A-029 · P1 · WS: plazo = min(exp, auth_time+max_age) y código de cierre propio

- **Estado:** ⬜ FALTA · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.02`
- **Roles:** soc_operator, gov_operator, tenant_admin, takab_*, inspector, building_admin, brigadista, security_guard
- **Evidencia:** api/src/takab_api/routers/ws.py:37,80-82,88-99,113-130

ws._authenticate (ws.py:113-130) debe aplicar enforce_session_age y devolver deadline=min(exp, session_deadline). Una sesión caducada en el handshake cierra con el nuevo código 4440 'sesion_expirada' (hoy todo es 4401, ws.py:37). En el bucle (ws.py:88-99): si el plazo que se alcanza es el de la sesión, cerrar con 4440 (el cliente NO debe reintentar); si es el exp del ID token, mantener 4401, pero ver el cambio del cliente WS (reintentar con token renovado). Nota: ws.py:125 usa decode_verify (solo el pool principal); es correcto porque el occupant se rechaza en el handshake (ws.py:80-82). Actualizar el docstring de ws.py:1-14 y la constante en shared/sdk-ts/src/live.ts:67.

### A-030 · P1 · Móvil: la caducidad de la sesión no debe tapar la pantalla de crisis

- **Estado:** 🟠 SOSPECHA · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.18`
- **Roles:** occupant, brigadista
- **Evidencia:** mobile/src/app/crisis.tsx:60-61; mobile/src/auth/secureTokens.ts:71-79; takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md:414-418; api/src/takab_api/routers/mobile_me.py:109

crisis.tsx:60-61 redirige a '/' (y de ahí al login) si status !== 'authenticated'. Un 401 durante un incidente, o abrir la app desde una push más de 60 min después del login (ver el item del refresh), deja al ocupante en el login y no en la crisis. Contradice la aceptación §0.1 de la especificación móvil ('expiración del refresh NO bloquea la pantalla de crisis si hay incidente activo cacheado <15 min'). Diseño: estado de sesión nuevo 'expired', distinto de 'anonymous', que permita las pantallas de crisis y alarma con datos retenidos y el aviso 're-autentíquese al tocar'. No borrar WATCHED_SITE_KEY (secureTokens.ts:78-79) hasta que entre otro usuario. Y el servidor NO debe borrar push tokens cuando caduca una sesión (hoy signOut no llama DELETE /me/push-tokens, y eso hay que conservarlo). En ejecución: NO_MEDIDO.

### A-031 · P1 · Terraform: validez del refresh por app client

- **Estado:** ⬜ FALTA · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.05`
- **Roles:** todos
- **Evidencia:** infra/terraform/modules/identity/main.tf:142-168,611-643,647-679; infra/terraform/envs/dev/.terraform.lock.hcl:5

infra/terraform/modules/identity/main.tf. (a) mobile_tactical (665-673): refresh_token_validity 24 'hours' → 30 'days'. Cubre a brigadista e inspector; security_guard y building_admin quedan en 24 h por el tope de la API. (b) mobile_occupants (629-637): 90 → 30 días, para que cuadre con el tope de 30 d del occupant (si la API topa a 30 d, dejar 90 en Cognito solo añade refresh tokens que la API rechaza). (c) web (160-168): 8 'hours' → 24 'hours' (opción recomendada B: el inspector tiene 30 d solo en móvil) o → 30 'days' (opción A: el inspector tiene 30 d también en web y la API topa al resto a 24 h). AWS acepta de 60 min a 10 años (doc 'Refresh tokens'). Opcional: declarar enable_token_revocation=true de forma explícita (garantiza origin_jti) y valorar refresh_token_rotation. Si se activa la rotación, AWS la declara incompatible con ALLOW_REFRESH_TOKEN_AUTH; retirarlo sigue pasando la aserción 8 de mfa.tftest.hcl:184-190 (usa setsubtract). Si provider 6.53.0 soporta el bloque de rotación: NO_MEDIDO (confirmar con terraform validate).

### A-032 · P1 · Web: persistencia de la sesión (sessionStorage vs localStorage)

- **Estado:** ⬜ FALTA · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.03`
- **Roles:** roles web + inspector
- **Evidencia:** web/src/auth/userManager.ts:13-27; web/src/features/fleet/GatewayAcuse.tsx:79; takab-docs/DECISIONES-MAURICIO.md:924-925

userManager.ts:24 usa WebStorageStateStore({store: window.sessionStorage}): la sesión vive por pestaña, y cerrar la pestaña o el navegador la pierde. Abrir otra pestaña entra al Hosted UI; según la doc de AWS la cookie del login gestionado dura 1 h, así que pasada esa hora vuelve a pedir contraseña y TOTP. Opción 1 (mantener sessionStorage): menos riesgo, pero NO cumple '1 día' fuera de la pestaña. Opción 2 (localStorage): cumple, pero expone el refresh token (24 h / 30 d) a cualquier XSS en una consola pública (D-22) donde no se encontró ninguna CSP en el repo. Recomendación: localStorage + CSP estricta (response headers del hosting) + revokeTokensOnSignout:true en oidc-client-ts + revisar si la rotación es compatible con varias pestañas. Actualizar el comentario 'refresh token (8 h en el pool)' (userManager.ts:25) y el razonamiento de GatewayAcuse.tsx:79, que asume sessionStorage.

### A-033 · P1 · Web: el arranque descarta sesiones con access token vencido aunque haya refresh

- **Estado:** ⬜ FALTA · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.03`
- **Roles:** roles web
- **Evidencia:** web/src/auth/session.store.ts:142-165

runBootstrap solo acepta 'user && !user.expired && user.id_token' (session.store.ts:154); si no, llama clearSession(). Con persistencia en localStorage, reabrir el navegador más de 60 min después cae al login aunque el refresh siga vivo. Cambio: si user.expired && user.refresh_token, intentar await getUserManager().signinSilent() antes de declarar anónimo; si responde sesion_expirada, ir al login con el motivo.

### A-034 · P1 · Web: mostrar 'sesión expirada por tope' distinto del 401 genérico

- **Estado:** 🔷 MEJORA · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.03`
- **Roles:** roles web
- **Evidencia:** web/src/auth/session.store.ts:54-66,242-254; web/src/auth/apiClient.ts:26-31; web/src/auth/me.ts:7-18; web/src/pages/LoginPage.tsx:114-128; web/src/app/RequireSession.tsx:25-34

Ya existe endedReason 'expired' (session.store.ts:66, 242-254) y el aviso en LoginPage.tsx:123-128 ('SU SESIÓN SE CERRÓ · expiró o fue revocada'). Ampliar: endedReason 'expired' | 'max_age'. handleUnauthorized(reason) recibe el motivo desde apiClient.ts:26-31 (leer response.headers.get('WWW-Authenticate') y buscar error_description="sesion_expirada") y desde me.ts:7-18 (MeRequestError con reason). Con 'max_age' NO intentar signinSilent (Cognito seguiría refrescando y la API rechazaría en bucle): removeUser() y mostrar 'SU SESIÓN DE 24 H TERMINÓ · vuelva a entrar con contraseña y código' (30 días para el inspector si opción A). RequireSession.tsx:32-34 no cambia (ya redirige a '/' con returnTo). DegradedSessionScreen no cambia: solo cubre fallos de /me que no son 401. Hay que decirlo en el comentario para que nadie enchufe ahí la expiración. Añadir en Topbar un aviso previo ('su sesión vence en 30 min · renovar ahora') a partir de session_expires_at.

### A-035 · P1 · Fábricas de tokens de test y /dev/token deben emitir auth_time

- **Estado:** ⬜ FALTA · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.02`
- **Roles:** n/a
- **Evidencia:** api/tests/auth_utils.py:81-120; api/src/takab_api/routers/dev_token.py:27-43,73-88

Ni api/tests/auth_utils.py::_base_claims (97-114) ni routers/dev_token.py (73-88) emiten auth_time. Si se exige, TODA la suite de la API y los e2e de la web (web/e2e/helpers.ts usa /dev/token) darán 401. Cambio: auth_time = now - auth_age (parámetro nuevo, default 0) en auth_utils; campo opcional auth_age_s en DevTokenRequest (default 0, tope ≈ 40 d) para simular sesiones cerca del corte en los e2e. Tests nuevos: soc_operator con auth_age 86401 → 401 'sesion_expirada' y cabecera; brigadista con 29 d → 200; occupant del pool de ocupantes con 31 d → 401; token sin auth_time → 401; WS con sesión caducada → 4440.

### A-036 · P1 · Kill switch administrativo para sesiones de 30 días

- **Estado:** 🔷 MEJORA · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.02`
- **Roles:** tenant_admin, takab_superadmin (acción); brigadista/inspector/occupant (afectados)
- **Evidencia:** api/src/takab_api/users/directory.py:382-387

set_enabled(False) solo llama admin_disable_user (directory.py:382-387). Con sesiones de 30 d en teléfonos de brigadistas que silencian sirenas, añadir admin_user_global_sign_out al desactivar y una acción 'Cerrar todas sus sesiones' en UsersCard (web/src/features/tenants/UsersCard.tsx), auditada. Si un usuario desactivado aún puede refrescar: NO_MEDIDO. Aunque no pueda, los ID tokens ya emitidos valen hasta 60 min en la API, porque la API no comprueba revocación.

### A-037 · P1 · D-38 en DECISIONES-MAURICIO.md (con cabecera y reparto)

- **Estado:** ⬜ FALTA · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.05`
- **Roles:** n/a
- **Evidencia:** takab-docs/DECISIONES-MAURICIO.md:14-17,36,1832; api/tests/test_docs_consistency.py:2060-2101

Añadir '## D-38 · Sesión de 30 d para brigadista/inspector/occupant y de 24 h para el resto, tope absoluto desde el login impuesto en la API por auth_time', con las secciones 'El problema', 'Lo decidido', 'El precio, declarado' (MFA una vez al mes en roles con actuadores; ventana de un teléfono robado; XSS si se usa localStorage) y 'Cómo se revocaría'. Además la fila del índice tras la línea 36 y la cabecera (líneas 14-17): '38 decisiones · 32 tomadas por Mauricio (… 2 el 2026-09-22)' o la fecha real. test_docs_consistency.py:2079-2101 exige que cabecera, índice y secciones cuadren, y el test del reparto (≈2106-2190) deriva por fecha y por quién decidió.

### A-038 · P1 · Regla de oro 8: los roles con actuadores mostrarían MFA una vez al mes

- **Estado:** 🟠 SOSPECHA · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.05`
- **Roles:** brigadista, inspector
- **Evidencia:** takab-docs/RBAC-TAKAB.md:345-378; api/src/takab_api/routers/commands.py:84-104; api/src/takab_api/auth/mfa.py:85-96; infra/terraform/modules/identity/tests/mfa.tftest.hcl:168

brigadista e inspector tienen manual_activate (RBAC §4.1, deslizar para activar); brigadista, security_guard y building_admin silencian (RBAC §4.2). La guarda de emisión exige el pool con MFA (commands.py:104, mfa.py:144-147), no frescura. El texto de RBAC §4.3.2 ('MFA obligatorio en el login') se sigue cumpliendo, porque el pool principal sigue en ON (main.tf:42). Pero un teléfono perdido o desbloqueado da 30 d de capacidad de activar y silenciar sin segundo factor. Ninguna acción exige hoy auth reciente, y mfa.py:85-88 lo deja declarado a propósito. Compensaciones propuestas para D-38: step-up biométrico local antes de firmar un comando (expo-local-authentication, o SecureStore con requireAuthentication para el refresh token), kill switch administrativo y que se mantengan rate-limit, nonce y acuse. NO resolverlo encendiendo 'dispositivos recordados': mfa.tftest.hcl:168 lo prohíbe porque se salta el MFA sin que se note en el token (mfa.py:89-96).

### A-039 · P1 · Corte de 24 h en plena emergencia para el SOC

- **Estado:** 🟠 SOSPECHA · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.03`
- **Roles:** soc_operator, gov_operator, tenant_admin, takab_*
- **Evidencia:** api/src/takab_api/auth/mfa.py:85-88; web/src/shell/Topbar.tsx

mfa.py:85-88 ya advierte que exigir auth reciente 'haría que el operador tuviera que volver a autenticarse en plena emergencia'. Un tope absoluto de 24 h hace justo eso a un soc_operator o gov_operator cuyo turno cruza la hora 24 durante un sismo: todas las llamadas dan 401 sesion_expirada y tiene que teclear contraseña y TOTP. Mitigar con el aviso previo (session_expires_at en /me, banner en Topbar) y 'renovar ahora' en un momento tranquilo. Alternativa a decidir: gracia mientras haya un incidente activo (más compleja; afecta la regla de estados explícitos).

### A-040 · P1 · Refresh de larga vida en localStorage de una consola pública sin CSP

- **Estado:** 🟠 SOSPECHA · **Dimensión:** Sesiones por rol · **Ficha:** `T-8.03`
- **Roles:** roles web, inspector
- **Evidencia:** takab-docs/DECISIONES-MAURICIO.md:924-947; web/src/auth/userManager.ts:24; infra/terraform/modules/site/main.tf:136

D-22 dejó la consola abierta a 0.0.0.0/0 con Cognito y MFA como única capa. No se encontró ninguna Content-Security-Policy en el repo (grep en web/index.html, infra/terraform y .conf sin resultados; el módulo site no declara response_headers_policy). Pasar a localStorage convierte cualquier XSS en robo de un refresh token de 24 h (o de 30 d para el inspector si opción A), y el inspector firma dictámenes y activa sirenas. Requisitos previos: CSP estricta, revocación al cerrar sesión (revokeTokensOnSignout, endpoint /oauth2/revoke de Cognito) y, si se activa la rotación, comprobar la carrera entre pestañas que comparten el refresh (AWS permite como mucho 60 s de gracia).

### A-041 · P1 · No hay usuario de prueba takab_support

- **Estado:** ⬜ FALTA · **Dimensión:** RBAC y flujos · **Ficha:** `T-8.13`
- **Roles:** takab_support
- **Evidencia:** infra/scripts/seed_console_users.sh:30-33

seed_console_users.sh siembra por defecto 6 roles y deja fuera a takab_support, aunque es un rol web de §1/§2. Sin esa identidad no se puede enseñar ni probar el recorrido de soporte en la nube. Acción: añadirlo a DEFAULT_ROLES, o sembrarlo con `seed_console_users.sh takab_support` (su tenant es interno: comprobar qué tenant_id le conviene).

### A-042 · P1 · El panel CCTV de EVALUACIÓN muestra un error 403 a support y a gov

- **Estado:** 🔴 DEFECTO · **Dimensión:** RBAC y flujos · **Ficha:** `T-8.08`
- **Roles:** takab_support, gov_operator
- **Evidencia:** web/src/features/triage/useCctv.ts:31-44; web/src/features/triage/TriagePage.tsx:97; web/src/features/triage/TriageDetail.tsx:344; api/src/takab_api/routers/cctv.py:35-46; api/src/takab_api/auth/matrix.py:406,447; takab-docs/RBAC-TAKAB.md:305-309

useCctv lanza GET /incidents/{id}/cctv en cuanto hay un incidente seleccionado, sin mirar allowed_actions.cctv_read. La API lo protege con roles_with_action('cctv_read'), que por decisión T-3.12.c excluye a takab_support y a gov_operator. Resultado: en la demo, esos dos roles ven «GET /incidents/{id}/cctv falló (403)» dentro de Evaluación. Contradice la regla de oro 7 (no pintar algo que siempre falla). Acción: pasar `enabled: incidentId !== null && me.allowed_actions.cctv_read` y no montar CctvPanel sin esa acción.

### A-043 · P1 · La consola no muestra check-ins de vida ni el pase de lista aunque los datos existen

- **Estado:** ⬜ FALTA · **Dimensión:** RBAC y flujos · **Ficha:** `T-8.14`
- **Roles:** soc_operator, tenant_admin, takab_superadmin, building_admin (web)
- **Evidencia:** api/src/takab_api/routers/mobile_incident.py:52-65,182-199; api/src/takab_api/auth/matrix.py:164-165; web/src/features/triage/CctvPanel.tsx:104

life_checkins y el roster se exponen solo por GET /incidents/{id}/checkins (propios) y /roster, este último con roster_read (brigadista, security_guard, building_admin). Ningún rol web tiene roster_read y en web/src no hay ningún componente de roster, check-in ni «necesito ayuda» (CctvPanel solo muestra un conteo dentro de la discrepancia). En una emergencia, el SOC no ve quién pidió ayuda. Acción: un endpoint agregado de lectura para roles de consola (conteos a salvo / necesita ayuda / sin respuesta por zona, sin PII o con PII auditada) y una tarjeta en DetailPanel/Triage.

### A-044 · P1 · El gov_operator sembrado vive en un tenant privado: ve el botón ACUSAR y la API responde 404; su aislamiento no se puede demostrar

- **Estado:** 🟠 SOSPECHA · **Dimensión:** RBAC y flujos · **Ficha:** `T-8.13`
- **Roles:** gov_operator
- **Evidencia:** infra/scripts/seed_console_users.sh:28,60-63; db/seeds/prod_fleet.sql:24-26; db/schema.sql:119,795-799,887-889,960-962; api/migrations/versions/0056_gov_ack_bitacora.py:60-61; api/src/takab_api/routers/incidents_ack.py:57-80; web/src/features/console/ConsolePage.tsx:191

seed_console_users.sh crea a gov_operator con tenant_id = tenant-dev y site_scope '*'. tenant-dev se crea sin visibility, así que queda 'private' por defecto. La RLS sites_read/incidents_read incluye `tenant_id = app_tenant_id()`, de modo que gov ve su «propio» tenant sin que sea gov_shared. La consola le pinta ACUSAR (ack_incident=True), pero la API desvía a gov_ack_incident, que lanza 'tenant no es gov_shared', y se traduce a 404 «incidente no encontrado». Tampoco se demuestra que solo ve tenants gov_shared. Acción: crear un tenant «Protección Civil» propio para el gov de la demo y marcar tenant-dev como gov_shared (o el tenant cliente de la demo). Si el valor en la nube ya cambió es NO_MEDIDO.

### A-045 · P1 · Inspector y building_admin no tienen identidad para móvil (el documento dice Web + Móvil)

- **Estado:** ⬜ FALTA · **Dimensión:** RBAC y flujos · **Ficha:** `T-8.13`
- **Roles:** inspector, building_admin
- **Evidencia:** infra/scripts/seed_console_users.sh:30-33,62-63,73-74; infra/scripts/seed_mobile_users.sh:79-87,123-128; mobile/src/auth/profileGate.ts:26-42; takab-docs/RBAC-TAKAB.md:32-33

seed_console_users.sh fija `custom:surface=web` a los 6 roles web. seed_mobile_users.sh solo acepta occupant, brigadista y security_guard, y rechaza inspector y building_admin. Con surface=web, profileGate.gateFor devuelve `wrong_surface` y la app los manda a /denied. Así, el recorrido móvil del inspector (cámara forense, triage) y del building_admin (silenciar, pase de lista) no se puede enseñar. Acción: sembrarlos con surface=both y un site_scope concreto (no '*'), en el pool principal y en su grupo.

### A-046 · P1 · enrollment_manage y self_test de building_admin no se pueden usar desde ninguna pantalla

- **Estado:** ⬜ FALTA · **Dimensión:** RBAC y flujos · **Ficha:** `T-8.19`
- **Roles:** building_admin
- **Evidencia:** api/src/takab_api/auth/matrix.py:468-482; web/src/features/fleet/FleetAdmin.tsx:135,219; web/src/features/fleet/SiteCard.tsx:78; web/src/features/fleet/FleetPage.tsx:302,326; api/src/takab_api/routers/mobile_site.py:57-61,466-471; takab-docs/RBAC-TAKAB.md:505

La matriz le concede enrollment_manage y self_test. La UI de códigos de enrolamiento (EnrollmentCodes dentro de FleetAdmin) y el autodiagnóstico (SiteCard) solo se montan en /fleet, y building_admin no tiene /fleet (§2 «—»). En móvil no hay UI para ninguna de las dos. Consecuencia: el responsable del edificio no puede dar códigos a sus ocupantes ni probar los relés, aunque la API se lo permite. RBAC §7 también sitúa los códigos en /fleet. Acción: una sección «Ocupantes y autodiagnóstico» en /building/:siteId, gateada por esas acciones, o una pantalla móvil.

### A-047 · P1 · Si la app arranca sin red, desaparecen PANEL, TRIAGE y LISTA y se apagan los controles tácticos

- **Estado:** 🟠 SOSPECHA · **Dimensión:** RBAC y flujos · **Ficha:** `T-8.18`
- **Roles:** brigadista, security_guard, inspector, building_admin
- **Evidencia:** mobile/src/auth/useAuth.ts:85-117; mobile/src/auth/pestanasTacticas.ts:51-63; mobile/src/app/(brigadista)/panel.tsx:139-141; mobile/src/auth/session.store.ts:16-44

Sin red, bootstrapSession deja me=null. pestanasVisibles(null) solo muestra RUTAS, DIRECTORIO, SYNC y CUENTA, y el panel calcula canActivate/canSilence desde me.allowed_actions, así que quedan en false. /me no se guarda en caché. Tras un sismo sin datos móviles, un brigadista que abre la app en frío no puede registrar daños ni pasar lista, aunque la cola offline (SYNC) existe precisamente para eso. El default-deny está declarado para una «sesión a medio cargar», no para arrancar sin red. Acción: guardar el último /me firmado junto a la sesión y usarlo para las pestañas (el servidor revalida al sincronizar); marcarlo como dato retenido.

### A-048 · P1 · Un táctico creado desde la consola queda sin edificio en la app (site_scope '*' y surface 'web' por defecto)

- **Estado:** 🔴 DEFECTO · **Dimensión:** RBAC y flujos · **Ficha:** `T-8.19`
- **Roles:** brigadista, security_guard, inspector, building_admin
- **Evidencia:** web/src/features/tenants/UsersCard.tsx:91,321-332; mobile/src/services/mySite.ts:1-5,109-124; mobile/src/auth/profileGate.ts:32-34; takab-docs/DECISIONES-MAURICIO.md:1738-1756

El formulario de alta de UsersCard empieza con surface 'web' y siempre envía site_scope '*' al crear, sea cual sea el rol. La app táctica elige el sitio que vigila con enrolled_sites[0] o site_scope[0]; con '*' queda en null y todas las pantallas dicen «sin sitio vigilado». No hay selector de sitio y los códigos de enrolamiento solo conceden occupant. Además, con surface 'web', el brigadista recién creado acaba en /denied (wrong_surface). Acción: al elegir un rol táctico, poner surface mobile/both por defecto y exigir uno o más sitios en el alta, o añadir un selector de sitio en la app táctica.

### A-049 · P1 · No se puede comprobar si las identidades sembradas existen hoy en Cognito ni su estado de MFA

- **Estado:** ❔ NO MEDIDO · **Dimensión:** RBAC y flujos · **Ficha:** `T-8.13`
- **Roles:** todos
- **Evidencia:** infra/scripts/seed_console_users.sh:93-101; infra/scripts/seed_mobile_users.sh:240-261; takab-docs/DECISIONES-MAURICIO.md:1684-1770

La memoria seed-usuarios-moviles (hace 67 días) decía que no existían; D-34/D-35 (2026-09-17/18) indican que después se sembraron occupant, occupant-e2e, brigadista y brigadista-e2e. Desde el código no se puede saber qué usuarios hay, con qué atributos ni si enrolaron TOTP. Acción: listar el pool (list-users + admin-list-groups-for-user) antes de la presentación.

### A-050 · P1 · §14 DAÑOS: con UNA foto (o con un número impar) lo siguiente se pinta encima del pie de foto

- **Estado:** 🔴 DEFECTO · **Dimensión:** PDF · **Ficha:** `T-8.12`
- **Roles:** todos los que reciben el PDF
- **Evidencia:** api/src/takab_api/dictamen/pdf.py:1592-1616,1575-1578; takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:171-172; api/tests/dictamen/test_fotos_en_el_papel.py:87-88,155-181

En _fotos_del_reporte, el multi_cell del pie usa new_y=YPos.NEXT if j else YPos.TOP. Si la fila solo tiene la foto j=0, el cursor vuelve a la parte de ARRIBA del pie (unos 4 renglones de 2.4 mm). Después vienen ln(1) + ln(2), y el siguiente reporte o el título «15. EVACUACIÓN OBSERVADA (CCTV)» se imprime unos 3 mm por debajo del inicio del pie, pisando las huellas DECLARADA, MEDIDA e IMPRESA. El propio plan de la presentación lo registra como la trampa 5: pasa en el 100 % de los incidentes con foto. La guarda solo prueba con 4 fotos (número par) y no mide solapes de texto. Arreglo: tras la fila, set_y(máximo del fondo de los pies), o bien new_y=NEXT en la última foto de la fila.

### A-051 · P1 · Las fotos en vertical superan la reserva de página y pueden pisar el pie (hash, paginación, razón social)

- **Estado:** 🔴 DEFECTO · **Dimensión:** PDF · **Ficha:** `T-8.12`
- **Roles:** todos los que reciben el PDF
- **Evidencia:** api/src/takab_api/documentos/fotos.py:157-161; api/src/takab_api/dictamen/pdf.py:1511-1518,1592-1600; api/tests/dictamen/test_fotos_en_el_papel.py:44-53

preparar() usa thumbnail((1024,1024)), que conserva la proporción: una foto 3:4 de teléfono sale a 768×1024 y se imprime a 88×117.3 mm. La reserva por fila es _FOTO_FILA_H = 88+10 = 98 mm, y el comentario que la justifica («una foto de retrato a 1024×1024 sale cuadrada») es falso. pdf.image() no dispara el salto de página, así que si la fila empieza con 98-128 mm libres, la foto baja hasta 19 mm dentro del pie. Las pruebas solo usan JPEG apaisados de 1600×1200. Arreglo: reservar el alto real de la foto más alta de la fila más el pie de foto, o encajar la foto en una caja de 88×88.

### A-052 · P1 · «VERIFICAR HASH» del dictamen en Triage da 404 (rojo «NO SE PUDO VERIFICAR») para superadmin, support, tenant_admin, soc_operator y gov_operator

- **Estado:** 🔴 DEFECTO · **Dimensión:** PDF · **Ficha:** `T-8.08`
- **Roles:** takab_superadmin, takab_support, tenant_admin, soc_operator, gov_operator
- **Evidencia:** api/src/takab_api/routers/mobile_incident.py:619-629,646-649; api/src/takab_api/auth/matrix.py:361-400,459,477,492,502; web/src/features/triage/TriageDetail.tsx:392-400; web/src/features/triage/EvidenceVerifier.tsx:20-35; web/src/features/triage/structural.ts:100-103; api/src/takab_api/dictamen/pdf.py:214-226

TriageDetail pinta EvidenceVerifier junto a «Dictamen emitido» sin filtrar por rol. POST /evidence/{id}/verify deja pasar a toda la consola (_require_verificable), pero para kind=report_pdf exige dictamen_read (inspector, building_admin, brigadista, security_guard) y responde 404 a los demás. En la web, el 404 cae en onError y se pinta como crítico. La portada del PDF promete que en Triage «se puede re-verificar contra el objeto archivado». Si la presentación la conduce superadmin, el botón sale en rojo delante del cliente. Hay que decidir: dar dictamen_read o el alcance de verificación a los roles de consola, u ocultar el botón.

### A-053 · P1 · El papel no rotula la clasificación humana del incidente (reproducción, prueba, falso positivo); «REPRODUCCIÓN» solo sale en la §7 si el evento es un replay

- **Estado:** ⬜ FALTA · **Dimensión:** PDF · **Ficha:** `T-8.12`
- **Roles:** todos los que reciben el PDF
- **Evidencia:** api/src/takab_api/dictamen/model.py:1006-1013,166-177; api/src/takab_api/dictamen/pdf.py:183-194,759-764; db/schema.sql:380-385; api/src/takab_api/dictamen/bitacora.py:46-77

model.reproduccion se deriva SOLO de seismic_events.meta.reproduccion. Es una decisión declarada: papel y consola leen el mismo campo. La leyenda solo se imprime dentro de «7. RED DE ESTACIONES», no en la portada ni en la cabecera. incident_classifications (real, falso_positivo, prueba, indeterminado, reproduccion) no llega al PDF, y bitacora.py no rotula ninguna acción de clasificación. Consecuencia en la demostración: un golpe en la losa clasificado a mano como «reproduccion» (así se clasifican los ensayos de T-7.28) sale como un incidente REAL, con veredicto y la frase «el sensor midió…» en la portada. Propuesta: una línea «CLASIFICACIÓN: …» en la portada y el ejecutivo, y la leyenda de REPRODUCCIÓN también en la portada.

### A-054 · P1 · El certificado de reingreso del móvil puede abrir un PDF PRELIMINAR (anterior a la firma)

- **Estado:** 🟠 SOSPECHA · **Dimensión:** PDF · **Ficha:** `T-8.12`
- **Roles:** inspector, building_admin, brigadista, security_guard
- **Evidencia:** api/src/takab_api/queries/mobile.py:198-202; api/src/takab_api/routers/mobile_incident.py:379-425; api/src/takab_api/dictamen/pdf.py:136-157,1727-1741; mobile/src/features/dictamen/DictamenCertificate.tsx:2-3,35-58

GET /incidents/{id}/dictamen exige un dictamen firmado, pero pdf_url es simplemente el report_pdf más reciente del incidente (ORDER BY created_at DESC LIMIT 1), sin comprobar que se generara DESPUÉS de firmar. Firmar no regenera el PDF: render() solo lo llama routers/reports.py, y el móvil no llama a /report. Flujo de la demo: el inspector firma en el teléfono, el brigadista pulsa «DESCARGAR CERTIFICADO», y el PDF dice «DICTAMEN OPERATIVO PRELIMINAR · SIN FIRMA DE INSPECTOR» o no existe. Hay que generar el PDF desde Triage DESPUÉS de firmar, o filtrar por created_at >= signed_at.

### A-055 · P1 · Revisión visual real de cada PDF y datos de la nube

- **Estado:** ❔ NO MEDIDO · **Dimensión:** PDF · **Ficha:** `T-8.12`
- **Roles:** todos
- **Evidencia:** takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:66-84,124-135

Por el modo de solo lectura no generé ni rasterizé ningún PDF. Quedan NO_MEDIDOS: texto desbordado en tablas y celdas, el aspecto del mapa de la sacudida, el espectrograma y el croquis, y el color de la banda de veredicto. Tampoco he comprobado lo que el plan dice de la nube: cero snapshots de mapa de sacudida; incidentes con fotos y con miniSEED que no coinciden, así que ninguno enseña las dos cosas; OpenRouter encendido con gemini-2.5-flash-lite. Hace falta una reproducción durante el ensayo que traiga fotos y onda juntas.

### A-056 · P1 · GET /fleet/gateways descarta disco y evidencia retenida: siempre null

- **Estado:** 🔴 DEFECTO · **Dimensión:** Estatus visibles · **Ficha:** `T-8.09`
- **Roles:** takab_superadmin, takab_support, tenant_admin, soc_operator, gov_operator (/fleet)
- **Evidencia:** api/src/takab_api/routers/fleet.py:284-353; api/src/takab_api/queries/fleet.py:48-52,58-62; api/src/takab_api/schemas/fleet.py:495-499; web/src/features/fleet/SiteCard.tsx:118-128,243-249; api/tests/contracts/test_todo_campo_del_latido_tiene_destino.py:48-66; git 760c222 (no tocó routers/fleet.py)

El SELECT trae h.evidence_pending, h.evidence_oldest_age_s y h.disk_used_pct y el schema GatewayOut los declara, pero el constructor GatewayOut(...) del router no los pasa, así que la API responde siempre null. Consecuencias: (a) SiteCard pinta en TODOS los gabinetes «EVIDENCIA · s/d · el gabinete no pudo mirar», culpando al gabinete de un fallo de la API (regla de oro 7, atribución falsa); (b) el disco del Pi, que T-7.53 hizo aterrizar en la base, no se ve en ninguna superficie web. El censo test_todo_campo_del_latido_tiene_destino.py sólo exige una COLUMNA por campo, no la salida de la API: por eso no lo detectó. Acción: añadir evidence_pending=m[...], evidence_oldest_age_s=m[...], disk_used_pct=m[...] al constructor, un test de API que lo fije y pintar el disco en SiteCard.

### A-057 · P1 · El LWT 'offline' hace que el gabinete parezca vivo durante sin_enlace_min

- **Estado:** 🔴 DEFECTO · **Dimensión:** Estatus visibles · **Ficha:** `T-8.09`
- **Roles:** todos (consola: mapa/flota/edificio; móvil: estado del sitio y sirena)
- **Evidencia:** api/src/takab_api/ingest/handlers.py:927-931,994-1013; api/src/takab_api/queries/fleet.py:58-66; api/src/takab_api/queries/telemetry.py:230-236; api/src/takab_api/queries/mobile.py:345,370-373; api/src/takab_api/schemas/fleet.py:88-89; web/src/features/fleet/useFleet.ts:137-142; api/src/takab_api/ops/metrics.py:122-126,153-159

handle_status inserta en device_health una fila (ts=meta.ts_iot, reason='transition') con TODAS las métricas en NULL, tanto para 'online' como para 'offline'. Todas las lecturas del «último latido» toman la fila más reciente SIN filtrar reason: flota, mapa, salud móvil, orden de sirena y métricas de ops. Tras una desconexión, age_s≈0, así que derive_fleet_state devuelve OPERATIVO sin razones (todo es None), las métricas salen S/D, los relés se pintan ARMADOS (None=compat en useFleet) e is_ghost marca «sigue latiendo» a un retirado recién caído. El hecho real (gateways.status='offline') no entra en la derivación. SIN ENLACE se retrasa hasta LWT+5 min en vez de último latido+5 min. Ningún test cubre LWT→estado de flota. Acción: excluir las filas de presencia del «último latido» (marcarlas o no insertarlas con métricas nulas) y/o derivar SIN ENLACE cuando gateways.status='offline' y metadata.status_ts > h.ts.

### A-058 · P1 · actuation_records (bitácora del gabinete) sin endpoint, sin UI y fuera del PDF

- **Estado:** ⬜ FALTA · **Dimensión:** Estatus visibles · **Ficha:** `T-8.14`
- **Roles:** tenant_admin, soc_operator, gov_operator, inspector, building_admin
- **Evidencia:** db/schema.sql:724-808; api/src/takab_api/ingest/handlers.py:683-739; edge/takab_edge/local_api/__init__.py:1451-1482,1846-1872; edge/takab_edge/supervisor.py:526; api/src/takab_api/privacy/erasure.py:356 (único lector)

La ingesta guarda cada actuación del gabinete: actuaciones con el enlace caído (online=false), acciones del panel LAN (arm_test_mode, silenciar, prueba de actuación, reset), voceo de simulacro y resultado éxito/fallo. Ningún router ni consulta la lee; sólo aparece en el mapa de PII de privacy/erasure.py. Es «lo primero que pide un perito o un seguro» (comentario del DDL) y hoy no se puede ver ni exportar. Acción: GET /sites/{id}/actuations (paginado, RLS), panel en /building y en el detalle de triage, y sección en el dictamen PDF.

### A-059 · P1 · MODO PRUEBA WR-1 («la nube no recibe alertas») invisible desde la nube

- **Estado:** ⬜ FALTA · **Dimensión:** Estatus visibles · **Ficha:** `T-8.14`
- **Roles:** soc_operator, tenant_admin, takab_superadmin/support
- **Evidencia:** edge/takab_edge/local_api/__init__.py:1595-1602; shared/schemas/health_snapshot.schema.json (sin campo); web/src/features/scene/MaintenanceBanner.tsx:12-13 (cita el precedente del banner-wr1)

El panel LAN muestra test_mode.active/remaining_s, pero el estado no viaja en HealthSnapshot ni en ningún otro mensaje: el SOC no puede saber que un gabinete tiene la nube muda. El armado sí queda en actuation_records (ver item anterior), que no tiene lector. Acción: añadir test_mode_active/remaining al latido (contrato aditivo) y un banner o pill en SiteCard, en el mapa y en el SceneStrip, igual que el banner violeta del panel.

### A-060 · P1 · El faro sobre los edificios que DISPARARON sigue pulsando con prefers-reduced-motion

- **Estado:** 🔴 DEFECTO · **Dimensión:** Animaciones · **Ficha:** `T-8.09`
- **Roles:** roles de consola web (soc_operator, gov_operator, tenant_admin, takab_*)
- **Evidencia:** web/src/features/console/MapPanel.tsx:486-488,677-690,1064-1068,1379-1381; web/e2e/motion.spec.ts:60-150

El loop rAF llama pulseAt() y setPaintProperty('pulse', radius/opacity) en cada tick SIN mirar la preferencia. reducedMotionRef se declara y asigna pero nunca se lee. Con reducción, la leyenda afirma «ANILLOS ESTÁTICOS (MOVIMIENTO REDUCIDO)» mientras el faro rojo sigue expandiéndose de 15 a 60 px cada 1.6 s. motion.spec.ts no lo cubre (sólo sondea soc-dot, transiciones, UPS y ConfirmButton). Arreglo: en el loop `if (!reducedMotionRef.current)` antes de pulseAt; con reducción fijar un anillo quieto y PUESTO (p.ej. circle-radius 22, circle-stroke-opacity 0.6), como hace T-7.18 con el anillo de arribo; añadir un e2e que siembre un sitio felt=trip y compare map.getPaintProperty('pulse','circle-radius') entre dos instantes con reduce.

### A-061 · P1 · El parpadeo del banner rojo atenúa TAMBIÉN la instrucción: ~1.6:1 de contraste medio ciclo

- **Estado:** 🔴 DEFECTO · **Dimensión:** Animaciones · **Ficha:** `T-8.15`
- **Roles:** personas en el inmueble frente al kiosco, security_guard, building_admin
- **Evidencia:** edge/takab_edge/local_api/index.html:55,107-108,418-422; edge/tests/test_local_api_panel.py:1030-1045; takab-docs/DECISIONES-MAURICIO.md:1504-1520

`animation:tk-blink 900ms steps(2,end)` está sobre #banner-alert, y opacity 0.35 se aplica a todo el grupo, incluido `.big` «ALERTA SÍSMICA · PROTÉJASE». Calculado (no medido en navegador): texto navy #0E2336 sobre la mezcla 35 % rojo #FF5252 con el fondo surface-0 da ≈1.6:1 frente a ~5:1 en reposo, durante 450 ms de cada 900 ms. D-30 lo heredó explícitamente («el panel ya parpadeaba… esta decisión no añade») y su condición 1 dice que el texto se lee desde el primer frame. El test `test_el_parpadeo_vive_en_el_BANNER_y_no_en_el_texto` sólo comprueba el SELECTOR y no el efecto visual. Arreglo sin keyframe nuevo: mover la animación a `#banner-alert::after` (capa absoluta de fondo/borde con pointer-events:none) y dejar el texto a opacidad 1; actualizar el test para exigir que ningún ancestro de `.big` anime opacity. Mantener el período ≤3 destellos/s (hoy 1.1/s: correcto).

### A-062 · P1 · Ningún botón de la app responde visualmente al toque

- **Estado:** 🔷 MEJORA · **Dimensión:** Animaciones · **Ficha:** `T-8.11`
- **Roles:** occupant, brigadista, security_guard, inspector, building_admin
- **Evidencia:** mobile/src (grep '<Pressable' = 57, 'pressed' = 0); mobile/src/features/checkin/CheckinView.tsx:28-64; mobile/src/app/(brigadista)/sync.tsx:125-156

Hay 57 <Pressable> fuera de tests y 0 usos de `pressed`, android_ripple, TouchableOpacity o TouchableHighlight. Pressable no trae feedback por defecto: cada toque parece ignorado hasta que llega la respuesta, justo lo que un cliente nota en la demo. Propuesta: style={({pressed}) => [base, pressed && {opacity: 0.85}]} + android_ripple con palette.cyan al 20 % (instantáneo, no es movimiento); añadir transform scale 0.97 sólo si !reduceMotion. Excepción: PanicButton y SlideToConfirm ya tienen su propio portador.

### A-063 · P1 · Si la red corrobora (cuórum), la consola y el teléfono se contradicen

- **Estado:** 🔴 DEFECTO · **Dimensión:** Funciones básicas · **Ficha:** `T-8.10`
- **Roles:** soc_operator, gov_operator, tenant_admin, occupant, brigadista
- **Evidencia:** web/src/features/console/AlertBanner.tsx:73; mobile/src/features/alert/source.ts:79-80; takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:160-166

PARCIAL/DEFECTO. El motor de correlación no reescribe `trigger`. La consola decide si la alerta autoriza actuación solo con `authorizes(incident.trigger)`, y el móvil usa `meta.node_count`. Resultado para el mismo incidente: panel rojo, teléfono «EVACÚE», consola ámbar «SIN ACTUACIÓN». El plan de presentación lo midió como trampa 2, pero no hay ficha en TASKS.md. Acción: que AlertBanner/scene derive `authorizes` también de `node_count ≥ quorum_min_nodes` (el mismo dato que usa source.ts) y fichar la corrección.

### A-064 · P1 · La sirena NO suena con el Pi apagado (ruta de hardware paralela, G-02)

- **Estado:** ⬜ FALTA · **Dimensión:** Funciones básicas · **Ficha:** `T-8.19`
- **Roles:** building_admin, occupant, cliente
- **Evidencia:** takab-docs/TASKS.md:10416-10432 (T-2.92); takab-docs/INFORME-V1-COMERCIAL.md:61 (H-05); edge/takab_edge/config/settings.py:510

FALTA, bloqueada en dinero y hardware. La ruta está decidida (D-10), pero la compra quedó sin fecha (D-16). El latido de software arranca deshabilitado y el gabinete declara `keepalive: sin_ruta`. Es la mitigación de punto único de falla más importante del sistema y lo primero que preguntará un hospital. No se debe prometer en la demo.

### A-065 · P1 · El apartado 14 del PDF («DAÑOS REPORTADOS EN CAMPO») se rompe en todos los incidentes con foto, y no tiene ficha

- **Estado:** 🟠 SOSPECHA · **Dimensión:** Funciones básicas · **Ficha:** `T-8.12`
- **Roles:** inspector, cliente receptor del PDF
- **Evidencia:** api/src/takab_api/dictamen/pdf.py:1540; takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:171-172

PARCIAL/SOSPECHA. PLAN-REVISION lo registra como trampa 5 («se dispara en el 100 % de los incidentes con fotografía»), pero no aparece en TASKS.md ni se describe qué falla. No lo reproduje: NO_MEDIDO. Acción: generar el PDF de un incidente con un reporte de daño con foto, describir el defecto y fichar. Es el papel que se le entrega al cliente.

### A-066 · P1 · Dictamen «completo» no demostrable con los datos de la nube de hoy

- **Estado:** 🟠 SOSPECHA · **Dimensión:** Funciones básicas · **Ficha:** `T-8.13`
- **Roles:** inspector, soc_operator
- **Evidencia:** takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:79-84; takab-docs/TASKS.md:15371 (T-7.28 [~])

PARCIAL (dato, no código). La nube tiene 0 snapshots de ShakeMap. Los candidatos exigen que el incidente se haya abierto en las últimas 6 h. Fotos y miniSEED están en incidentes distintos (8 con onda y sin foto, 4 con foto y sin onda). Acción para la presentación: una reproducción armada durante el ensayo que produzca onda, foto del brigadista y ShakeMap en el mismo incidente (T-7.28, segunda corrida).

### A-067 · P1 · La duración de sesión por rol no se puede expresar con los app clients actuales

- **Estado:** 🟠 SOSPECHA · **Dimensión:** Funciones básicas · **Ficha:** `T-8.05`
- **Roles:** todos
- **Evidencia:** infra/terraform/modules/identity/main.tf:160-168,629-635,665-671; web/src/auth/userManager.ts:24-26; takab-docs/specs/cognito-pool-v1.md:102-105

PARCIAL. En Cognito la validez del refresh es por app client, no por grupo. Hoy: web `takab-web` 8 h (y guardado en sessionStorage: se pierde al cerrar la pestaña); `takab-mobile-tactical` 24 h, compartido por brigadista, security_guard, inspector y building_admin; `takab-mobile-occupants` 90 días. MFA solo se pide al iniciar sesión, así que un refresh válido evita repetirla. Para cumplir «30 días para brigadista, inspector y ocupante; 1 día para los demás»: ocupantes a 30 días; un app client táctico nuevo de 30 días solo para brigadista e inspector (la app elige el cliente según el grupo, o una puerta en /me rechaza el cruce), con security_guard y building_admin en el de 24 h; web a 24 h y en localStorage (o aceptar la sesión por pestaña). El inspector también usa la web, donde le tocaría 1 día: hay que decidir (ver preguntas abiertas). Requiere terraform apply (HUMANO-AWS) y además arreglar la renovación del ítem anterior.

### A-068 · P1 · No hay app iOS ni publicación en tiendas

- **Estado:** ⬜ FALTA · **Dimensión:** Funciones básicas · **Ficha:** `T-8.19`
- **Roles:** occupant, brigadista, security_guard, inspector, building_admin
- **Evidencia:** mobile/app.json (ios.bundleIdentifier=com.takab.ailert); takab-docs/TASKS.md:10476-10500 (T-2.97, T-2.98); takab-docs/PENDIENTES-MAURICIO.md:1038-1065

FALTA, bloqueada en HUMANO-AWS y LEGAL. En mobile/ solo existe android/ (no hay proyecto ios ni eas.json). APNs no es real (T-2.97), el entitlement de Critical Alerts está sin pedir (T-2.98) y el APK se instala a mano en el Pixel. En corporativos y universidades, buena parte de los ocupantes usa iPhone: hoy no se puede enseñar ni instalar. El tono propio ya está cableado (D-19).

### A-069 · P1 · No existe camino para crear cuentas de ocupante

- **Estado:** ⬜ FALTA · **Dimensión:** Funciones básicas · **Ficha:** `T-8.19`
- **Roles:** occupant, building_admin, tenant_admin
- **Evidencia:** infra/terraform/modules/identity/main.tf:556-559; api/src/takab_api/schemas/users.py:26-29; takab-docs/specs/cognito-pool-v1.md:25; takab-docs/USER-STORIES.md:141-145

FALTA; necesita DECISIÓN y luego software. El pool de ocupantes tiene `allow_admin_create_user_only = true` (el comentario dice «Self-signup: decisión futura»), y /users excluye `occupant` a propósito. Hoy las cuentas solo salen de scripts (seed_mobile_users.sh). El código de enrolamiento vincula una cuenta que ya existe, pero no la crea. Con cientos de ocupantes por edificio no hay forma práctica de darlos de alta. Opciones: autorregistro restringido al código del edificio (disparador pre-signup que valide el código) o invitación masiva desde la consola por building_admin o tenant_admin.

### A-070 · P1 · Zonas/pisos y su política EVACÚE/REPLIÉGUESE no se pueden dar de alta

- **Estado:** ⬜ FALTA · **Dimensión:** Funciones básicas · **Ficha:** `T-8.19`
- **Roles:** tenant_admin, building_admin, takab_support, occupant (afectado)
- **Evidencia:** api/src/takab_api/routers/sites.py:100-103; api/src/takab_api/schemas/sites.py:44; db/seeds/e2e_harness.sql:48

FALTA; es software. La API solo lee zonas (GET /sites/{id} → `zones`), y hoy se crean por SQL (seed). US-09 y la crisis por piso dependen de `zone_id` y `evac_policy`: sin alta de zonas no se puede configurar un edificio real. Acción: CRUD de zonas (nombre, nivel, evac_policy) en la consola (Flota/Sitio) para tenant_admin, building_admin y takab_support, con auditoría, y que EnrollmentCodes las elija.

### A-071 · P1 · Cascada de notificación: solo webhook, correo verificado y push Android entregan de verdad

- **Estado:** 🟠 SOSPECHA · **Dimensión:** Funciones básicas · **Ficha:** `T-8.19`
- **Roles:** tenant_admin, soc_operator, gov_operator, occupant
- **Evidencia:** api/src/takab_api/notify/providers.py:40-72; takab-docs/TASKS.md:7033,7218,7348; takab-docs/PENDIENTES-MAURICIO.md:989-1037

PARCIAL, bloqueada. El webhook HMAC es real. El correo sale por SES en sandbox, solo a direcciones verificadas (T-2.78). El push Android es real y el de iOS no (T-2.97). SMS y WhatsApp siguen en simulado (T-2.76.a Twilio, T-2.77.a Meta). La consola declara qué canal es real (T-2.75.a). Todo depende de altas de cuentas y trámites legales, no de código.

### A-072 · P1 · La gestión de usuarios de la consola corre SIMULADA en la nube (T-2.87)

- **Estado:** ⬜ FALTA · **Dimensión:** Funciones básicas · **Ficha:** `T-8.19`
- **Roles:** tenant_admin, takab_superadmin
- **Evidencia:** deploy/cloud/deploy.sh:125-175 (sin COGNITO_USER_POOL_ID); infra/terraform/modules/database/main.tf:532-537; web/src/features/tenants/UsersCard.tsx:128; takab-docs/TASKS.md:10347-10356

FALTA, bloqueada en HUMANO-AWS. deploy.sh no exporta `TAKAB_API_COGNITO_USER_POOL_ID` al contenedor de la API, y el rol de la instancia solo tiene `cognito-idp:ListUsers`. La tarjeta de usuarios pinta «DIRECTORIO SIMULADO · NADA SE ESCRIBE DE VERDAD»: el autoservicio (crear, invitar, resetear, dar de baja) no escribe en Cognito. NO_MEDIDO: si /etc/takab/cloud.env lo trae a mano. Riesgo en la demo: un tenant_admin que abra MULTI-TENANT verá el rótulo. Acción: cablear la variable y dar AdminCreateUser, AdminUpdateUserAttributes, AdminAddUserToGroup, AdminDisableUser, AdminResetUserPassword y AdminDeleteUser acotados al pool, y hacer apply.

### A-073 · P1 · Backups y DR: construidos, pero el RTO de producción no está medido y el WAL no se verifica en S3

- **Estado:** 🟠 SOSPECHA · **Dimensión:** Funciones básicas · **Ficha:** `T-8.16`
- **Roles:** takab_superadmin, takab_support
- **Evidencia:** api/src/takab_api/ops/restore_check.py; api/src/takab_api/ops/restore_drill.py; takab-docs/TASKS.md:6318,6851,7348

PARCIAL. PITR en IaC, ensayo de restore que mide su propio RTO y comprobador con 59 mutaciones. Abiertas: T-2.72.a (comprobar que el WAL llegó de verdad a S3: head-object del segmento, software) y T-2.74 (restore real con RTO publicado, HUMANO-AWS). La cadena de guardia sigue sin acreditar mientras SES esté en sandbox (T-2.78). En la demo: «RTO objetivo 1 h», nunca «medido».

### A-074 · P1 · Lo que un cliente esperaría y hoy no se puede demostrar

- **Estado:** ⬜ FALTA · **Dimensión:** Funciones básicas · **Ficha:** `T-8.19`
- **Roles:** todos
- **Evidencia:** takab-docs/INFORME-V1-COMERCIAL.md:120-138; takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:66-139; takab-docs/TASKS.md:17382-17406

Lista para no prometerlo y para priorizar:
(a) SMS y WhatsApp, y push en iPhone;
(b) sirena con el Pi apagado; gas, ascensores y puertas;
(c) voceo;
(d) magnitud del SSN (USGS sí, con procedencia);
(e) RTO medido;
(f) usuarios reales creados desde la consola (sale SIMULADO);
(g) reporte mensual y % de disponibilidad;
(h) QR del edificio y alta masiva de ocupantes;
(i) multi-idioma: no hay ninguna librería de i18n en web ni móvil, todo es es-MX; poca prioridad para clientes mexicanos, pero lo preguntan corporativos con personal extranjero;
(j) SSO corporativo;
(k) exportar la bitácora.
Respetar la lista «lo que NO debe decirse» del runbook y las invariantes de §14 (sin cuenta regresiva T-MINUS, sin magnitud preliminar, sin streaming crudo continuo, sin IA en la ruta de disparo, sin tocar Shake OS).

### A-075 · P1 · Fichas que dependen de Mauricio (PENDIENTES: 30 puntos)

- **Estado:** ⬜ FALTA · **Dimensión:** Funciones básicas · **Ficha:** `T-8.19`
- **Roles:** n/a
- **Evidencia:** takab-docs/TASKS.md:1008,1071,5322,5940,6851,7033-7348,10347-10500,10682,11190,11337-11357,12762,15371; takab-docs/PENDIENTES-MAURICIO.md:11-13

HUMANO-AWS: T-1.44/T-2.88 (rol CI OIDC), T-2.87 (Cognito Admin), T-2.90 (e2e contra lo desplegado), T-2.91 (ocupante real), T-2.74 (RTO), T-2.76.a (Twilio), T-2.77 y T-2.77.a (WhatsApp), T-2.78 (SES y guardia), T-2.97 (APNs), T-2.167 y T-2.168 (landing), T-2.71 (gates de mantenimiento).
FÍSICO: T-1.42 (WR-1 con CIRES), T-2.70.a (criterio 4), T-2.92 (G-01, G-02, G-04), T-2.93 (G-03, G-05, G-07, G-10), T-2.94 (G-06, G-08), T-2.95 (móvil y voceo), T-3.10 (B.2 CCTV), T-3.12.d, T-5.22, T-7.28 (segunda corrida, capturas y vídeo).
LEGAL: T-2.96, T-2.98, T-4.04.
Cierre: T-4.01, T-4.03.

### A-076 · P1 · El paso 7.b de deploy.sh «blanquea» el rojo del dueño de los pines en el segundo despliegue, y la poda puede borrar la release que el dueño está corriendo

- **Estado:** 🔴 DEFECTO · **Dimensión:** Edge/nube/presentación · **Ficha:** `T-8.17`
- **Roles:** n/a (operación/despliegue)
- **Evidencia:** deploy/edge/deploy.sh:459; deploy/edge/deploy.sh:993-1034; deploy/edge/deploy.sh:721-737; edge/takab_edge/gpio/__init__.py:559; edge/takab_edge/version.py:106-113

RELEASE_ANTERIOR es el destino del symlink ANTES de este despliegue (deploy.sh:459), no la release desde la que arrancó takab-gpio. Escenario: el despliegue N cambia código del dueño → ✗ «corre código anterior» (exit 1, el symlink se queda en N). El operador no abre ventana y despliega N+1 sin tocar el código del dueño; la comparación N+1↔N da DUENO-IGUAL → ✓ (deploy.sh:1024-1025), aunque el dueño siga ejecutando N-1. Además la poda 6.e solo protege ACTIVA_AHORA, RELEASE_ANTERIOR y heredada-* (deploy.sh:721-737), así que tras 3 despliegues sin ventana puede hacer rm -rf del árbol del proceso vivo (los imports perezosos, p. ej. gpio/__init__.py:440/735/809, fallarían al siguiente uso). Arreglo (fuera del camino determinista): que el dueño escriba release=<running_version()> en el registro del cerrojo, junto a pid/unit (gpio/__init__.py:559); que 7.b compare VIVO contra ESA release; y que la poda la proteja.

### A-077 · P1 · La versión que corre el dueño de los pines (takab-gpio) no se ve en ningún sitio

- **Estado:** ⬜ FALTA · **Dimensión:** Edge/nube/presentación · **Ficha:** `T-8.17`
- **Roles:** takab_superadmin, takab_support (flota)
- **Evidencia:** edge/takab_edge/health/__init__.py:466-470; edge/takab_edge/version.py:106-113; edge/takab_edge/contracts.py:447-557

El latido publica fw_version/fw_running del proceso takab-edge (health/__init__.py:466-470), no del dueño. Ni pinlink ni gpio_link exponen versión: un grep de fw_/version/release en gpio_link.py, pinlink/codec.py y pinlink/server.py no da nada. «El dueño corre código anterior» (memoria desplegar-el-edge-sin-mover-un-pin) solo se descubre por ssh. Propuesta: añadir owner_running al snapshot del pinlink → panel → HealthSnapshot → consola y conformidad.sh. Es un cambio de contrato en shared/schemas/health_snapshot.schema.json.

### A-078 · P1 · cloud.publish() hace fsync y espera el PUBACK (hasta 10 s) en el hilo de SeedLink: puede cegar la detección instrumental

- **Estado:** 🟠 SOSPECHA · **Dimensión:** Edge/nube/presentación · **Ficha:** `T-8.17`
- **Roles:** todos (detección)
- **Evidencia:** edge/takab_edge/supervisor.py:598-614; edge/takab_edge/supervisor.py:850; edge/takab_edge/telemetry/__init__.py:66-76; edge/takab_edge/cloud/__init__.py:480-517; edge/takab_edge/cloud/__init__.py:567-594; edge/takab_edge/cloud/__init__.py:731-733; edge/tests/test_cloud.py:273-304

La cadena es SeedLink.ingest → _on_packet → _act_and_publish → cloud.publish(EVENTS_TOPIC) (supervisor.py:598-605, 850); en watch+, telemetry.submit publica cada feature de 1 Hz en el mismo hilo (telemetry/__init__.py:66-76). publish() escribe al spool con fsync de fichero y directorio (cloud/__init__.py:505, 135) y luego llama a flush() síncrono (516). Si nadie más está drenando, este hilo espera future.result(timeout=10) (732). Con un enlace medio abierto (keepalive de 30 s) cada publicación bloquea hasta 10 s la ingesta y la evaluación de reglas. El test test_flush_of_backlog_does_not_block_concurrent_publish (test_cloud.py:273) solo cubre el caso en que OTRO hilo drena. No toca el reflejo SASMEX→sirena, que vive en takab-gpio. Arreglo: que publish() solo encole y avise con un threading.Event al hilo cloud-reconnect para que drene él, y valorar un fsync por lote para los topics acotados (features). El impacto real en el Pi 4 está sin medir.

### A-079 · P1 · Cada despliegue tira el stack entero: se reinicia con `compose down`+`up` y sin descargar antes las imágenes

- **Estado:** 🔷 MEJORA · **Dimensión:** Edge/nube/presentación · **Ficha:** `T-8.16`
- **Roles:** todos (indisponibilidad durante el despliegue)
- **Evidencia:** deploy/cloud/deploy.sh:339-355; deploy/cloud/deploy.sh:417-429; deploy/cloud/deploy.sh:520-523; deploy/cloud/takab-cloud.service:11-12

deploy.sh lo dice él mismo: «no hay ningún docker pull». Las imágenes bajan como efecto colateral del `docker run` de alembic y del `compose up` (deploy.sh:339-344). Después, `systemctl restart takab-cloud.service` ejecuta ExecStop=`docker compose down` y luego ExecStart=`up -d` (takab-cloud.service:11-12). Resultado: API, consola/Caddy (TLS), ingest y notify quedan caídos mientras se descargan las imágenes de los 8 servicios. Encima, la migración (deploy.sh:417-420) corre con la API VIEJA sirviendo contra el esquema nuevo. Arreglo: `docker compose pull` justo después de margen-y-poda.sh y antes de migrar, y sustituir `systemctl restart` por `docker compose up -d --remove-orphans`, que recrea solo lo que cambió. margen-y-poda (T-7.46) ya garantiza el disco.

### A-080 · P1 · Generar el PDF bloquea el event loop de un uvicorn de un solo worker

- **Estado:** 🟠 SOSPECHA · **Dimensión:** Edge/nube/presentación · **Ficha:** `T-8.12`
- **Roles:** inspector, takab_superadmin (generan); todos (sufren el congelamiento)
- **Evidencia:** api/src/takab_api/routers/reports.py:50-136; api/src/takab_api/routers/drills.py:852-855; api/src/takab_api/dictamen/builder.py:742; api/src/takab_api/dictamen/builder.py:795; api/src/takab_api/routers/_s3.py:22-89; deploy/cloud/docker-compose.yml:36-47; api/src/takab_api/commands/service.py:118

generate_report y drill_report son `async def` pero llaman en línea a boto3 síncrono (get_object/put_object, _s3.py:22-89, con un cliente nuevo por llamada) y a render() de fpdf, que es CPU pura (reports.py:94, 130, 136; drills.py:852-855). El builder lee fotos y miniSEED de S3 de forma síncrona (builder.py:742, 795). La API corre sin --workers (docker-compose.yml:41-47). Mientras dura el render se congelan el WebSocket de la consola, /health y el mobile-state que la app sondea cada 5 s en crisis. El patrón correcto ya está en el repo: anyio.to_thread.run_sync (commands/service.py:118, routers/users.py:165). La duración real en la nube está sin medir.

### A-081 · P1 · No hay alarma de edad o profundidad de la cola PRINCIPAL de SQS ni healthcheck en los contenedores

- **Estado:** ⬜ FALTA · **Dimensión:** Edge/nube/presentación · **Ficha:** `T-8.16`
- **Roles:** todos (alertamiento)
- **Evidencia:** infra/terraform/modules/observability/main.tf:166-186; infra/terraform/modules/observability/main.tf:354-376; deploy/cloud/docker-compose.yml:23-29; deploy/cloud/docker-compose.yml:50-114

Solo se alarma la DLQ (observability/main.tf:166-172, ApproximateNumberOfMessagesVisible sobre las DLQ). No existe ninguna alarma sobre ApproximateAgeOfOldestMessage (grep vacío en infra/, api/ y deploy/). Los servicios usan `restart: unless-stopped` sin healthcheck (docker-compose.yml:23-29), así que un ingest-events o incident-engine COLGADO (sin crash) deja los eventos reales en cola sin abrir incidente y sin avisar a nadie. No pasan a la DLQ porque nadie los recibe. gateway_offline no lo ve porque su métrica sale de una regla de IoT, no de los workers. Añadir: alarma de edad del mensaje más viejo en events/telemetry/backfill (p. ej. > 120 s) y un healthcheck o latido por worker.

### A-082 · P1 · Backups y DR: el restore real con RTO medido y la comprobación del WAL en S3 siguen abiertos; una sola instancia

- **Estado:** ⬜ FALTA · **Dimensión:** Edge/nube/presentación · **Ficha:** `T-8.16`
- **Roles:** n/a
- **Evidencia:** takab-docs/TASKS.md:6318-6328; takab-docs/TASKS.md:6851; takab-docs/PENDIENTES-MAURICIO.md:338-356; infra/terraform/modules/observability/main.tf:459-653; infra/terraform/modules/database/main.tf:899; deploy/cloud/docker-compose.yml:1-6

Existen PITR con barman-cloud, las alarmas backup-base-ausente/atrasado y wal-archivado-atascado, DLM de EBS y el procedimiento de restore corregido (fase 2.6). Sigue abierto T-2.74 (G-09: restore real en AWS con RTO medido) y T-2.72.a (last_archived_time mide el rc del archive_command, no que el objeto esté en el bucket). La API, los workers y la BD están en un único EC2 t4g.medium: es un SPOF declarado (D-2026-07-09). Por eso «restauramos en menos de una hora» sigue prohibido (RUNBOOK:101).

### A-083 · P1 · Sesiones: la duración pedida (30 días campo/ocupante, 1 día resto) choca con cómo está montado Cognito

- **Estado:** 🔷 MEJORA · **Dimensión:** Edge/nube/presentación · **Ficha:** `T-8.05`
- **Roles:** brigadista, inspector, occupant (30 d); tenant_admin, soc_operator, gov_operator, building_admin, security_guard, takab_superadmin, takab_support (1 d)
- **Evidencia:** infra/terraform/modules/identity/main.tf:160-167; infra/terraform/modules/identity/main.tf:629-636; infra/terraform/modules/identity/main.tf:665-672; mobile/src/auth/profileGate.ts:17-22; web/src/auth/userManager.ts:24-26; api/src/takab_api/auth/mfa.py:78-96; takab-docs/DECISIONES-MAURICIO.md:80

La duración del refresh es POR APP CLIENT, no por rol. Web: 8 h (identity/main.tf:160-167), compartido por inspector y los roles de administración. Táctico: 24 h (665-672), que usan brigadista, security_guard, inspector y building_admin (profileGate.ts:17-22). Ocupantes: 90 días (629-636), así que pedir 1 mes es REDUCIRLO. Además la consola guarda la sesión en sessionStorage (userManager.ts:24): cerrar la pestaña obliga a volver a entrar, dure lo que dure el refresh. Opciones: separar app clients, o poner el client táctico a 30 días y que la API rechace tokens con auth_time > 24 h para building_admin y security_guard. auth_time viaja en el ID token (auth/mfa.py:29, 85). Toca D-22 («Cognito con MFA como única capa»): conviene escribirlo como decisión. «MFA durante 1 mes» equivale al refresh token; no hace falta device_configuration, que mfa.py:89-96 ancla en apagado.

### A-084 · P1 · El guion y el RUNBOOK siguen mandando `POST /api/reset` SIN PIN, y en el último paso eso da 401

- **Estado:** 🔴 DEFECTO · **Dimensión:** Edge/nube/presentación · **Ficha:** `T-8.13`
- **Roles:** building_admin/presentador (panel)
- **Evidencia:** deploy/demo/guion.sh:713; deploy/demo/guion.sh:143; takab-docs/runbooks/RUNBOOK-demo-cliente.md:366-368; takab-docs/runbooks/GUIA-DEMOSTRACION-POR-ROLES.md:279-297; edge/takab_edge/local_api/__init__.py:716-737

El panel exige X-Takab-Pin en toda acción (local_api:6, 716-737): sin la cabecera devuelve 401 {"error":"pin"}. La GUIA ya lo corrigió con la medición del 22-09 (GUIA:279-297), pero siguen mal guion.sh:713 («1) suelta el enclavado: curl -X POST $PANEL/api/reset»), la pista de guion.sh:143 y RUNBOOK-demo-cliente.md:367. Es el paso de limpieza, con el edificio enclavado y el cliente delante: el 401 se leerá como «se colgó». Cambiarlo a «botón CERRAR ALERTA del panel (PIN en campo password)» o al curl con -H X-Takab-Pin, y tener el PIN a mano (edge.env solo lo lee root).

### A-085 · P1 · Los dos incidentes del ensayo 1 siguen sin clasificar, y el Goal de la fase no puede pasar

- **Estado:** ⬜ FALTA · **Dimensión:** Edge/nube/presentación · **Ficha:** `T-8.13`
- **Roles:** soc_operator / inspector (clasificar)
- **Evidencia:** takab-docs/runbooks/RUNBOOK-demo-cliente.md:554-565; takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:292-303; takab-docs/PLAN-REVISION-PRESENTACION-CLIENTE.md:221-235

d5af54e5-b01b-44b8-81e4-3851c71eb9f6 (acto 2, watch) y b420daaa-84d1-4bf2-95d4-e328fc0ead92 (acto 3, critical) figuran «in_review y SIN CLASIFICAR». La comprobación 4 del Goal falla mientras el § Registro diga «sin clasificar» o «Pendiente de esta corrida». Hasta clasificarlos como `reproduccion` cuentan como sismos reales en las métricas del sitio. Si ya los cerró el review_ttl de 6 h (sin medir), clasificarlos igual: la tabla es append-only. Después, editar el § Registro.

### A-086 · P1 · F7 / T-7.28 sigue abierta: faltan el ensayo 2, las capturas, el vídeo y el veredicto de flujos; el ensayo 1 duró 59 min

- **Estado:** ⬜ FALTA · **Dimensión:** Edge/nube/presentación · **Ficha:** `T-8.13`
- **Roles:** todos (presentador, brigadista, inspector, occupant)
- **Evidencia:** takab-docs/TASKS.md:15371-15444; takab-docs/runbooks/RUNBOOK-demo-cliente.md:486-587; takab-docs/PLAN-PROTOTIPO-FUNCIONAL.md:353-375; api/src/takab_api/routers/mobile_site.py:214-229

Ensayo 1 (20260922T180248Z): 29 ✓ · 0 ✗, pero el acto 4 duró 46:57. El acto 2 solo llegó a `watch`, con lo que el teléfono del ocupante no enseña nada por diseño (T-2.105). La limpieza se hizo 4 h después. El número del reflejo (0,22 ms) no se puede citar. Para el ensayo 2: precargar el reporte de daños y dejar el incidente listo para firmar; en el acto 2, golpe más seco y comprobar el tier en el panel antes de ir a la consola; limpieza dentro del guion; segunda medición del acta; y anotar si el PDF salió con prosa o con NARRATIVA DEGRADADA. Además, el Goal de F7 pide Maestro en el Pixel (01a, 01b, 02, 03) y Playwright contra la nube desplegada: no hay registro de corrida reciente (sin medir).

### A-087 · P1 · Mergear la rama de instrumentos antes del día: en main, goal-presentacion.sh todavía da veredictos ciegos

- **Estado:** 🔷 MEJORA · **Dimensión:** Edge/nube/presentación · **Ficha:** `T-8.01`
- **Roles:** n/a (presentador)
- **Evidencia:** git log main..HEAD (b804039); deploy/demo/goal-presentacion.sh; deploy/cloud/conformidad.sh

git log main..HEAD = b804039 (subida a origin, sin mergear). En main, goal-presentacion.sh pinta de ROJO el «instancia no medida» (A4) y manda a redesplegar una nube correcta; da VERDE a un censo con 13 de 19 piezas sin medir (A3); y da ✓ «relés en reposo» cuando el dueño de los pines no contesta (A6). La rama solo toca docs y scripts de operador (conformidad.sh, medir-latencia-ia.sh, goal-presentacion.sh), que no viajan en las imágenes: no hace falta redesplegar.

### A-088 · P1 · Ningún documento de la demo dice cómo evitar que la sesión caduque o haya que repetir el MFA a mitad de la presentación

- **Estado:** ⬜ FALTA · **Dimensión:** Edge/nube/presentación · **Ficha:** `T-8.13`
- **Roles:** los 6 roles web, brigadista, inspector
- **Evidencia:** infra/terraform/modules/identity/main.tf:160-167; infra/terraform/modules/identity/main.tf:665-672; web/src/auth/userManager.ts:24-26; takab-docs/runbooks/GUIA-DEMOSTRACION-POR-ROLES.md:18-37

Web: el refresh dura 8 h absolutas desde el login y la sesión vive en sessionStorage, así que cerrar la pestaña obliga a volver a meter contraseña y TOTP. Cambiar entre los 6 roles web en un mismo navegador exige cerrar sesión y volver a entrar con TOTP, porque la cookie del hosted UI es compartida. Táctico (brigadista e inspector en el Pixel): refresh de 24 h, así que hay que haber entrado en las últimas 24 h. El grep de «caduc|expira|incógnito|perfil del navegador» en GUIA, RUNBOOK y PLAN-REVISION no da nada. Añadir a la GUIA §0: un perfil de navegador por rol, abiertos la misma mañana (menos de 8 h antes), no cerrar pestañas (recargar sí conserva la sesión), y entrar en el Pixel con el rol táctico el mismo día.

## 6 · Lo que un cliente esperaría y hoy no se puede demostrar

Lista para no prometerlo y para priorizar:
(a) SMS y WhatsApp, y push en iPhone;
(b) sirena con el Pi apagado; gas, ascensores y puertas;
(c) voceo;
(d) magnitud del SSN (USGS sí, con procedencia);
(e) RTO medido;
(f) usuarios reales creados desde la consola (sale SIMULADO);
(g) reporte mensual y % de disponibilidad;
(h) QR del edificio y alta masiva de ocupantes;
(i) multi-idioma: no hay ninguna librería de i18n en web ni móvil, todo es es-MX; poca prioridad para clientes mexicanos, pero lo preguntan corporativos con personal extranjero;
(j) SSO corporativo;
(k) exportar la bitácora.
Respetar la lista «lo que NO debe decirse» del runbook y las invariantes de §14 (sin cuenta regresiva T-MINUS, sin magnitud preliminar, sin streaming crudo continuo, sin IA en la ruta de disparo, sin tocar Shake OS).

## 7 · Animaciones: inventario, propuestas y rechazos

| ID | P | Estado | Dónde | Propuesta o hallazgo | Ficha |
|---|---|---|---|---|---|
| A-060 | P1 | 🔴 DEFECTO | Consola web · MapPanel · faro de disparo (capa 'pulse') | El faro sobre los edificios que DISPARARON sigue pulsando con prefers-reduced-motion | T-8.09 |
| A-061 | P1 | 🔴 DEFECTO | Panel local edge · #banner-alert (tk-blink) | El parpadeo del banner rojo atenúa TAMBIÉN la instrucción: ~1.6:1 de contraste medio ciclo | T-8.15 |
| A-062 | P1 | 🔷 MEJORA | App móvil · feedback de pulsación (57 Pressable) | Ningún botón de la app responde visualmente al toque | T-8.11 |
| A-163 | P2 | 🔴 DEFECTO | Consola web · ConfirmButton (confirmación de acción) | «EJECUTADO» en verde antes de que responda el servidor | T-8.07 |
| A-164 | P2 | 🟠 SOSPECHA | Tres superficies · alerta sobre dato RETENIDO | La carcasa de la alerta sigue respirando/parpadeando cuando la fuente está retenida | T-8.15 |
| A-165 | P2 | 🟠 SOSPECHA | Consola web · MapPanel · faro de disparo | El faro pulsa también con el incidente en revisión (in_review), a diferencia de la tarjeta | T-8.09 |
| A-166 | P2 | 🔷 MEJORA | App móvil · háptica | No hay háptica: añadir expo-haptics en las confirmaciones críticas | T-8.15 |
| A-167 | P2 | 🔷 MEJORA | App móvil · transición a /crisis, /checkin, /alarma-inmueble | La toma de crisis hereda la transición nativa por defecto del Stack | T-8.15 |
| A-168 | P2 | 🔷 MEJORA | App móvil · pull-to-refresh | No hay gesto de refresco: añadir RefreshControl en inicio, panel, lista, sync y directorio | T-8.15 |
| A-169 | P2 | 🔷 MEJORA | App móvil · (brigadista)/lista (headcount en vivo) | Tinte único de fila cuando llega o cambia un check-in por WS | T-8.15 |
| A-170 | P2 | 🔷 MEJORA | Consola web · Modal (EpicenterModal y futuros) | Entrada/salida del modal: hoy aparece de golpe | T-8.15 |
| A-171 | P2 | 🔷 MEJORA | Consola web · OperatorMenu y desplegables | Popover del operador y desplegables abren sin transición; chevrón sólo en 2 de 5 | T-8.15 |
| A-172 | P2 | 🔷 MEJORA | Consola web · botones (estado pulsado) | Sólo existe 1 :active en todas las hojas | T-8.15 |
| A-173 | P2 | 🔷 MEJORA | Consola web · KpiStrip (contadores) | Tinte único al cambiar un KPI; nunca contar hacia arriba | T-8.15 |
| A-174 | P2 | 🔷 MEJORA | Consola web · resultado de acciones (toasts) | No existe un canal de confirmación de acciones: añadir región role=status animada | T-8.15 |
| A-175 | P2 | 🔷 MEJORA | Consola web · MapPanel (rendimiento del muro 24/7) | El rAF de 20 fps corre siempre y repinta el mapa sin nada que animar | T-8.15 |
| A-176 | P2 | 🔷 MEJORA | Panel local edge · frame loop (Pi 4 kiosco) | Ondas y rosa se redibujan a 60 fps con datos que llegan a 1 Hz | T-8.15 |
| A-177 | P2 | ❔ NO MEDIDO | Rendimiento real en dispositivo | FPS y coste de CPU/GPU de las animaciones en el Pixel, el Pi 4 y el videowall | T-8.15 |
| A-264 | P3 | 🔴 DEFECTO | App móvil · ControlSheet (deslizar para confirmar) | El resorte de regreso ignora reduce-motion y corre en el hilo JS | T-8.15 |
| A-265 | P3 | 🔴 DEFECTO | Panel local edge · lienzo de ondas (peakHold) | La retención de pico decae por FOTOGRAMA: escala y línea de pico dependen del monitor | T-8.15 |
| A-266 | P3 | 🟠 SOSPECHA | Consola web · MapPanel · anillo de arribo con reducción | Con reducción, los anillos 'ya llegó' sólo se recalculan con cada snapshot (hasta ~30 s tarde) | T-8.15 |
| A-267 | P3 | 🟠 SOSPECHA | Panel local edge · marcas SASMEX/TIER | Las marcas se deslizan con el reloj de pared mientras la traza se congela al perder conexión | T-8.15 |
| A-268 | P3 | 🔷 MEJORA | Consola web · StateFrame (carga) — animación pasiva | Barra indeterminada mientras hay consulta en vuelo (en vez de sólo 'CARGANDO · X…') | T-8.15 |
| A-269 | P3 | 🔷 MEJORA | Consola web · FeatureStrip (sismograma de features 1 s) | Cabeza de escritura que late sólo con dato vivo | T-8.15 |
| A-270 | P3 | 🔷 MEJORA | Consola web · propiedades animadas (compositor) | Tres animaciones mueven propiedades de layout o de pintura | T-8.15 |
| A-271 | P3 | 🔷 MEJORA | Consola web · cámara del mapa | easeTo sólo por acción del operador; nunca automático al llegar una alerta | T-8.15 |
| A-272 | P3 | 🔷 MEJORA | Panel local edge · ritmo y pasivas | Mismo período de latido que las otras superficies y punto de BACKFILL EN CURSO | T-8.15 |
| A-273 | P3 | 🔷 MEJORA | App móvil · sync (cola offline) | Barra indeterminada por fila en 'ENVIANDO…' y tinte al pasar a OK | T-8.15 |
| A-274 | P3 | 🔷 MEJORA | App móvil · tokens y censo de movimiento | Duraciones a mano y sin censo que obligue a consultar reduce-motion | T-8.15 |
| A-275 | P3 | 🔷 MEJORA | App móvil · pestañas (occupant / táctico) | Cambio de pestaña sin transición | T-8.15 |
| A-334 | P3 | ✅ OK | Compartido · tokens de movimiento | Inventario: tokens de duración/curva únicos para las tres superficies | T-8.15 |
| A-335 | P3 | ✅ OK | Consola web · interruptor reduced-motion | Inventario: reducción DERIVADA (tokens a 0 + keyframes apagados por selector con reposo fijado) | T-8.15 |
| A-336 | P3 | ✅ OK | Consola web · latido de dato vivo | Inventario: el halo soc-dot--pulse sólo late con frescura real | T-8.15 |
| A-337 | P3 | ✅ OK | Consola web · MapPanel (frentes P/S, ráfaga de arribo) | Inventario: frentes, dash y ráfaga apagados y DECLARADOS bajo reducción | T-8.15 |
| A-338 | P3 | ✅ OK | Panel local edge · inventario | Inventario: 2 keyframes, 0 transiciones, reducción global, latido sólo con conexión viva | T-8.15 |
| A-339 | P3 | ✅ OK | App móvil · inventario | Inventario: useReduceMotion consultado en LatidoPunto, CrisisView, PanicButton y SiteNoticeStrip | T-8.15 |
| A-340 | P3 | ✅ OK | Rechazo · camino de lectura de la crisis (tres superficies) | NO animar el texto ni la entrada de la instrucción de alerta; sólo la carcasa | T-8.15 |
| A-341 | P3 | ✅ OK | Rechazo · dato congelado o retenido | NO shimmer ni animación en DATO RETENIDO / stale, ni tween en cifras de dato | T-8.15 |
| A-342 | P3 | ✅ OK | Rechazo · mapa y rutas de alta frecuencia | NO anillos en todas las estaciones activas, ni transiciones de ruta en /console, ni salida animada de filas | T-8.15 |

**Rechazos, con su razón** (no se animan):

- **NO animar el texto ni la entrada de la instrucción de alerta; sólo la carcasa.** CrisisView, AlertBanner y #banner-alert: nada de fade-in, slide ni typewriter sobre instrucción, zona, fuente o T+. D-30 condición 1 y T-6.23 exigen legibilidad desde el primer frame, y una instrucción que aparece desvaneciéndose todavía no se puede leer. Tampoco más háptica o vibración en crisis: ya suenan la push y el loop de audio. Tampoco T-MINUS, cuenta regresiva ni magnitud preliminar (el WR-1 es un booleano). El T+ ascendente y la cuenta del modo prueba WR-1 del gabinete son correctos: la segunda es la ventana de prueba, no el sismo.
- **NO shimmer ni animación en DATO RETENIDO / stale, ni tween en cifras de dato.** Un shimmer en stale se lee como 'cargando' o 'vivo'. En este sistema la QUIETUD es el portador de lo retenido: el tramado del simulacro se detiene retenido, el latido del panel se apaga y el helicorder repinta sólo por dato. Tampoco count-up ni tween en PGA/PGV, KPIs o % de batería: 'un dato que llega deslizándose es un dato que tarda en ser cierto' (por eso la barra UPS salta con reduce).
- **NO anillos en todas las estaciones activas, ni transiciones de ruta en /console, ni salida animada de filas.** (1) Pulsar las 20+ estaciones OPERATIVAS diluye el único faro que importa (el de disparo); el enlace ya tiene glifo, opacidad y halo estático. (2) Nada de cross-fade de ruta en el muro ni en las pestañas del shell: se cambia a menudo y el contenido tiene que estar legible al instante. (3) Una fila cerrada no se desvanece: se mostraría una fila que ya no existe. (4) No animar grid-template-columns del panel de detalle: redimensiona MapLibre en cada frame. (5) El grito de rechazo del kiosco (#action-toast) entra sin animación: tiene que leerse en el primer frame.

## 8 · Cómo se verifica cada dimensión en ejecución

### Web · MONITOREO/EVALUACIÓN

```text
Arrancar localmente (no lo ejecuté): `cd web && npm run dev` con la API local y VITE_DEV_TOKEN habilitado. En '/', usar el panel LOGIN DEV con el tenant d0000000-0000-0000-0000-000000000001 y cambiar de rol en el select.

1. Aterrizaje por rol: entrar con cada uno de los 10 roles. Los 7 web deben caer en /console con las pestañas descritas; brigadista, security_guard y occupant deben ver SIN SUPERFICIE WEB.

2. Robo de foco: como tenant_admin, en /console seleccionar un incidente, pulsar REUBICAR EPICENTRO y escribir en 'LAT, LON MANUAL' o NOTA; en menos de 1 s el cursor debería salir del campo. Repetir en INICIAR SIMULACRO → NOTA o nombre de plantilla.

3. Acuse silencioso: DevTools → Network → bloquear POST /incidents/*/ack (o forzar un 409 acusando dos veces). El botón muestra EJECUTADO y no aparece ningún error.

4. Selección por sitio: sembrar dos incidentes abiertos en el mismo site_id (INSERT en incidents en la BD local) y hacer clic en la segunda fila. La fila resaltada sigue siendo la primera.

5. QUÓRUM RED: como soc_operator, enfocar un incidente con event_id. Network muestra GET /sites/{id}/commands → 403 cada 15 s.

6. Triage: como gov_operator o takab_support, abrir /triage; el panel 'Evacuación observada' queda en ERROR 403. Como soc_operator, en un incidente con dictamen PDF, pulsar el verificador: rojo (404). Como tenant_admin, en un incidente con clip CCTV disponible, pulsar DESCARGAR CLIP: no hay petición en Network.

7. Firma sin preliminar: como inspector, abrir un incidente sin filas en dictamens. No aparece FIRMAR DICTAMEN.

8. Simulacro de superadmin: como takab_superadmin, en INICIAR SIMULACRO la lista de sitios incluye varios tenants. NO pulsar INICIAR AHORA en un entorno con gabinetes reales; revisar la respuesta en un entorno de pruebas o con un test de API.

9. Modo demo: como takab_superadmin, buscar cualquier botón de encender modo demostración (no existe).

10. Sesión: revisar infra/terraform/modules/identity/main.tf:160-168 y web/src/auth/userManager.ts:24. Cerrar la pestaña obliga a volver a entrar (sessionStorage).

Tests existentes relacionados: web/src/components/Modal.test.tsx (no cubre foco), web/src/features/console/ConsolePage.test.tsx, web/src/features/triage/TriageDetail.test.tsx.
```

### Web · flota/tenants/edificio

```text
1) Levantar: `make soc-local` (docker, uv, npm) → http://localhost:5173 → LOGIN DEV → ROL + TENANT d0000000-0000-0000-0000-000000000001 → ENTRAR COMO ROL. Para cambiar de rol: menú del operador → cerrar sesión (o una pestaña nueva).
2) gov_operator en /fleet: debe aparecer [data-testid=fleet-maint-error] con 'VENTANAS DE MANTENIMIENTO SIN LECTURA'. En DevTools/Red, GET /api/maintenance-windows?active=true → 403.
3) Sirena: entrar como tenant_admin → /building/d1000000-0000-0000-0000-000000000000 (o building_admin). PROBAR SIRENA (confirmar 2 veces) → esperar el acuse del gabinete simulado → SILENCIAR SIRENA → cuando llega el acuse, [data-testid=siren-phase] vuelve a decir 'SIRENA SONANDO · ACUSADA POR EL EDGE'.
4) Usuarios: takab_superadmin → /tenants → seleccionar un cliente con usuarios → la tarjeta 'Usuarios del cliente' muestra correos de otros tenant_id (comparar con la respuesta de GET /api/users). En local el directorio puede ser 'SIMULADO'.
5) Ventana: tenant_admin → /fleet → VENTANA → motivo → en DevTools bloquear POST /api/maintenance-windows → ABRIR VENTANA: el diálogo se cierra y no aparece ningún error.
6) Autodiagnóstico: tenant_admin → /fleet → bloquear POST /api/sites/*/commands → AUTODIAGNÓSTICO SILENCIOSO: el marco queda solo con LIMPIAR, sin motivo.
7) Historial: /building/... → quedarse más de 3 min sin interactuar → aparece la franja 'DATOS RETENIDOS · hh:mm UTC' en HISTORIAL (y a los 5 min en la cabecera del sitio). Elegir 1h en un sitio sin datos recientes → los botones de rango desaparecen.
8) Fantasma: con el gabinete simulado vivo, retirarlo (necesita código de retiro rotado vía PUT /tenants/{id}/retire-code) → sale en la sección FANTASMAS sin RESTAURAR; con VER RETIRADOS tampoco aparece en la cuadrícula.
9) Invalidación de config-state: en /tenants aplicar umbrales → en la pestaña Red no hay GET /fleet/config-state inmediato, sino hasta el sondeo de 10 s.
10) E2E: `cd web && npx playwright install chromium && npm run e2e` con soc-local corriendo (solo cubre superadmin, soc_operator y tenant_admin). Unitarios: `cd web && npx vitest run src/features/{fleet,tenants,building,audit,privacy,telemetry}`.
Todo lo anterior son pasos para el agente padre. Este informe no ejecutó nada.
```

### Móvil

```text
REGLA: nada de emuladores ni AVD. Todo corre en el Pixel 8 Pro real por USB, y antes hay que pedirle a Mauricio que lo conecte.

1) Preparación: `adb devices` debe listar el serial 41270DLJG000WB. mobile/.env debe tener los 7 EXPO_PUBLIC_* sacados de los outputs de Terraform (tabla en mobile/README.md §Configuración).

2) Desarrollo con dev client: `cd mobile && REACT_NATIVE_PACKAGER_HOSTNAME=localhost npx expo run:android`. ufw bloquea el 8081, por eso se usa localhost más adb reverse tcp:8081 tcp:8081. Si lo lanza el agente, hacerlo con `setsid nohup … & disown` desde un .sh, porque si no muere en silencio. La señal buena es «Android Bundled … (N modules)» en el log de Metro. El esquema del dev client es exp+takab-ailert://expo-development-client/?url=http%3A%2F%2Flocalhost%3A8081, no takab://. Reinstalar borra la sesión: Mauricio vuelve a entrar por la Hosted UI (táctico con TOTP).

3) E2E con Maestro: sólo con APK de RELEASE: `cd mobile/android && ./gradlew :app:assembleRelease -PreactNativeArchitectures=arm64-v8a && adb install -r app/build/outputs/apk/release/app-release.apk`. Después: `make cloud-staging-incident PHASE=<crisis|conclude|roster|reentry|reset>` y `TAKAB_MAESTRO_ENV=.env.e2e mobile/.maestro/run.sh <flujo>.yaml`. Nunca con SITE_CODE=site-dev. Los flujos 02 y 05 piden TOTP tecleado a mano. Los flujos 05a/b/c van con run-offline.sh, que apaga el WiFi de verdad.

4) Reproducir la sesión de 60 min (antes del arreglo): entrar como ocupante, dejar la app abierta en INICIO 61-62 min. Esperado: vuelve a la pantalla de login. Ver `adb logcat | grep ReactNativeJS` y el 401 de /sites/{id}/mobile-state en los logs del API. Variante táctica: pestaña PANEL abierta; el WS se cierra con 4401 al minuto 60.

5) Después del arreglo:
- (a) La sesión sobrevive más de 60 min. En los logs del API se ve un token nuevo cada ~55 min, y en CloudWatch/Cognito la llamada /oauth2/token con grant_type=refresh_token.
- (b) Offline: WiFi apagado más de 60 min, luego se enciende: la app renueva, drena la cola sin pedir login y la pastilla LIVE vuelve a ready.
- (c) Security_guard o building_admin con authAt de más de 24 h pasan al login.
- (d) Cerrar sesión y volver a entrar pide credenciales (la cookie de la Hosted UI quedó borrada).
- (e) Decodificar un ID token renovado y comprobar si conserva el auth_time original.

6) Defectos de pantalla:
- Dictamen: PHASE=reentry, entrar como brigadista, PANEL → «VER DICTAMEN» → sale «Sin incidente activo».
- Cuenta sin red: WiFi apagado y arranque en frío → CUENTA muestra error sin CERRAR SESIÓN.
- Cámara: CAPTURAR, mover el teléfono y pulsar USAR ESTA FOTO; bajar la evidencia desde la consola y comparar con lo que se encuadró.
- 05b: sin red, tocar VERIFICAR → aparece el aviso de error y en SYNC no hay ningún item nuevo, aunque el flujo sale verde.
- Dictamen: esperar más de 5 min en la pantalla y tocar DESCARGAR → no pasa nada.

7) Sin teléfono (no es probar la app): `cd mobile && npm test && npm run typecheck && npx expo lint`.
```

### Sesiones por rol

```text
1) auth_time al refrescar (Cognito real, lo más importante): en la consola desplegada, iniciar sesión con usuario de prueba, abrir devtools y forzar un refresh (p.ej. import del UserManager o esperar al silent renew). Decodificar el id_token nuevo (base64 del payload) y comparar auth_time con iat: se espera auth_time = hora del login original e iat = ahora. Alternativa por CLI (cliente público, sin secret): `aws cognito-idp initiate-auth --auth-flow REFRESH_TOKEN_AUTH --client-id <mobile_tactical> --auth-parameters REFRESH_TOKEN=<rt>` y decodificar AuthenticationResult.IdToken.
2) Defecto del WS en web (hoy): `POST /dev/token` con expires_in=120 y login dev en la consola local (VITE dev); esperar unos 2 min con /console abierto y comprobar en devtools > Network > WS el cierre 4401 seguido de logout. Con Cognito real, dejar la consola abierta más de 60 min y observar la redirección a /logout.
3) Defecto del móvil (hoy, en el Pixel): iniciar sesión táctica u ocupante, esperar más de 61 min, matar y reabrir la app (o abrirla desde una push): se espera caer al login y no a panel/crisis.
4) Tras implementar: `pytest api/tests/auth api/tests/ws api/tests/api/test_command_mfa.py api/tests/test_docs_consistency.py`; casos con auth_utils: soc_operator con auth_age=86401 → 401 con detail 'sesion_expirada' y WWW-Authenticate error_description; brigadista con 29 d → 200; WS con sesión caducada → cierre 4440. `terraform test` en infra/terraform/modules/identity (mfa + sesion.tftest.hcl nuevo). web: `npm test` (vitest) + e2e con /dev/token auth_age_s. mobile: `npm test && npm run typecheck && npx expo lint`.
5) Revisión del plan con `terraform plan` en envs/dev: solo deben cambiar las tres aws_cognito_user_pool_client (in-place), sin recrear pools.
```

### RBAC y flujos

```text
Solo lectura. Estos pasos los ejecuta Mauricio; yo no corrí ninguno.

1) Paridad RBAC: `cd api && uv run pytest tests/auth/test_matrix.py -q`.

2) Tokens de Cognito:
`AWS_PROFILE=takab-dev aws cognito-idp describe-user-pool-client --user-pool-id <pool> --client-id <takab-web|takab-mobile-tactical|takab-mobile-occupants> --query 'UserPoolClient.[RefreshTokenValidity,TokenValidityUnits]'`

3) Sesión móvil de 60 min (en el Pixel): entra con el táctico y con el ocupante, deja la app 61 min, vuelve y haz cualquier acción. Lo esperado según el defecto es que te mande al login. En logcat busca el 401 de /me o el cierre 4401 del WS.

4) Web:
· Entra como takab_support y como gov_operator, abre EVALUACIÓN con un incidente. Debe salir «GET /incidents/{id}/cctv falló (403)».
· Como gov_operator, pulsa ACUSAR en MONITOREO: 404 si tenant-dev sigue en 'private'. Compruébalo con `SELECT code, visibility FROM tenants;` por el túnel `make db-tunnel`.

5) building_admin: entra en la web y confirma que no existe la pestaña FLOTA ni hay otra vía hacia códigos de enrolamiento o autodiagnóstico. Con `curl -H "Authorization: Bearer <id_token building_admin>" -X POST $API/sites/<id>/enrollment-codes` la API responde 201.

6) Alta de táctico: en /tenants → Usuarios, crea un brigadista con los valores por defecto y entra en la app. Debe salir /denied (surface web) o «sin sitio vigilado» (site_scope '*').

7) Arranque sin red: con el táctico ya con sesión, activa modo avión, mata la app y ábrela. Deberían faltar PANEL, TRIAGE y LISTA.

8) SOC: con un incidente abierto y check-ins de ocupantes, confirma que MONITOREO y EVALUACIÓN no muestran quién pidió ayuda.

9) auth_time: decodifica un ID token antes y después de un refresh (jwt.io o `python -c` con base64) y comprueba que auth_time se conserva. Es la base del tope de 30 d / 1 d por rol.
```

### PDF

```text
A) GENERAR EN LOCAL SIN NUBE NI BASE (render puro con los modelos de las pruebas) y RASTERIZAR:
cd /home/maubautista/Documentos/Desarrollo/Alertamiento_Sismico/api && mkdir -p /tmp/takab-pdf && PYTHONPATH=.:src uv run python - <<'EOF'
import hashlib
from pathlib import Path
from tests.dictamen.test_pdf import model
from tests.documentos.test_geometria import _modelo_con_todas_las_figuras
from tests.dictamen.test_fotos_en_el_papel import _foto, _dano, _jpeg
from tests.api.test_drill_report import _rep
from takab_api.dictamen.pdf import render
from takab_api.dictamen.model import FotoFila
from takab_api.documentos.fotos import preparar
from takab_api.narrative import apply_narrative
from takab_api.narrative.base import Narrative
from takab_api.narrative.prompts import SECTION_TITLES
from takab_api.drill_report import render as render_drill, SitioReporte
o = Path('/tmp/takab-pdf'); w = lambda n, b: (o/n).write_bytes(b)
w('01-tecnico.pdf', render(model(), 'technical'))
w('02-ejecutivo.pdf', render(model(), 'executive'))
w('03-repro-tecnico.pdf', render(model(reproduccion=True), 'technical'))
w('04-repro-ejecutivo.pdf', render(model(reproduccion=True), 'executive'))
w('05-todas-figuras.pdf', render(_modelo_con_todas_las_figuras()))
w('06-una-foto.pdf', render(model(danos=[_dano([_foto(3)])])))
c = _jpeg(9, w=1200, h=1600); d = preparar(c); h = hashlib.sha256(c).hexdigest()
r = FotoFila(evidence_id='00000009-aaaa-bbbb-cccc-dddddddddddd', sha256_declarado=h, sha256_medido=h, sha256_impreso=d.sha256, ancho=d.ancho, alto=d.alto, jpeg=d.jpeg)
w('07-fotos-retrato.pdf', render(model(danos=[_dano([r, r, r])])))
m = model(); apply_narrative(m, Narrative(sections=tuple((t, 'Prosa con acentos: ñ á é í ó ú ü.') for t in SECTION_TITLES), provider='openrouter')); w('08-narrativa-ia.pdf', render(m))
m = model(); apply_narrative(m, Narrative(sections=tuple((t, 'Prosa determinista.') for t in SECTION_TITLES), provider='deterministic', degraded_reason='el proveedor no respondió (prueba)')); w('09-narrativa-degradada.pdf', render(m))
L = 'Torre Corporativa Reforma 222 · Edificio B Norte'
w('10-simulacro.pdf', render_drill(_rep(SitioReporte(site_name='Planta Cholula', commandable=True, acked=True, latency_s=4.2), SitioReporte(site_name=L, commandable=True, acked=False, latency_s=None, command_status='expired'), SitioReporte(site_name=L, commandable=False, acked=False, latency_s=None))))
EOF
cd /tmp/takab-pdf && for f in *.pdf; do pdftoppm -r 110 -png "$f" "${f%.pdf}"; done; pdftoppm -r 110 -png /home/maubautista/Documentos/Desarrollo/Alertamiento_Sismico/shared/brand/membrete/carta.pdf hoja
for f in /tmp/takab-pdf/*.pdf; do echo "== $f"; pdfinfo "$f" | grep -E 'Pages|Page size'; pdffonts "$f" | tail -n +3; pdftotext -layout "$f" - | grep -nE 'REPRODUCCIÓN|NARRATIVA DEGRADADA|ASISTENCIA DE IA|TIPOGRAFÍA DEGRADADA|^ *\. QU|warning|structural|people_trapped|reentry|PRELIMINAR|FIRMADO|SHA-256 DEL CONTENIDO'; done
Qué mirar en los PNG: 06 (pie de foto pisado por «15. EVACUACIÓN…»), 07 (foto vertical invadiendo el pie), 02 y 04 (títulos «. QUÉ PASÓ», sin REPRODUCCIÓN), 10 (líneas de sitio que pasan del margen derecho), 01 (portada con «warning», §11 FECHA sin UTC), 08 y 09 (rótulo de IA o NARRATIVA DEGRADADA al pie de la §16), recuadros de ausencia de más de 2 renglones, y el pie en todas las páginas (folio, Pág. X de N, hash de 64 caracteres, EVENTO … UTC, razón social y domicilio).

B) GUARDAS (sin tocar la nube): cd api && DATABASE_URL=postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab_test uv run pytest -q tests/dictamen tests/documentos tests/narrative tests/api/test_reports.py tests/api/test_drill_report.py (las de tests/api necesitan `make test-db`).

C) EXTREMO A EXTREMO EN LOCAL (API + MinIO): make db objetos demo-db; bash demo/soc_local.sh (pone TAKAB_API_EVIDENCE_BUCKET=takab-dev-evidence, TAKAB_API_S3_ENDPOINT_URL=http://127.0.0.1:9000 y las credenciales de MinIO); make web. En la consola, con el dev-login como takab_superadmin o inspector: Triage → incidente → «DICTAMEN PDF» (se abre en una pestaña). Para el ejecutivo, con el token de dev: curl -s -X POST -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8000/incidents/$IID/report?variant=executive" | jq -r .url | xargs curl -s -o /tmp/takab-pdf/ejecutivo-local.pdf. Simulacro: Consola → Historial de simulacros → «EXPORTAR REPORTE» (superadmin o tenant_admin), o POST /drills/$DID/report. Para verificar: con superadmin, pulsar «VERIFICAR HASH» junto a «Dictamen emitido» (se espera rojo, por el defecto de roles); con inspector debería salir «HASH VERIFICADO». Los objetos se ven en la consola de MinIO en http://127.0.0.1:9001.

D) NUBE DESPLEGADA (base https://16-58-11-196.sslip.io/api, token de Cognito de inspector o superadmin). Cuidado: cada generación gasta el freno (6/min por usuario, 20/min por sitio), llama a OpenRouter con coste y deja una fila de evidencia inmutable. curl -s -X POST -H "Authorization: Bearer $TOKEN" "https://16-58-11-196.sslip.io/api/incidents/$IID/report?variant=technical" | tee /tmp/takab-pdf/resp.json | jq -r .url | xargs curl -s -o /tmp/takab-pdf/nube-tecnico.pdf && sha256sum /tmp/takab-pdf/nube-tecnico.pdf && jq -r .sha256 /tmp/takab-pdf/resp.json (los dos sha deben coincidir). Luego: pdftotext -layout nube-tecnico.pdf - | grep -nE 'ASISTENCIA DE IA|NARRATIVA DEGRADADA|REPRODUCCIÓN|SIN DATOS|SHAKEMAP|NO CALCULADO' y pdftoppm -r 110 -png nube-tecnico.pdf nube. Para volver a bajar uno existente: POST /api/evidence/$EVID/download (roles con export). Para verificarlo: POST /api/evidence/$EVID/verify (inspector o building_admin). Simulacro: POST /api/drills/$DID/report (superadmin o tenant_admin), solo con el simulacro YA CERRADO para no sobrescribir la clave fija. Acto 4 del guion: bash deploy/demo/guion.sh --reporte (localiza el último report_pdf y cuenta sus imágenes con pdfimages). En el móvil: tras firmar como inspector, generar el PDF desde Triage ANTES de abrir «Certificado» en el teléfono, y comprobar que el PDF descargado dice FIRMADO.
```

### Estatus visibles

```text
No ejecuté ninguno de estos pasos: son pasos sugeridos para comprobarlo en ejecución.

1) Disco y evidencia descartados (P1):
   - `curl -s -H "Authorization: Bearer $TOKEN" $API/fleet/gateways | jq '.[] | {serial, disk_used_pct, evidence_pending, evidence_oldest_age_s}'`
   - Compáralo con `psql -c "SELECT ts, disk_used_pct, evidence_pending, evidence_oldest_age_s FROM device_health WHERE gateway_id='<id>' ORDER BY ts DESC LIMIT 1"`.
   - Esperado: la base tiene valores y la API devuelve null. En el navegador, /fleet: la tarjeta dice «s/d · el gabinete no pudo mirar».
   - Fijarlo con un test en api/tests/api/ que siembre device_health con disk/evidence y compruebe la respuesta de GET /fleet/gateways.

2) LWT (P1):
   - En un gabinete de prueba (no el sitio real, D-34), corta la sesión MQTT (`sudo systemctl stop takab-edge` o cortar la red).
   - Tras el LWT, ejecuta `SELECT ts, reason, power_status, mqtt_rtt_ms FROM device_health WHERE gateway_id='<id>' ORDER BY ts DESC LIMIT 3`.
   - Durante los 5 min siguientes, consulta `GET /fleet/gateways` y `GET /map/state`. Esperado con el defecto: derived_state=OPERATIVO con métricas null, y gateways.status='offline'.

3) SOH en DetailPanel:
   - /console → selecciona un sitio. Detén SeedLink o el sensor 10 min.
   - La tarjeta «Features Live» pasa a «SIN FEATURES» y los badges NTP y LAG desaparecen.
   - Compara con /building/:id, que sí muestra la edad del SOH.

4) inspector / building_admin: entra con ese rol a /building/:id recién cargada. Aparece «SIN LATIDO DEL GABINETE EN ESTA SESIÓN» hasta el siguiente latido (≤60 s).

5) Nivel de alerta: DevTools → Network → WS. Hay frames `site_state` con `kind:"rule_evaluation"` y ninguna parte de la UI cambia.

6) MODO PRUEBA WR-1 y actuation_records:
   - En el panel LAN del gabinete de prueba, arma MODO PRUEBA WR-1.
   - La consola no muestra nada.
   - `SELECT occurred_at, cause, actor, action, success, online FROM actuation_records ORDER BY occurred_at DESC LIMIT 10` muestra la fila, y ningún endpoint la sirve (`grep -rn actuation_records api/src/takab_api/routers` → vacío).

7) Firmware en el panel LAN: `curl http://<pi>:<puerto>/api/status | jq 'keys'` → no aparece fw_version ni fw_running.

8) Simulacro expirado: lanza un simulacro a un sitio cuyo gabinete esté SIN ENLACE. Tras el TTL, DrillHistory dice «1 RECHAZADO(S)» y `SELECT status FROM commands WHERE command_id=...` devuelve 'expired'.

9) Endpoints sin consumidor (comprobación rápida):
   - `grep -rn "rollouts\|ops/alerts\|ai_spend\|privacy/erasure" web/src --include=*.ts* | grep -v test` → vacío.
```

### Animaciones

```text
Consola web:
1) Levantar la consola dev con el seed local y sembrar un sitio con felt='trip' (un incidente abierto con pico ≥ umbral de disparo). En Chrome DevTools > Rendering > 'Emulate CSS media feature prefers-reduced-motion: reduce' abrir /console. En la consola JS obtener la instancia del mapa y leer map.getPaintProperty('pulse','circle-radius') dos veces con 500 ms de diferencia: si cambia, el DEFECTO P1 sigue vivo. La leyenda dirá igualmente 'ANILLOS ESTÁTICOS'.
2) ConfirmButton: en /building/:siteId con la red en 'Offline' (DevTools > Network), pulsar PROBAR SIRENA dos veces: el botón dirá 'EJECUTADO' en verde aunque la petición falle.
3) Pasar el incidente a in_review y comprobar que la tarjeta deja de respirar mientras el faro del mapa sigue pulsando.
4) Contratos existentes: `cd web && npx vitest run src/styles/motionInvariants.test.ts` y `npx playwright test e2e/motion.spec.ts`. Las propuestas nuevas deben mantenerlos en verde, y cada keyframe nuevo tiene que entrar al grupo animation:none.

Panel del gabinete:
5) Abrir http://<pi>/?demo=alerta y medir el contraste de '.big' en la fase baja de tk-blink (DevTools > Animations a 10 %, pausar en la fase 0.35 y usar el color picker). Con el panel real y una alerta activa, cortar la red (DevTools offline): el pill pasará a 'DATO RETENIDO' mientras el banner rojo sigue parpadeando.
6) peakHold: abrir el panel en un monitor de 60 Hz y otro de 144 Hz (o forzar el throttling de CPU) con la misma escena demo y comparar cuánto baja la línea de pico en 1 s.
7) Tests: `cd edge && pytest tests/test_local_api_panel.py -k "parpadeo or pulse or movimiento"`.

App móvil:
8) En el Pixel, Ajustes > Accesibilidad > Quitar animaciones. Abrir el deslizador del panel táctico, soltarlo a medias y observar que la perilla sigue regresando con resorte. Tocar cualquier botón: no hay respuesta visual al presionar. Con `adb shell dumpsys gfxinfo <paquete>` medir los frames durante el halo de /crisis (sembrar con infra/scripts/seed_staging_incident.sh).
9) Push a /crisis sin la preferencia: grabar con `adb shell screenrecord` para ver la transición de entrada del Stack.
```

### Funciones básicas

```text
1) Conteo del backlog: `grep -c '^### \[ \]' takab-docs/TASKS.md` (39), `grep -c '^### \[~\]'` (11), `grep -c '^### \[x\]'` (392). Listado: `grep -n '^### \[ \]\|^### \[~\]' takab-docs/TASKS.md`.
2) Sesión móvil (P0): `grep -rn "refreshToken\|refreshAsync" mobile/src --include=*.ts*` muestra que solo se guarda. En el Pixel: iniciar sesión, esperar más de 60 min (o adelantar el reloj), reabrir la app; se espera la pantalla de login. En paralelo, `adb logcat | grep -i 401`.
3) Duración por app client: `aws cognito-idp describe-user-pool-client` para takab-web, takab-mobile-tactical y takab-mobile-occupants (RefreshTokenValidity/TokenValidityUnits), contrastado con infra/terraform/modules/identity/main.tf:160-168,629-635,665-671.
4) Usuarios simulados: abrir /tenants con tenant_admin en la nube y ver si UsersCard dice «DIRECTORIO SIMULADO»; en la instancia, `grep COGNITO_USER_POOL_ID /etc/takab/cloud.env`.
5) Contradicción con cuórum: `edge/simulators/fleet.py --replay --armar` con 2 o más estaciones y comparar el data-authorizes del banner (web) con «CONFIRMADO · N ESTACIONES» en el Pixel.
6) Apartado 14 del PDF: POST /incidents/{id}/report en un incidente con un reporte de daño con foto y revisar la sección «DAÑOS REPORTADOS EN CAMPO».
7) Huecos de alta: `grep -rn "INSERT INTO zones" api/src` (vacío), `grep -rn user_zone_assignments api/src | grep -i delete` (vacío), `grep -rniE "qr|barcode" web/src mobile/src` (vacío), `grep -rn allow_admin_create_user_only infra/terraform/modules/identity/main.tf`.
8) Sin UI: `grep -rniE "rollout|SiteIdUpdate|sensorsSensorId|AssetsPost|erasure|notify/test" web/src` (vacío).
9) Presentación: `bash deploy/demo/goal-presentacion.sh` y `bash deploy/demo/guion.sh --preflight` (solo lectura).
```

### Edge/nube/presentación

```text
Todo lo siguiente es de lectura, salvo lo marcado.

1) Estado de la rama y de lo desplegado:
`git log --oneline main..fix/instrumentos-y-documentos-de-la-presentacion`
`TAG=$(curl -s https://16-58-11-196.sslip.io/api/health | jq -r .build)`; después `. <(sed -n '/^rutas_que_llegan_a_la_nube()/,/^}$/p' deploy/cloud/conformidad.sh)` y `git diff --stat $TAG..HEAD -- $(rutas_que_llegan_a_la_nube)`

2) Goal de la presentación, desde la rama:
`aws sso logout && aws sso login --profile takab-dev` y luego `bash deploy/demo/goal-presentacion.sh` (salida 0 = listo · 1 = arregla el sistema · 3 = arregla el instrumento)
`AWS_PROFILE=takab-dev bash deploy/demo/guion.sh --preflight`

3) Reset sin PIN (confirma el hallazgo del guion y el RUNBOOK): `grep -n 'api/reset' deploy/demo/guion.sh takab-docs/runbooks/RUNBOOK-demo-cliente.md`. El 401 está medido en GUIA:279-297. No hace falta repetir el POST.

4) Dueño de los pines (edge 7.b): `ssh takab-pi5 'sudo cat /var/lib/takab/gpio.lock; readlink -f /opt/takab/edge; ls -1dt /opt/takab/releases/*/'`. Después `ps -o lstart= -p <pid>` del dueño, comparado con la fecha de cada release.

5) Watchdog de hardware y reloj: `ssh takab-pi5 'grep -r RuntimeWatchdogSec /etc/systemd/system.conf.d/ ; grep watchdog /boot/firmware/config.txt; timedatectl; systemctl is-enabled systemd-time-wait-sync chrony-wait 2>&1; sudo dmesg -T | grep "eth0: Link is"'`

6) Congelamiento por el PDF (N2): en una terminal, `while :; do curl -s -o /dev/null -w '%{time_total}\n' https://16-58-11-196.sslip.io/api/health; sleep 0.5; done`; en la consola, generar un reporte técnico de un incidente con fotos. Los picos de varios segundos confirman el hallazgo.

7) Caída durante el despliegue (N1): el mismo bucle de curl mientras corre `make cloud-deploy`. Esto sí tiene efectos: solo en una ventana acordada, nunca el día de la demo.

8) Colas SQS: `aws cloudwatch get-metric-statistics --namespace AWS/SQS --metric-name ApproximateAgeOfOldestMessage --dimensions Name=QueueName,Value=takab-dev-q-events ...` y comprobar que ninguna alarma lo vigila: `aws cloudwatch describe-alarms --query 'MetricAlarms[].MetricName'`.

9) Sesiones: `aws cognito-idp describe-user-pool-client --user-pool-id <pool> --client-id <web|tactical|occupants>` y mirar RefreshTokenValidity y TokenValidityUnits.

10) Incidentes del ensayo 1: en la consola, Triage del sitio d1000000-… → clasificar d5af54e5 y b420daaa como `reproduccion` y después actualizar el § Registro del RUNBOOK.

11) Pixel: `adb get-state` y `mobile/.maestro/run.sh 01a-crisis.yaml` (y 01b, 02, 03), y `( cd web && PW_BASE_URL=https://16-58-11-196.sslip.io npx playwright test e2e/deployed.spec.ts e2e/screens.spec.ts )`. Solo con el Pixel real, nunca emuladores.
```

## 9 · Preguntas abiertas del descubrimiento

Las de sesión las resolvió Mauricio el 2026-09-22 y quedan en `D-38`: 30 d brigadista/inspector,
90 d ocupante, 24 h el resto; `localStorage` en la consola con tope en el servidor; aviso sin
prórroga para el SOC. Las demás siguen abiertas y cada una vive en la ficha que la necesita.

- *Web · MONITOREO/EVALUACIÓN* — Sesión por rol: Cognito fija la vigencia del refresh token por app client, no por rol. ¿Se aceptan app clients separados (p.ej. uno de campo de 30 días para brigadista e inspector, y ocupantes a 30 días en lugar de 90) y takab-web a 24 h en localStorage? ¿O el inspector en web también debe durar 1 mes? Hoy security_guard y building_admin comparten mobile_tactical con brigadista e inspector.
- *Web · MONITOREO/EVALUACIÓN* — ¿Encender el modo demostración queda fuera de la UI a propósito (solo por guion o CLI) o es una omisión? Es clave para la presentación a clientes.
- *Web · MONITOREO/EVALUACIÓN* — ¿takab_superadmin debe poder lanzar un simulacro que abarque a varios clientes? Si no, ¿POST /drills debe exigir tenant_id explícito a los roles internos como hace resolve_write_tenant?
- *Web · MONITOREO/EVALUACIÓN* — ¿Siempre existe un dictamen preliminar automático antes de que el inspector firme, o la web debe permitir firmar el primer eslabón de la cadena?
- *Web · MONITOREO/EVALUACIÓN* — ¿Que gov_operator, inspector y building_admin no vean las ventanas de mantenimiento activas es una decisión, o debe cumplirse el comentario de maintenance.py ('lo puede ver cualquiera que llegue a la consola')?
- *Web · MONITOREO/EVALUACIÓN* — ¿Se quiere en el shell un selector o filtro de tenant para los roles internos durante la demo, o se hará con un usuario tenant_admin del cliente de demostración?
- *Web · MONITOREO/EVALUACIÓN* — ¿La tarjeta CCTV del DetailPanel de /console debe seguir diciendo 'PENDIENTE DE HARDWARE' en sitios que ya tienen cámara (T-3.12)?
- *Web · flota/tenants/edificio* — gov_operator conserva /fleet (matrix.py:78), pero maintenance.py no le deja leer ventanas: ¿se le concede lectura de ventanas, o solo se oculta el aviso cuando `forbidden`? La decisión cambia si gov ve que hay 'alarmas silenciadas' en clientes gov_shared.
- *Web · flota/tenants/edificio* — Tarjeta de usuarios para roles internos: ¿filtrar por el cliente seleccionado en la ficha (lo que promete el subtítulo) o mostrar un directorio global con columna CLIENTE?
- *Web · flota/tenants/edificio* — Prueba de sirena: ¿el edge apaga la sirena solo tras un tiempo máximo de prueba? Si no, el panel web es el único que puede silenciarla y el defecto de fase pesa más. NO_MEDIDO estáticamente.
- *Web · flota/tenants/edificio* — ¿Debe una estación nueva exigir que se coloque el marcador en el mapa (no aceptar DEFAULT_PICK de Puebla)?
- *Web · flota/tenants/edificio* — Petición del usuario sobre la duración de sesión (1 mes para brigadista/inspector/ocupante, 1 día para el resto): en Cognito la validez del refresh token se define por app client, no por rol, así que haría falta separar app clients o pools por perfil. /dev/token limita expires_in a 86400 s. Queda fuera de esta dimensión; NO_MEDIDO en infra/terraform.
- *Web · flota/tenants/edificio* — ¿Las interfaces faltantes (rotar el código de retiro, rollouts de firmware, aviso de privacidad y ARCO, gestión de sensores) entran en el alcance de la presentación, o se quedan como operación por API/curl de TAKAB?
- *Móvil* — Ocupante: el cliente de Cognito ya da 90 días de refresh. «1 mes», ¿se toma literal (bajar a 30 días) o vale como mínimo y se deja en 90?
- *Móvil* — Tácticos: brigadista/inspector (30 días) y security_guard/building_admin (1 día) comparten el cliente takab-mobile-tactical. ¿Se acepta un único cliente de 30 días con el límite de 1 día impuesto por la app y el API, o se prefiere un tercer cliente con otro botón de login?
- *Móvil* — ¿Cognito conserva el auth_time original en los ID tokens renovados? Está NO_MEDIDO y decide si el API puede imponer el día de validez por rol.
- *Móvil* — ¿Se activa la rotación de refresh tokens? Obliga a quitar ALLOW_REFRESH_TOKEN_AUTH de los tres clientes, y hay que confirmar que ninguna herramienta (scripts de siembra o E2E) usa ese flujo.
- *Móvil* — «A los demás perfiles, 1 día»: ¿incluye la consola web? Hoy el cliente web tiene 8 h de refresh y la consola tampoco renueva, así que en la práctica dura unos 60 min.
- *Móvil* — ¿Los teléfonos de guardia se comparten por turno? Eso decide la prioridad de sellar el sub en la cola offline y el onboarding/consentimiento por usuario.
- *Móvil* — ¿Es intencional que el táctico vea «Vincular a un edificio» en Cuenta y pueda consumir un código de ocupante que cambia su sitio vigilado?
- *Móvil* — ¿Sigue vigente la aceptación de la spec 0.1 (crisis visible con la sesión caducada si hay un incidente cacheado de menos de 15 min)? Hoy crisis.tsx la contradice al redirigir.
- *Sesiones por rol* — ¿El inspector debe tener 30 días también en la consola web (opción A: web a 30 d y la API topa a 24 h al resto) o basta con 30 d en el móvil y 24 h en web como todos (opción B, recomendada por el riesgo XSS en la consola pública)?
- *Sesiones por rol* — Occupant: ¿bajar el client de ocupantes de 90 a 30 días, o mantener 90 (también cumple 'no pedir durante 1 mes' y respeta la 'sesión de larga vida' de la especificación §0.1/§8)? El tope de la API debe coincidir con lo que se decida.
- *Sesiones por rol* — ¿El día o el mes se cuentan desde el login (tope absoluto, propuesto) o desde la última actividad (inactividad)? Cognito solo soporta el absoluto por client; la inactividad exigiría estado en el servidor.
- *Sesiones por rol* — Consola web: ¿se acepta guardar la sesión en localStorage (sobrevive a pestañas y reinicios; exige CSP y revocación) o se mantiene sessionStorage (el día solo vale dentro de la misma pestaña)?
- *Sesiones por rol* — Para brigadista e inspector con 30 d, ¿se exige confirmación biométrica local antes de activar o silenciar la sirena como compensación de la regla de oro 8?
- *Sesiones por rol* — SOC con tope de 24 h: ¿basta con un aviso previo y 'renovar ahora', o se quiere gracia mientras haya un incidente activo?
- *RBAC y flujos* — Duración por rol: el alcance literal es 30 días para brigadista, inspector y occupant, y 1 día para los demás. ¿Eso incluye a security_guard y building_admin en el móvil? Comparten el cliente mobile_tactical con brigadista e inspector, así que distinguirlos exige un tope por auth_time en la API o clientes separados.
- *RBAC y flujos* — ¿Los 30 días del inspector aplican también a la consola web? El cliente takab-web lo comparten los 7 roles web: habría que poner el refresh a 30 d y recortar a 1 d por rol con auth_time.
- *RBAC y flujos* — Ocupante: el refresh configurado es de 90 días. ¿Se baja a 30 o se queda en 90, que cumple «al menos 1 mes»?
- *RBAC y flujos* — Extender el refresh táctico a 30 días contradice lo que dicen infra main.tf:646 y la spec móvil §8 («refresh corto, las acciones tácticas re-verifican token»). ¿Se registra como una D-xx nueva que revoca ese criterio? La guarda de MFA (por procedencia del pool) no se rompe.
- *RBAC y flujos* — gov_operator de la demo: ¿se crea un tenant «Protección Civil» propio y se marca como gov_shared el tenant cliente de la demo, para que el acuse funcione y se vea el aislamiento?
- *RBAC y flujos* — ¿Dónde quieres los códigos de enrolamiento y el autodiagnóstico del building_admin: en /building/:siteId (web) o en una pantalla de la app táctica?
- *RBAC y flujos* — ¿Debe tenant_admin poder descargar (export) el PDF de dictamen y el miniSEED de su propio edificio? Hoy §2 le da solo Lectura.
- *RBAC y flujos* — Arranque sin red: ¿se acepta guardar en caché el último /me para mostrar las pestañas tácticas (el servidor revalida al sincronizar), o se mantiene el default-deny?
- *RBAC y flujos* — ¿Qué acciones que hoy son solo API deben tener pantalla antes de la presentación (código de retiro, aviso de privacidad, ARCO por escrito, planos de evacuación, modo demo, firmware)?
- *PDF* — ¿Se enseñará el resumen ejecutivo al cliente? Si es así, hace falta un botón o desplegable en Triage (hoy solo sale por API) y decidir si debe llevar la leyenda REPRODUCCIÓN.
- *PDF* — ¿La clasificación humana del incidente (reproduccion, prueba, falso_positivo) debe rotular el papel? La decisión actual (model.py:1006-1013) deriva el rótulo SOLO de seismic_events.meta.reproduccion, y los ensayos de T-7.28 se clasifican a mano como 'reproduccion'.
- *PDF* — Verificador del dictamen en Triage: ¿se concede el alcance de verificación de report_pdf a los roles de consola (superadmin, tenant_admin, soc, gov, support) o se oculta el botón a quien no tiene dictamen_read?
- *PDF* — ¿tenant_admin (el administrador del cliente) debería poder generar el dictamen PDF? Hoy generate_report es solo de superadmin e inspector, así que su botón sale deshabilitado.
- *PDF* — ¿Qué se imprime en «FIRMÓ»: el UUID de Cognito (hoy), el rol + display_name de user_profiles, o solo el rol? Hay que conciliarlo con D-32 y D-36.
- *PDF* — ¿Se añade la hora local (zona del sitio, America/Mexico_City) junto a la UTC en la portada, el simulacro y la cronología?
- *PDF* — Reporte de simulacro: ¿se prohíbe exportar un simulacro en curso, o se pasa a clave S3 con sello o sha, para no dejar filas de evidencia apuntando a un objeto sobrescrito?
- *PDF* — ¿Con qué incidente y qué rol se hará el acto del PDF en la presentación? Según el plan, en la nube no hay ningún incidente con fotos Y miniSEED a la vez, ni snapshots del mapa de sacudida.
- *PDF* — ¿Entran en el alcance de la presentación un informe de pase de lista y participación (Protección Civil) y una exportación de auditoría o compliance, o se declaran fuera?
- *Estatus visibles* — ¿Debe el SOC (soc_operator/tenant_admin/gov_operator) ver un conteo AGREGADO sin PII del pase de lista (a salvo / necesitan ayuda / sin reportar)? Hoy el RBAC limita el roster a los tácticos móviles (RBAC-TAKAB.md:329).
- *Estatus visibles* — ¿Los despliegues canary y las actualizaciones o rollbacks de firmware entran en la presentación con clientes, o son herramienta interna/CI? Define si la pantalla de rollouts es P2 o P3.
- *Estatus visibles* — ¿El costo IA (ai_spend) y la procedencia de la narrativa deben verlos el tenant_admin o sólo los roles internos de TAKAB?
- *Estatus visibles* — ¿LoRa (secundarios) y BACnet (gas/ascensores/puertas) se presentan como funciones operativas o como roadmap, dado que D-16 no compró el hardware de G-02 y BACnet sólo corre en simulador?
- *Estatus visibles* — ¿Una fila de presencia (LWT offline/online) debe contar como «latido» para derivar OPERATIVO/SIN ENLACE y para is_ghost? El docstring de handle_status la usa para «retirado que late», pero no distingue el LWT offline.
- *Estatus visibles* — relays_state=None: ¿se pinta ARMADO por compatibilidad (useFleet.ts) o S/D (comentario de schemas/fleet.py)? Hay que dejar una sola verdad escrita.
- *Estatus visibles* — ¿Se añade test_mode_active del WR-1 al latido (contrato aditivo) para que la nube lo vea, o basta con exponer actuation_records?
- *Animaciones* — ¿Con dato RETENIDO la alerta debe dejar de latir en las tres superficies (web AlertBanner, CrisisView móvil, #banner-alert del gabinete) manteniendo la carcasa puesta? D-30 condición 3 dice 'se detiene por estado' y no menciona la frescura; necesita decisión de Mauricio por el riesgo de que se lea como 'ya pasó'.
- *Animaciones* — ¿El faro del mapa sobre los edificios que dispararon debe cesar al pasar el incidente a in_review, como la tarjeta (D-33)? Hoy lo alimenta cualquier incidente con state <> 'closed'.
- *Animaciones* — ¿Se autoriza mover tk-blink de #banner-alert a un ::after del panel? Cambia el test que hoy fija el selector exacto (`test_el_parpadeo_vive_en_el_BANNER_y_no_en_el_texto`).
- *Animaciones* — ¿La pantalla /alarma-inmueble (ámbar, sirena del edificio) debe llevar también un halo bajo las cuatro condiciones de D-30, o se queda quieta a propósito?
- *Animaciones* — ¿Qué versión de Chromium lleva el kiosco del Pi y qué navegadores usará el cliente en la consola? Decide si @starting-style sirve para las entradas de modales y popovers o si hace falta desmontaje diferido en React.
- *Animaciones* — ¿Se acepta añadir expo-haptics? Exige recompilar el dev client o el build EAS antes de la presentación.
- *Animaciones* — El panel del gabinete declara 'dos keyframes y ninguna transición'. ¿Se permite ampliar ese inventario (barra de desarme de 5 s, punto de backfill) o se mantiene congelado para el Pi 4?
- *Funciones básicas* — Sesión de 30 días: la validez del refresh en Cognito es por app client. ¿Se crea un client táctico aparte de 30 días solo para brigadista e inspector, o se aceptan 30 días también para security_guard y building_admin, que hoy comparten el client de 24 h?
- *Funciones básicas* — El inspector usa también la consola web, donde le tocaría 1 día. ¿El mes aplica solo a su uso en la app, o se necesita un client web aparte para él?
- *Funciones básicas* — Consola web: ¿basta con subir el refresh a 24 h, o además se pasa de sessionStorage (por pestaña) a localStorage para que la sesión sobreviva al cerrar el navegador en el videowall del SOC?
- *Funciones básicas* — Alta de ocupantes: ¿autorregistro restringido al código o QR del edificio, o invitación masiva desde la consola por building_admin? Es una DECISIÓN que hoy no existe en DECISIONES-MAURICIO.md.
- *Funciones básicas* — ¿/etc/takab/cloud.env de la instancia trae TAKAB_API_COGNITO_USER_POOL_ID puesto a mano? Si no, la gestión de usuarios se verá SIMULADA delante del cliente (T-2.87).
- *Funciones básicas* — ¿Los clientes de la presentación usan iPhone? Sin build iOS ni APNs (T-2.97/T-2.98), la demo móvil solo es posible en Android.
- *Funciones básicas* — ¿Qué pide Protección Civil o el cliente en un reporte periódico (mensual, trimestral) y en qué formato? Decide el contenido del generador que falta.
- *Funciones básicas* — ¿Se cierran T-2.89, T-2.99 y T-3.09, que el repositorio ya da por hechas o consumadas, o se re-acreditan antes?
- *Funciones básicas* — ¿Hace falta multi-idioma (inglés) o SSO corporativo para algún prospecto concreto, o quedan fuera hasta que lo pidan (como T-3.15)?
- *Edge/nube/presentación* — ¿Se va a enseñar un simulacro ante el cliente? Si sí, ¿está command_enabled=true en gw-dev-0001? No se ve ni desde el repo ni desde el panel, y con el valor de fábrica el gabinete acusa 'rejected'.
- *Edge/nube/presentación* — ¿Qué release ejecuta hoy takab-gpio (el dueño de los pines) y desde cuándo? El registro del cerrojo solo guarda pid/unit. La respuesta decide si el 0,22 ms frente a 4,96 ms del reflejo se explica por el paso a D3.
- *Edge/nube/presentación* — ¿Están aplicados en el Pi 4 el watchdog de hardware (dtparam=watchdog=on, RuntimeWatchdogSec) y está habilitado systemd-time-wait-sync o chrony-wait? Lo segundo haría que takab-gpio esperase a NTP.
- *Edge/nube/presentación* — Política de sesiones pedida (30 días para brigadista, inspector y ocupante; 1 día para el resto): ¿se acepta separar app clients de Cognito o limitar por auth_time en la API, dado que el client táctico también lo usan building_admin y security_guard? ¿Y pasar la consola de sessionStorage a localStorage? Toca D-22.
- *Edge/nube/presentación* — El pool de ocupantes hoy da 90 días de refresh: ¿'1 mes' significa reducirlo a 30?
- *Edge/nube/presentación* — Catálogo SSN del panel (53 días): ¿se refresca días antes con POST /gateways/{id}/catalog o se narra como instantánea fechada?
- *Edge/nube/presentación* — ¿Los incidentes d5af54e5 y b420daaa ya los cerró el review_ttl de 6 h? Aun así hay que clasificarlos como reproduccion.
- *Edge/nube/presentación* — ¿El Pi 4 arranca de microSD o de NVMe? Cambia el coste del fsync por publicación en el hilo de SeedLink.
- *Edge/nube/presentación* — ¿Qué fecha tiene la presentación? Sirve para planificar el ensayo 2 y la ventana de despliegue (que no sea ese día) y para renovar la sesión del Pixel táctico en las 24 h previas.

## 10 · Verificación en ejecución (la rellenan las fases)

| Qué | Cómo | Resultado | Fecha |
|---|---|---|---|
| Recorrido web por rol, local | `web/e2e/recorrido_por_rol.spec.ts` | ✅ 10 roles · 268 controles · **0 inesperados** (ver §11). Occupant ❔ NO MEDIDO en local: sin pool de ocupantes, `/dev/token` responde 503 | 2026-09-23 |
| Recorrido web por rol, nube | el mismo con `PW_BASE_URL` | ❔ NO MEDIDO | — |
| Recorridos móviles en el Pixel | Maestro `recorrido-ocupante` / `recorrido-tactico` | ❔ NO MEDIDO | — |
| `auth_time` al refrescar en Cognito real | fragmento de DevTools | ❔ NO MEDIDO | — |
| Consola abierta más de 70 min sin logout | consola desplegada | ❔ NO MEDIDO en la nube. En local ✅: `web/e2e/sesion.spec.ts` 3/3 (token de 60 s y consola abierta 90 s ⇒ sigue dentro; aviso a 30 min del tope; tope ⇒ la entrada dice por qué) | 2026-09-23 |
| App 70 min sin pedir login | Pixel | ❔ NO MEDIDO | — |
| PDF: 10 variantes rasterizadas y revisadas | `auditoria/render-pdfs.sh` | ✅ sin solapes de texto (0 en las 10 variantes, medido con `cajas_de_texto.py`), clasificación en portada y ejecutivo, hora local, FIRMÓ con rol y nombre, sin inglés crudo. Revisado a ojo por el verificador y por el integrador. Pendiente: el informe de un incidente REAL de la nube con fotos y onda (ensayo 2) | 2026-09-23 |

## 11 · El recorrido de la consola, rol por rol (navegador de verdad)

`web/e2e/recorrido_por_rol.spec.ts` contra `make soc-local`, el 2026-09-23 (volcado íntegro en
[`auditoria/recorrido-web.json`](auditoria/recorrido-web.json)). Para cada rol: las rutas que el
servidor le concede, y en cada una cada botón, desplegable, pestaña y menú **no mutante** pulsado.
Cuenta como fallo toda respuesta HTTP ≥ 400, todo error de página y todo control que no haga nada.
Los controles **mutantes** (acusar, firmar, ejecutar, borrar…) no se pulsan aquí; los ejercen las specs
de flujo.

| Rol | Rutas | Con efecto | Deshabilitados con causa | Mutantes (no pulsados) | Re-renderizados | Resultado |
|---|---|---|---|---|---|---|
| `brigadista` | 1 | 0 | 0 | 0 | 0 | ✅ |
| `building_admin` | 3 | 24 | 3 | 1 | 0 | ✅ |
| `gov_operator` | 5 | 27 | 5 | 1 | 0 | ✅ |
| `inspector` | 3 | 24 | 3 | 0 | 0 | ✅ |
| `occupant` | 1 | 0 | 0 | 0 | 0 | ❔ NO MEDIDO (entorno) |
| `security_guard` | 1 | 0 | 0 | 0 | 0 | ✅ |
| `soc_operator` | 4 | 26 | 4 | 0 | 0 | ✅ |
| `takab_superadmin` | 6 | 37 | 9 | 8 | 3 | ✅ |
| `takab_support` | 6 | 30 | 11 | 1 | 0 | ✅ |
| `tenant_admin` | 6 | 33 | 7 | 8 | 3 | ✅ |

**Lo que encontró el recorrido y ningún test veía:** gov_operator, inspector y building_admin
pedían `GET /maintenance-windows` en CADA página y recibían 403. La pantalla lo toleraba, pero cada
petición estaba condenada de antemano. La consola aplica ya la regla del servidor antes de pedir
(`useMaintenanceWindows.ts::puedeLeerVentanas` ↔ `routers/maintenance.py::READ_ROLES`, ancladas
una contra la otra).

**Lo que el recorrido tuvo que aprender de sí mismo:**

- `locator.evaluate()` sobre un elemento que ya no existe espera hasta el timeout del test. El
  superadmin se quedó 25 minutos detrás de «ACEPTO ESTE AVISO», que desaparece al pulsarlo.
- Enumerar los controles de uno en uno (cuatro viajes al navegador por elemento) no cabía en
  `/fleet`, con 21 gabinetes.
- El `title` de un botón deshabilitado vive en su envoltorio: la consola lo pone ahí porque un
  botón deshabilitado no recibe eventos.

Una corrida larga contra el servidor de desarrollo de Vite llegó a agotar los recursos del navegador
(`ERR_INSUFFICIENT_RESOURCES`); repetido solo, el rol salió limpio.
