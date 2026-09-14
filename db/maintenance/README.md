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

---

## 2026-09-14 · Purga operativa pre-demostración (T-7.10)

**Decisión:** la demostración con cliente arranca con historial limpio. Se retira lo
recopilado de julio a septiembre de 2026 —los incidentes de las pruebas del WR-1, del
sensor golpeado a mano y de los arneses, con su familia y su telemetría— para que lo
que se enseñe ese día sea de ese día.

**En qué se diferencia de la purga del 2026-07-10**, que es lo que hay que tener claro
antes de ejecutarla: **aquélla se llevó la flota sim y conservó la telemetría real;
ésta conserva la flota ENTERA y se lleva la telemetría**. Copiar el script viejo
habría borrado los sitios y dejado al gabinete publicando contra un registro
inexistente.

**Qué conserva, y por qué:**

| | |
|---|---|
| `audit_log`, `actuation_records`, `pii_retention_runs` | regla de oro 11 — no se podan nunca |
| los cuatro `privacy_*` | avisos, consentimientos y ARCO: cumplimiento, no historial |
| tenants, sitios, gateways, sensores, zonas, `rule_sets`, cámaras, plantillas | flota e inventario |
| usuarios, llaves, alcances, códigos de alta | personas y accesos |
| `reference_earthquakes`, `gateway_catalog_state` | el catálogo, con la procedencia de `T-7.12` |
| `billing_meters_daily`, `ai_spend` | consumo acumulado: es facturación |

**Script:** [`2026-09-14_purge_operativa_demo.sql`](2026-09-14_purge_operativa_demo.sql)
— transacción única como superusuario, `session_replication_role = replica` (cubre los
triggers append-only copiados a los chunks de las hypertables y evita la tormenta
NOTIFY), conteos antes y después, y checks de orfandad embebidos. Idempotente.

⚠️ **Lleva un CENSO que revienta si aparece una tabla del esquema sin clasificar.** No
es ceremonia: sin él, una tabla nacida después de escribir esto se conservaría por
omisión y nadie se enteraría. Si la purga aborta diciendo un nombre, la respuesta es
decidir si su contenido es historial operativo o inventario — no quitar el censo.

**Probado sobre base efímera:** `demo/tests/test_purge_demo.py` crea una base, la migra
desde cero (no la clona: la base de tests tiene sesiones vivas y Postgres se niega a
usarla de plantilla), siembra, ejecuta el script ENTERO y comprueba lo que queda, lo que
no, que repetirlo no cambia nada y que el censo aborta **antes** de borrar.

### ⚠️ Cómo se VERIFICA el respaldo (dos trampas, dos restauraciones perdidas)

Un `pg_dump` que existe no es un respaldo; lo es uno que se ha restaurado. Medido el
2026-09-14 restaurando el dump de la nube en una base local:

1. **`pg_restore --jobs N` NO sirve con TimescaleDB.** La restauración paralela desordena
   el catálogo de Timescale y falla con
   `dimension_slice_chunk_id_fkey` / `compression_chunk_size_chunk_id_fkey`. El resultado
   es de los que engañan: las tablas normales quedan **perfectas** (incidentes,
   dictámenes, bitácora) y las **hypertables quedan en CERO** —9.4 millones de filas de
   features, 145 mil de salud— sin que nada diga «faltan datos». Se restaura **en serie**.
2. **`--single-transaction` lo aborta todo por un `SET` desconocido.** El `pg_dump` del
   portátil es más nuevo que el servidor (18.6 contra 16.14) y emite
   `SET transaction_timeout = 0`, que PG16 no conoce. Dentro de una transacción única eso
   tumba la restauración ENTERA y la base queda vacía. Sin ella es **un error ignorado** y
   todo lo demás entra.

El procedimiento que sí funcionó, entre `pre_restore` y `post_restore` (la mitad que ya
señalaba la Fase 2.6):

```bash
psql "$DSN_NUEVA" -c 'CREATE EXTENSION IF NOT EXISTS timescaledb' \
                  -Atc 'SELECT timescaledb_pre_restore()'
pg_restore -d "$DSN_NUEVA" --no-owner <dump>     # ni --jobs ni --single-transaction
psql "$DSN_NUEVA" -Atc 'SELECT timescaledb_post_restore()'
```

Y se comprueba **contando**, no leyendo la salida: las hypertables son las que se pierden
en silencio.

### Orden de ejecución

1. `pg_dump -Fc` con su `sha256`, copiado **fuera del EC2**, y **restaurado** según el
   apartado de arriba: sin contar filas, no está verificado.
2. CSV de `s3_key` de `evidence_objects` — los objetos de S3 **no se tocan aquí**.
3. Anotar los conteos ANTES (el script los imprime).
4. Editar `<SUB_DE_MAURICIO>` y `<NOMBRE_DEL_DUMP>`.
5. Ejecutar el script UNA vez y **leer la verificación antes de aceptar el COMMIT**: si
   algún conteo no cuadra o alguna orfandad da distinto de 0, `ROLLBACK`.
6. Registrar el resultado abajo.
7. *(Opcional, después de verificar el dump)* retirar los objetos S3 del CSV del paso 2.

### Bitácora de ejecuciones

| Fecha | Dump | Resultado | Operador |
|---|---|---|---|
| 2026-09-14 | `takab-2026-09-14.dump` (251 MB · sha256 `a0637eea0d4f…`) · **restaurado y contado** | 9 430 407 features, 145 512 latidos, 111 incidentes, 115 dictámenes, 49 evidencias, 8 simulacros retirados. Intactos: `audit_log` 948→949, `actuation_records` 35, 21 sitios, 8 gabinetes, 27 sensores, 1 usuario, catálogo 13. **Las 6 comprobaciones de orfandad en 0.** Base 3 233 → 2 192 MB. El gabinete volvió a alimentar en el mismo minuto. | Mauricio |
