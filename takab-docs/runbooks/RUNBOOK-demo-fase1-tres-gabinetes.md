# RUNBOOK · Hito de salida Fase 1 — demo en vivo con 3 gabinetes

> **Estado: RE-ACREDITADO (2026-07-11).** `make demo-fase1` = **35/35 asserts en verde, en 3
> corridas consecutivas**. (Acreditación original 2026-07-08; su "36/36" fue un error de
> transcripción — el harness imprime 35 y sus asserts no han cambiado desde entonces.)
> Confirmación en hardware real (Pi 5 `gw-dev-0001`): corte de WAN reversible, protección
> local intacta, cero pérdida al reconectar.
>
> **Guardia de exclusividad (lección A-3 de la auditoría de cierre):** la acreditación exige
> la DB local SIN otros clientes. Un worker residente — p.ej. el `python -m takab_api.incident`
> que deja vivo un `make soc-local` mal apagado (no escucha en ningún puerto que lo delate) —
> correlaciona y dispara fail-open por su cuenta ANTES de que C2 consulte ⇒ **33 OK · 2 FALLOS
> falsos** que parecen regresión del pipeline. Desde 2026-07-11 la demo revisa
> `pg_stat_activity` con su PRIMERA conexión y ABORTA ruidosa si hay cualquier otro
> `client backend` (`demo/run.py::_assert_exclusive_db`, tests en
> `demo/tests/test_reset_guard.py`).

El hito (TASKS.md) pide: *"Demo en vivo con 3 gabinetes: prueba SASMEX dispara actuadores y
aparece en el SOC; sismo simulado en 3 estaciones activa quórum; corte de internet no detiene
la protección local."*

---

## Qué es real y qué se sustituye

La demo levanta software de **producción** en todos los tramos salvo uno:

- **3 gabinetes** = 3 `EdgeSupervisor` reales, un proceso cada uno (`demo/gabinete.py`). La
  ruta de protección —`gpio` (reflejo SASMEX in-process), `rules` (decisión de tier),
  `actuators`— arranca como módulos críticos fail-fast, igual que bajo systemd en el Pi.
- **Ingesta** = el `SqsConsumer` REAL (`demo/bridge.py`): mismo despacho por topic, misma
  validación contra `shared/schemas/`, misma resolución de identidad por `meta_principal`,
  mismos handlers, misma DLQ.
- **Quórum** = el `IncidentEngine` REAL (`python -m takab_api.incident`).
- **SOC** = el mismo `NOTIFY takab_live` que alimenta al hub WebSocket de la consola.

**Único tramo sustituido: IoT Core + SQS** (`demo/spool.py`). En vez de mTLS a AWS, cada
gabinete escribe un archivo por mensaje, enriquecido igual que la IoT Rule
(`meta_principal`/`meta_topic`/`meta_ts_iot`), y el consumer los lee. `go_offline()` modela
la caída de WAN idéntico al `FakeMqttTransport` de los tests. El sustituto tiene sus propias
propiedades de SQS (visibility timeout, redrive a DLQ) porque el consumer real depende de
ellas; ver `demo/tests/test_spool.py`.

### Lo que la demo NO acredita (honestidad)

**Gate #3 sigue abierto**: no hay WR-1, ni relés de potencia, ni sirena, ni válvula de gas
cableados. La actuación es sobre **relés mock** (`gpiozero.MockFactory`). La latencia medida
del reflejo (~0.04 ms) es la de la **ruta software**; el presupuesto físico <100 ms (debounce
50 ms + interrupción + relé) se valida con hardware y esta demo **no** lo mide. El riesgo de
disparar un actuador real (válvula de gas) es nulo hoy: no hay nada físicamente cableado.

---

## Ejecutar (un comando)

```bash
make demo-fase1
```

Esto: levanta la DB (docker), aplica migraciones + siembra la flota, y corre `demo/run.py`,
que orquesta los 3 criterios y **falla ruidosamente** si alguno cae. Requisitos: Docker,
`uv`, y el venv del edge (`cd edge && uv sync`).

Gotcha clave: alembic lee la env **BARE** `DATABASE_URL`, mientras la API y los workers leen
`TAKAB_API_DATABASE_URL`. El target `demo-db` ya usa la correcta; confundirlas es el error
clásico.

Flags: `demo/run.py --keep` conserva `/tmp/takab-demo-fase1` (spools, DLQ, workdirs) para
inspección.

---

## Evidencia por criterio (lo que imprime, y por qué)

