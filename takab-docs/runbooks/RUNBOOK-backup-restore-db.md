# RUNBOOK · Backup y restore de la DB (Timescale en EC2) — hallazgo A-5

> **Estado: PROCEDIMIENTOS DOCUMENTADOS (2026-07-11) · RESTORE JAMÁS PROBADO (gate G-09).**
> **Criterio:** existe procedimiento ejecutable de restauración para AMBOS mecanismos de
> respaldo, con RPO/RTO declarados; el gate se cierra ejecutando una restauración REAL,
> midiendo el RTO y llenando el registro §6. Hasta entonces, el respaldo es una hipótesis.

La DB es Postgres 16 + TimescaleDB **autogestionada en EC2** (contenedor
`timescale/timescaledb-ha:pg16`; RDS no soporta la extensión —
`modules/database/main.tf:166-167`). El dato vive en un volumen EBS dedicado gp3 40 GiB
(`main.tf:178-187`) adjunto como `/dev/xvdf`.

---

## 1. Qué existe HOY (dos mecanismos, ninguno probado)

| Mecanismo | Cuándo | Qué captura | Retención | Dónde |
|---|---|---|---|---|
| **Snapshot EBS (DLM)** | Diario 03:00 UTC | Instancia completa (root + volumen de datos), crash-consistent | 7 snapshots (7 días) | EBS snapshots, tag `DlmBackup=true` (`modules/database/main.tf:268-292`) |
| **Dump lógico (`pg_dump -Fc`)** | Diario 08:00 UTC (cron en la instancia) | La base `takab` completa, consistente (MVCC) | 60 días (lifecycle S3 `expira-60d`, `modules/storage/main.tf:129-144`) | `s3://takab-dev-db-backups-<ACCT>/takab-YYYY-MM-DD.dump`, cifrado KMS (`modules/database/user_data.sh.tpl:103-104`) |

Notas honestas:
- El cron del dump corre DENTRO de la instancia: si la instancia muere a las 07:59, el último
  dump es de ayer. Los dumps ya subidos y los snapshots sobreviven a la instancia.
- El snapshot EBS en caliente es **crash-consistent**: Postgres arranca y se recupera con su
  propio WAL, como tras un corte de luz. Aceptable; documentado.
- No hay archivado de WAL (PITR): entre puntos de respaldo la pérdida es total (§7).
- Las tablas de compliance (`audit_log`, `evidence_objects`, `dictamens`…) jamás se podan en
  la DB viva (regla de oro 11); la expiración de 60 días aplica SOLO a los archivos de dump.

## 2. RPO / RTO

- **RPO actual (capacidad medible): ≤ 24 h.** Dos puntos por día (03:00 snapshot físico,
  08:00 dump lógico); peor caso = desastre a las 02:59 → se pierde desde las 08:00 del día
  anterior (~19 h); el peor caso teórico entre puntos es < 24 h.
- **RTO actual: NO MEDIDO.** Estimaciones a validar en G-09: restore lógico 15–45 min;
  restore físico por snapshot 30–60 min (manual, un operador).
- **Objetivos PROPUESTOS (a ratificar por Mauricio antes del primer cliente):**
  RPO ≤ 15 min (exige PITR, §7) · RTO ≤ 60 min con runbook ensayado.

## 3. Procedimiento A — Restore LÓGICO desde dump (corrupción lógica, borrado accidental)

Restaura a una base LATERAL primero; el swap es el último paso y es reversible.

```bash
ACCT=634882473845
# 1. Elegir el dump (el más reciente, o el anterior al incidente):
AWS_PROFILE=takab-dev aws s3 ls s3://takab-dev-db-backups-$ACCT/ | sort | tail -5
AWS_PROFILE=takab-dev aws s3 cp s3://takab-dev-db-backups-$ACCT/takab-YYYY-MM-DD.dump /tmp/

# 2. Subirlo a la instancia (SSM; SIN ssh público) y restaurar a base lateral:
#    (o correr 1-3 directamente en la instancia vía aws ssm start-session)
docker exec -i takab-db psql -U postgres -c "DROP DATABASE IF EXISTS takab_restore;" \
  -c "CREATE DATABASE takab_restore;"
docker exec -i takab-db pg_restore -U postgres -d takab_restore --no-owner < /tmp/takab-YYYY-MM-DD.dump

# 3. VERIFICAR contra el checklist §5 en takab_restore (no en takab).

# 4. Swap (VENTANA: parar API/workers primero — docker compose stop en la instancia):
docker exec -i takab-db psql -U postgres \
  -c "ALTER DATABASE takab RENAME TO takab_pre_restore;" \
  -c "ALTER DATABASE takab_restore RENAME TO takab;"
# rollback = invertir los dos RENAME. Al terminar: docker compose start.
```

