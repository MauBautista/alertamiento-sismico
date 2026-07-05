# USER-STORIES.md — Historias de usuario TAKAB (Fase 1 MVP)

> Formato: **Como** [rol] · **quiero** [acción] · **para** [valor]. Cada historia lista sus
> criterios de aceptación. Roles definidos en `RBAC-TAKAB.md`. No se implementa T-MINUS ni
> magnitud preliminar en MVP (ver pendientes RBAC §8).

---

## Épica 1 · Operación del SOC (web)

### US-01 · Vista global de sitios
**Como** `soc_operator` **quiero** ver un mapa con todos mis sitios y su estado (verde/ámbar/rojo)
**para** detectar de un vistazo dónde hay un evento activo.
- El mapa carga sitios del tenant con su severidad actual.
- Un evento activo resalta el sitio (anillos/color) en <2 s desde el edge.
- Estados loading/error/empty/stale visibles; un dato >30 s viejo se marca como "stale".

### US-02 · Cola de incidentes en vivo
**Como** `soc_operator` **quiero** una tabla de incidentes abiertos con severidad, sitio, PGA y edad
**para** priorizar mi atención.
- La tabla se actualiza por WebSocket sin recargar.
- Puedo acusar (`ack`) un incidente y el cambio se refleja en el SOC y en la app del brigadista.

### US-03 · Detalle de sitio con sismograma
**Como** `soc_operator` **quiero** abrir el detalle de un sitio y ver el waveform y métricas
**para** evaluar qué está pasando.
- El waveform histórico carga una ventana de 10 min en <1 s.
- Aparece un pop-up automático del waveform cuando una estación registra anomalía
  (STA/LTA > 3.5 sostenido 2 s).

### US-04 · Acuse sin control ajeno (gobierno)
**Como** `gov_operator` (Protección Civil) **quiero** ver y acusar incidentes de sitios `gov_shared`
**para** coordinar respuesta, **sin** poder accionar sirenas de inmuebles ajenos.
- Veo solo tenants con `visibility = gov_shared`.
- No tengo botones de silenciar/probar/activar actuadores en sitios de terceros.

---

## Épica 2 · Gabinete y flota (edge + web)

### US-05 · Protección local autónoma
**Como** ocupante de un edificio **quiero** que la sirena suene cuando llega la alerta SASMEX
**aunque** no haya internet **para** tener tiempo de resguardarme.
- Cierre del contacto #2 del WR-1 → sirena en <100 ms.
- Funciona con el Pi apagado (ruta de hardware paralela).
- Funciona sin nube.

### US-06 · Salud de la flota
**Como** `takab_support` **quiero** ver el estado de cada gabinete (MQTT, SeedLink lag, batería,
actuadores) **para** mantener la red operativa.
- La página Flota Edge refleja `device_health` ([ANALISIS-00]: la tabla `device_health_10s`
  se renombró — el muestreo por intervalo de 10 s violaba P5; ahora es por transición + heartbeat).
- Un gabinete offline >5 min se marca y alerta a operaciones (observabilidad de flota,
  Fase 2 del roadmap — numeración "2.8" de FASE-0, hoy en `archive/`).

### US-07 · Prueba de sirena con auditoría
**Como** `building_admin` **quiero** ejecutar una prueba de sirena en mi edificio
**para** verificar que funciona, **dejando** registro.
- Puedo lanzar la prueba desde web/móvil.
- Queda en `audit_log` con mi ID y timestamp.

---

## Épica 3 · App móvil del ocupante

### US-08 · Estado tranquilizador en reposo
**Como** `occupant` **quiero** ver "Edificio SEGURO" y mis rutas de evacuación
**para** sentirme informado en el día a día.
- Banner verde con nombre del edificio.
- Directorio de emergencia y mapa de evacuación accesibles.

