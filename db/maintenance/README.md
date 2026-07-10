# db/maintenance — operaciones manuales sobre la DB desplegada

Scripts de mantenimiento que **NO son migraciones**: se ejecutan a mano, una vez,
contra el entorno desplegado, con runbook y respaldo. Las migraciones de esquema
viven en `api/migrations/`; los seeds en `db/seeds/`.

---

## 2026-07-10 · Purga pre-producción (T-1.47)

**Decisión (Mauricio, 2026-07-10):** el sistema sale de fase de pruebas. Se
eliminan del entorno desplegado la flota SIM completa y TODOS los incidentes
existentes (5 pruebas del botón WR-1 de la madrugada del 2026-07-10 + 1 de sitio
sim del 07-jul). El historial de producción arranca en cero: el primer incidente
real será del radio WR-1 o de un sismo real.

**Excepción deliberada a la regla de oro 11** ("evidencia/audit no se poda"):
aplica a DATOS de prueba/sim, no a la bitácora — `audit_log` se conserva íntegro
y la purga misma queda registrada dentro (`verb='purge'`). El respaldo `pg_dump`
+ el CSV de llaves S3 preservan lo borrado de forma recuperable.

**Script:** [`2026-07-10_purge_sim_fleet_and_test_incidents.sql`](2026-07-10_purge_sim_fleet_and_test_incidents.sql)
— transacción única como superusuario, `session_replication_role=replica`
(cubre los triggers append-only copiados a los chunks de hypertables y evita la
tormenta NOTIFY), guardia anti-flota-real, verificación y checks de orfandad
embebidos. Idempotente (re-ejecutar borra 0 filas).

### Precondición dura

El **split de seeds ya debe estar desplegado** (deploy que embebe
`db/seeds/prod_fleet.sql`): `deploy/cloud/deploy.sh` re-siembra en CADA deploy y
con el seed viejo (`dev_fleet.sql`, pre T-1.47) los 20 sitios sim resucitarían.

### Runbook (EC2 co-locado, cuenta takab-dev us-east-2)

1. **Sesión** al EC2:
   `AWS_PROFILE=takab-dev aws ssm start-session --region us-east-2 --target <EC2_INSTANCE_ID>`
2. **Pausar escritores** (la DB y el broker siguen arriba; el Pi acumula en
   SQS/spool sin pérdida — verifica los nombres con `docker compose ps`):
   `cd /opt/takab/cloud && docker compose --env-file /etc/takab/deploy.env stop <workers de ingest/engine/notify/sync>`
3. **Verificar superusuario** (por socket local del contenedor, auth trust):
   `docker exec -i takab-db psql -U postgres -d takab -c "SELECT rolsuper FROM pg_roles WHERE rolname = current_user;"` → `t`
4. **Respaldo OBLIGATORIO** y copia fuera del EC2:
   ```sh
   mkdir -p /opt/takab/backups
   docker exec -i takab-db pg_dump -U postgres -Fc takab \
     > /opt/takab/backups/takab-prepurga-$(date +%Y%m%d-%H%M).dump
   pg_restore -l /opt/takab/backups/takab-prepurga-*.dump | head   # lista objetos ⇒ dump sano
   aws s3 cp /opt/takab/backups/takab-prepurga-*.dump s3://<BUCKET_EVIDENCIA>/backups/
   ```
5. **Exportar llaves S3 de evidencia** (los objetos no se tocan hoy):
   ```sh
   docker exec -i takab-db psql -U postgres -d takab -c \
     "\copy (SELECT s3_key, kind, incident_id FROM evidence_objects) TO STDOUT CSV HEADER" \
     > evidencia-s3-prepurga.csv
   aws s3 cp evidencia-s3-prepurga.csv s3://<BUCKET_EVIDENCIA>/backups/
   ```
6. **Editar y ejecutar el script** (rellena `<SUB_DE_MAURICIO>` y
   `<NOMBRE_DEL_DUMP>` en el INSERT de audit; UNA sola ejecución):
   ```sh
   docker exec -i takab-db psql -U postgres -d takab -v ON_ERROR_STOP=1 \
     < db/maintenance/2026-07-10_purge_sim_fleet_and_test_incidents.sql
   ```
   Revisa la tabla de conteos y los checks de orfandad que imprime al final:
   `sites=1, gateways=1, sensors=1`, familia de incidentes en 0, `dh_real`/
   `wf_real` > 0, huérfanos todos en 0. Cualquier discrepancia ⇒ restaurar del
   dump (`pg_restore -d takab --clean --if-exists <dump>`).
   *Nota:* el alcance de la purga es SOLO la convención sim + incidentes; si los
   conteos de flota salen mayores a 1, hay sitios/gateways creados a mano
   (`SELECT code FROM sites ORDER BY code;`) — se evalúan aparte, el script no
   los toca (verificado en el ensayo local del 2026-07-10, donde fixtures de
   tests quedaron intactos y el re-run dio 21×`DELETE 0`).
7. **Re-sembrar lo real** (idempotente; crea además el rule_set v1):
   `docker exec -i takab-db psql -U postgres -d takab -v ON_ERROR_STOP=1 < /opt/takab/cloud/prod_fleet.sql`
8. **Rearrancar**: `docker compose --env-file /etc/takab/deploy.env up -d` (o
   `systemctl restart takab-cloud.service`).
9. **Smoke** en `https://<console_public_host>`: Consola sin incidentes y con
   solo "Sitio Dev Puebla"; Flota = 1 gabinete OPERATIVO; Multi-Tenant muestra
   rule_set v1; esperar 1–2 min y confirmar heartbeats frescos
   (`SELECT max(ts) FROM device_health;`).
10. **Registrar el resultado** aquí abajo (fecha, dump, conteos) — la fila de
    `audit_log` quedó dentro de la DB en el paso 6.
11. *(Opcional, después de verificar el dump)* borrar los objetos S3 del CSV del
    paso 5.

### Bitácora de ejecuciones

| Fecha | Dump | Resultado | Operador |
|---|---|---|---|
| _(pendiente)_ | | | |