### C1 · SASMEX → actuadores → SOC
- Reflejo SASMEX→sirena in-process **<0.05 s** (software) — `gpio.last_reflex_latency_s`.
- **5/5 relés** activados (sirena, estrobo, gas, ascensor, puerta) — la secuencia de
  `evacuate_or_hold`.
- El incidente llega al SOC (`NOTIFY takab_live`) en **<2 s** desde el publish (criterio T-1.22).
- Incidente `trigger='sasmex'`, `severity=critical`, atribuido al sitio del gabinete.
- Los ACK de actuador (`siren_on`, `gas_closed`) quedan como evidencia inmutable en
  `incident_actions`. Cola vacía, DLQ en 0.

### C2 · Quórum en 3 estaciones
- Los 3 gabinetes sienten el mismo sismo instrumental → **1 incidente por sitio**, sin
  corroborar (`event_id IS NULL`), en 3 sitios distintos (Puebla ×2 + CDMX, ~100 km).
- El motor real crea **1 `seismic_events` `source='local_quorum'`** con `meta.node_count ≥ 3`.
- **3 `quorum_votes`** con offsets por nodo (ancla `delta_s=0`); los 3 incidentes quedan
  linkeados al evento de red.
- **Fail-open (T-1.19)**: al formarse el evento, los sitios en rango sin heartbeat fresco
  abren un incidente sintético `trigger='quorum'`, `severity=warning`. Es correcto: se prefiere
  sobre-notificar a callar.

### C3 · Corte de internet no detiene la protección local
- WAN caída → la actuación local ocurre igual (**5/5 relés**, sirena suena sin nube).
- El contador `sent` del gabinete **no avanza** durante el corte; la cola durable **crece**.
- Ningún mensaje del gabinete llega a la DB mientras está offline.
- Al reconectar, la cola durable **drena**, se ingiere todo, y **cero duplicados**
  (idempotencia por `event_uuid` + `ON CONFLICT DO NOTHING`); el incidente detectado offline
  aparece ahora en el SOC. DLQ en 0.

---

## Confirmación en hardware real (Pi 5 `gw-dev-0001`)

El criterio C3 se confirmó además sobre el gabinete real (Pi 5 + Shake RS4D), sin pararlo ni
tocar la actuación. Es reversible y deja el Pi intacto.

```bash
# En el Pi (ssh takab-pi5), como root vía sudo -n. nft disponible; iptables no.
# 1) Watchdog de seguridad: revierte el corte pase lo que pase, aunque se pierda el ssh.
sudo nohup bash -c 'sleep 120; nft delete table inet takab_demo 2>/dev/null' &
# 2) Corte QUIRÚRGICO: sólo egress a tcp/8883 (MQTT a IoT Core). ssh/LAN intactos.
sudo nft add table inet takab_demo
sudo nft add chain inet takab_demo out '{ type filter hook output priority 0; policy accept; }'
sudo nft add rule inet takab_demo out tcp dport 8883 drop
# 3) Observar: el servicio sigue active; el edge loguea "fallo al publicar; se reintentará";
#    /var/lib/takab/spool crece.  4) Revertir: sudo nft delete table inet takab_demo
```

**Resultado medido (2026-07-08):** `takab-edge.service` `active` durante todo el corte; el
spool durable `/var/lib/takab/spool` creció de 0 a **93 archivos**; al restaurar drenó a **0**
y la conexión `:8883` se restableció. El socket TCP a IoT Core figura `ESTABLISHED` unos
segundos tras el corte (descartar paquetes no lo tumba al instante: lo mata el timeout del
keepalive MQTT); la prueba real del corte es que las publicaciones fallan y se encolan.

Nota de limpieza: `pgrep -f "…takab_demo"` cuenta también el propio shell ssh que lleva ese
texto en su línea de comando — usar `pgrep -x sleep` para contar el watchdog de verdad.

---

## Arquitectura de la demo (archivos)

```
demo/
├── spool.py       SpoolMqttTransport (≡ IoT Core) + SpoolSqsClient (≡ SQS). Solo stdlib.
├── gabinete.py    Un EdgeSupervisor real + API de control (SASMEX/quake/WAN) por proceso.
├── bridge.py      El SqsConsumer REAL sobre el spool (SET ROLE takab_ingest, BYPASSRLS).
├── run.py         Orquestador de los 3 criterios con asserts; falla ruidosamente.
└── tests/test_spool.py   Contratos del sustituto de IoT Core+SQS (meta_*, orden, visibility, redrive).
```