## 4. Procedimiento B — Restore FÍSICO desde snapshot (pérdida de instancia/volumen)

```bash
# 1. Snapshot más reciente del volumen de DATOS (tag copiado por DLM):
AWS_PROFILE=takab-dev aws ec2 describe-snapshots --owner-ids self \
  --filters Name=tag:DlmBackup,Values=true \
  --query 'sort_by(Snapshots,&StartTime)[-3:].[SnapshotId,StartTime,VolumeId,Description]' --output table

# 2. Crear volumen en la MISMA AZ de la instancia destino:
aws ec2 create-volume --snapshot-id snap-XXXX --availability-zone us-east-2a --volume-type gp3

# 3. Parar la instancia (o usar una de recuperación), detach del volumen dañado,
#    attach del nuevo como /dev/xvdf, arrancar. El user_data ya monta /dev/xvdf y
#    levanta compose (ver modules/database/user_data.sh.tpl). Si se restaura la
#    instancia COMPLETA: lanzar desde el snapshot de root + attach de datos, y
#    re-asociar la EIP del módulo serve.

# 4. Postgres se auto-recupera (crash-consistent) al arrancar takab-db.
# 5. VERIFICAR (§5) y MEDIR el RTO real (§6).
```

## 5. Checklist de verificación de integridad (tras CUALQUIER restore)

```sql
-- La punta del dato: ¿hasta cuándo hay telemetría?
SELECT max(ts) FROM waveform_features_1s;
-- Volumen de negocio (comparar contra lo esperado):
SELECT count(*) FROM incidents; SELECT count(*) FROM audit_log; SELECT count(*) FROM evidence_objects;
-- Compliance intacta: el trigger append-only sigue (debe FALLAR):
UPDATE audit_log SET verb='x' WHERE false; -- y un UPDATE real de 1 fila debe rechazarse
-- Timescale sano:
SELECT extversion FROM pg_extension WHERE extname='timescaledb';
SELECT count(*) FROM timescaledb_information.hypertables;
-- RLS viva:
SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname IN ('incidents','audit_log');
```

## 6. Registro de verificación (G-09 — llenar al ejecutar; SIN marcar hasta entonces)

| # | Prueba | Esperado | Medido | OK/NO | Fecha/inicial |
|---|---|---|---|---|---|
| R-1 | Restore lógico (Proc. A) a `takab_restore` | checklist §5 verde |  |  |  |
| R-2 | Swap + rollback del swap | app funciona en ambos sentidos |  |  |  |
| R-3 | Restore físico (Proc. B) en volumen/instancia limpia | Postgres arranca y §5 verde |  |  |  |
| R-4 | RTO medido (A y B) | ≤ 60 min |  |  |  |
| R-5 | RPO verificado (`max(ts)` vs hora del "desastre") | ≤ 24 h |  |  |  |

## 7. Plan PITR (tarea futura — cierra la brecha de RPO)

Archivado continuo de WAL con **WAL-G** al bucket de backups (ya existe bucket + IAM de
escritura acotada — `modules/database/main.tf:98`): RPO ≤ 15 min y restauración a un punto
en el tiempo (deshacer un DELETE de hace 10 minutos, no solo "volver a ayer"). Piezas:
contenedor/sidecar wal-g o `archive_command` en el compose de la DB, `wal-g backup-push`
base semanal, prueba de `wal-g backup-fetch` + `recovery_target_time`, y alarma si el
archivado se atasca (extensión natural del módulo `observability` de A-4). Dimensionar
costo S3 (WAL ~MB/h a esta escala: centavos).

## 8. Relación con el resto del sistema

- Los objetos de EVIDENCIA (miniSEED, PDFs) viven en S3 (`evidence`), fuera de esta DB y de
  este runbook; su durabilidad es la de S3. Este runbook cubre la base relacional.
- El spool del edge re-entrega lo no confirmado al reconectar (idempotencia por
  `event_uuid`): tras un restore, el gabinete rellena el hueco de SUS eventos aunque la nube
  haya perdido horas — otra razón por la que el RPO de 24 h no pierde eventos del camino de
  vida, solo telemetría agregada y estado de consola.