### US-09 · Pantalla de crisis por piso
**Como** `occupant` **quiero** una instrucción gigante y clara al recibir alerta
**para** saber exactamente qué hacer según mi piso.
- Push de alta prioridad que rompe silencio/No-Molestar.
- Texto "EVACÚE AHORA" o "REPLIÉGUESE" según `zone_id` del usuario.
- En MVP: "ALERTA SÍSMICA · PROTÉJASE" (sin cuenta regresiva ni magnitud).

### US-10 · Check-in de vida post-sismo
**Como** `occupant` **quiero** reportar "Estoy a salvo" o "Necesito ayuda"
**para** que brigadistas y SOC sepan mi estado.
- Botón verde/rojo tras el movimiento.
- "Necesito ayuda" envía última ubicación/piso al SOC y brigadistas.
- Veo el bloqueo "Reingreso Prohibido" hasta que se firme el dictamen.

### US-11 · Activación manual con quórum (ocupante)
**Como** `occupant` **quiero** poder activar la sirena ante una emergencia no sísmica (incendio)
**pero** con control para evitar pánico injustificado.
- Requiere 2 ocupantes activando en el mismo sitio dentro de 30 s.
- Queda en `audit_log` con ambos IDs.

---

## Épica 4 · Brigadista y seguridad (app móvil)

### US-12 · Dashboard táctico del gabinete
**Como** `brigadista` **quiero** ver salud del gabinete y estado de actuadores
**para** confirmar que las acciones automáticas se ejecutaron.
- Checklist: sirena/gas/puertas con su estado real.
- Batería UPS, MQTT, sensor RS4D visibles.

### US-13 · Silenciar sirena desde LTE
**Como** `brigadista` **quiero** silenciar la sirena local desde mi celular aunque esté en datos
móviles **para** detener el pánico acústico tras evacuar.
- La app intenta LAN; si no, va por nube (app → IoT Core → gateway).
- Comando firmado + MFA + ack de ejecución.
- (Limitación documentada: no silencia el pulso breve inicial de la rama de hardware.)

### US-14 · Activación individual (brigadista+)
**Como** `brigadista`/`security_guard` **quiero** activar la sirena con deslizar-para-activar
**para** responder rápido a una emergencia, sin segundo confirmante.

### US-15 · Cámara forense y triage
**Como** `brigadista` **quiero** fotografiar daños con marca de agua inalterable
(hora, GPS, PGA, mi ID) **para** alimentar el triage estructural.
- Formulario de daños (estructural / no estructural / fuga).
- Sincronización offline-first: si no hay red, guarda local y sube al recuperar señal.

### US-16 · Headcount / pase de lista
**Como** `brigadista` **quiero** filtrar "no reportados" de mi piso con sus teléfonos
**para** localizar a quien no hizo check-in.

### US-17 · Recepción de dictamen de reingreso
**Como** `brigadista` **quiero** recibir el certificado PDF cuando el inspector firma el dictamen
**para** dar la indicación oficial de reingreso.

---

## Épica 5 · Inspector / dictamen

### US-18 · Firma de dictamen
**Como** `inspector` **quiero** revisar evidencias y firmar un dictamen semaforizado
**para** autorizar o restringir el reingreso con trazabilidad.
- El dictamen queda con mi firma, versión de reglas y evidencias en `dictamens`.
- Al firmar, se notifica a brigadistas y ocupantes (estos solo el aviso de reingreso).

---

## Épica 6 · Registro y administración

### US-19 · Auto-registro de ocupantes
**Como** `occupant` **quiero** registrarme escaneando un QR/PIN del edificio
**para** entrar sin que un admin me cargue a mano.
- El código asigna tenant + site + zona automáticamente (`site_enrollment_codes`).
- Quedo en el grupo Cognito `occupant`.

### US-20 · Alta de sitios y umbrales
**Como** `tenant_admin` **quiero** dar de alta sitios y configurar umbrales por tipología
**para** adaptar el sistema a mis edificios.
- Cambios de umbral se sincronizan al edge firmados (T-1.23/T-1.30; la "fase 2.2" era
  numeración de FASE-0, hoy en `archive/`).
