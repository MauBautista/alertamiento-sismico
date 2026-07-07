# RUNBOOK · Load test de ingesta (T-1.17 · G1)

**Criterio:** 20 sitios × 4 canales × 1 msg/s (= 80 msg/s) sostenido sin lag de cola;
idempotente por PK; validación contra `shared/schemas/` con rechazo a DLQ.

## Topología medida

```
fleet.py --mode sqs ──▶ takab-dev-q-telemetry ──▶ takab-worker-telemetry (docker, CO-LOCADO
   (laptop dev)              (SQS standard)          en el EC2 de la DB) ──▶ Timescale local
aws iot-data / --mode iot ─▶ broker IoT ─▶ reglas ─▶ q-events ─▶ takab-worker-events (ídem)
```

- Workers = imagen `takab-cloud:t117` (`api/Dockerfile`, build en el EC2 desde tarball S3
  `s3://takab-dev-transfer-.../build/t117-ctx.tgz`; pip editable para conservar el layout
  del repo que resuelve `shared/schemas/`). Credenciales AWS por rol IAM de la instancia
  (statements `WorkerQueues`/`EcrAuth`/`EcrPull`/`WorkerTransferRead` — plan §C.1: workers
  co-locados son el default dev). DSN de `takab_ingest` desde Secrets Manager en el host.
- Simulador: `edge/simulators/fleet.py` (SIM001..SIM020, 5 estaciones por gateway
  `gw-sim-0001..4`), enriquecimiento idéntico a la IoT Rule (`meta_principal/meta_topic/
  meta_ts_iot`), payloads validados contra el schema antes de enviar.

## Cómo reproducir

```bash
# 1. Túnel (solo para observar la DB; los workers NO lo usan): make db-tunnel  → :5434
# 2. Workers co-locados (una vez): ver sección Topología (docker build + docker run vía SSM).
# 3. Carga:
AWS_PROFILE=takab-dev uv run --directory edge python simulators/fleet.py \
  --mode sqs --queue-url "$(terraform -chdir=infra/terraform/envs/dev output -json queue_urls | jq -r .telemetry)" \
  --rate 1.0 --sites 20 --duration-s 600 --with-health --region us-east-2
# 4. Observar: aws sqs get-queue-attributes ... ApproximateNumberOfMessages (cada 20 s)
# 5. ⚠️ AL TERMINAR: detener el simulador SIEMPRE (no dejarlo corriendo: ≈$0.3–0.5/h).
```

## Resultados (2026-07-06)

### Corrida A — workers vía túnel SSM desde laptop (NO válida para G1, diagnóstica)

- Simulador: 48,080 msgs @ 80.2 msg/s sostenidos, 0 errores, 599.7 s.
- 1 consumer no alcanza (~30–40 msg/s efectivos): backlog creció hasta ~30k.
  4 consumers ≈ 70 msg/s — aún < entrada. **Cuello = RTT del túnel SSM por batch**, no el
  diseño: el despliegue objetivo es co-locado (§C.1). La escalada horizontal funcionó sin
  duplicados (idempotencia por PK) — evidencia útil, medición no representativa.

### Corrida B — workers co-locados en el EC2 (CALIFICADA para G1)

- Simulador: **48,080 msgs @ 80.2 msg/s sostenidos, 0 errores, 599.6 s** (48,000 features
  + 80 health heartbeats).
- Profundidad q-telemetry (muestreo cada 20 s, 26 muestras): **máx 21 mensajes**
  (≈0.25 s de entrada, picos momentáneos), serie ≈0 constante → **sin lag sostenido**.
- DLQs (telemetry y events): **0 mensajes** durante toda la corrida.
- Filas: `waveform_features_1s` **+48,000 exactas** (cero pérdida); duplicados por
  `(ts,sensor_id,channel)`: **0**. `device_health` +80 heartbeats.
- Identidad (en vivo): publish vía `aws iot-data` con principal fuera de la flota →
  events-DLQ con `reason: unknown principal` (attrs `original_topic=takab/events`).

### Smoke mTLS real (broker → regla → SQS → DB)

- `fleet.py --mode iot`: 4 conexiones mTLS reales (certs por gateway de Secrets Manager,
  `client_id = thing name`), 1,202 msgs, 0 errores.
- `--quake SIM016`: LocalEvent `watch` → `evacuate_or_hold` con el MISMO `event_id` por el
  broker real → `q-events` → worker → **UN solo incidente** en `incidents` con
  `severity=critical` (UPSERT al tier mayor verificado E2E, sin duplicados).
- Seguridad verificada de facto: publicar por `aws iot-data publish` (principal ≠ thing de
  la flota) produce REJECT `unknown principal` → DLQ — la identidad sale del certificado,
  no del payload.

## Notas operativas

- Los workers co-locados sobreviven reinicios (`--restart unless-stopped`).
- Purga de colas para corridas limpias: `aws sqs purge-queue` (1/60 s por cola).
- Con carga sostenida real (>8 sitios), separar los workers a Fargate es el toggle previsto
  en Terraform (plan §C.1); a 4–8 sitios el co-locado sobra.
