# RUNBOOK · Backup y restore de la DB (Timescale en EC2) — hallazgo A-5

> **Estado: PROCEDIMIENTOS EJECUTABLES Y ENSAYADOS EN LOCAL (2026-08-08) · RESTORE REAL
> PENDIENTE (gate G-09).**
> **Criterio:** existe procedimiento ejecutable de restauración para los TRES mecanismos de
> respaldo, con RPO derivado de la configuración y RTO medible por un comando; el gate se
> cierra ejecutando una restauración REAL contra AWS, midiendo el RTO de producción y llenando
> el registro §8 (`T-2.74`).
>
> **Lo que cambió el 2026-08-08 (T-2.72/T-2.73), y por qué este documento ya no se parece al
> anterior:** el procedimiento que este mismo runbook documentaba **perdía datos en silencio**,
> y el checklist de verificación que traía **salía entero en verde sobre la base mutilada**
> (§4.1). Eso está medido, reproducido de forma independiente y corregido abajo. Si vienes de
> una copia vieja de este archivo, no la uses.

La DB es Postgres 16 + TimescaleDB **autogestionada en EC2** (contenedor
`timescale/timescaledb-ha:pg16`; RDS no soporta la extensión —
`modules/database/main.tf`). El dato vive en un volumen EBS dedicado gp3 40 GiB
adjunto como `/dev/xvdf` y montado en `/data`.

---

## 1. Qué existe HOY (tres mecanismos)

| Mecanismo | Cuándo | Qué captura | Retención | Dónde |
|---|---|---|---|---|
| **Archivado continuo de WAL (PITR)** | continuo (`archive_timeout = 60 s`) | cada transacción, hasta un punto en el tiempo | 14 d | `s3://takab-dev-db-backups-<ACCT>/pitr/takab-dev-db/wals/` |
| **Backup base de la cadena PITR** | semanal | el ancla desde la que se reproduce el WAL | 14 d | `.../pitr/takab-dev-db/base/<timestamp>/` |
| **Snapshot EBS (DLM)** | diario 03:00 UTC | instancia completa (root + datos), crash-consistent | 7 snapshots | EBS snapshots, tag `DlmBackup=true` |
| **Dump lógico (`pg_dump -Fc`)** | diario 08:00 UTC (cron en la instancia) | la base `takab` completa, consistente (MVCC) | 60 d | `s3://takab-dev-db-backups-<ACCT>/takab-YYYY-MM-DD.dump` |

**La herramienta del PITR es `barman-cloud`, no WAL-G**, aunque el plan original decía WAL-G.
Motivo: la imagen `timescale/timescaledb-ha:pg16` que corre en producción **ya trae barman-cloud
instalado y no trae wal-g** (verificado contra el contenedor real). Meter wal-g exigiría
reconstruir la imagen de la DB o descargar un binario y montarlo dentro del contenedor, o sea
**un eslabón de suministro nuevo justo en el camino de recuperación** — el último sitio donde
conviene tener uno. El diseño (archivado continuo, RPO derivado de la alarma, un solo podador)
no dependía de cuál fuera la herramienta.

Notas honestas:
- El cron del dump corre DENTRO de la instancia: si la instancia muere a las 07:59, el último
  dump es de ayer. **El PITR ya no tiene ese hueco**: el WAL sube continuo a S3.
- El snapshot EBS en caliente es **crash-consistent**: Postgres arranca y se recupera con su
  propio WAL, como tras un corte de luz. Aceptable; documentado.
- Las tablas de compliance (`audit_log`, `evidence_objects`, `dictamens`…) jamás se podan en
  la DB viva (regla de oro 11); la expiración aplica SOLO a los archivos de respaldo. El bucket
  `evidence` **no tiene ninguna regla de lifecycle, a propósito**, y hay un test que lo exige
  en la dirección contraria (`modules/storage/tests/lifecycle.tftest.hcl`).
- **La retención de la cadena PITR no es un número suelto**: `wal_retention_days (14) ≥
  base_backup_interval_days (7) × chain_margin (2)`, comprobado por una `validation` de
  Terraform. Con margen 1, el backup base más antiguo expiraría junto con los WAL que lo
  continúan y la ventana de recuperación se cerraría a cero cada semana sin que nada fallara.

### 1.1 · La retención que no retenía (defecto vivo desde julio-2026, corregido)

La regla de lifecycle `expira-60d` **nunca borró un solo byte**. Los buckets están versionados, y
sobre un bucket versionado `Expiration` no borra: **pone un delete marker** y la versión anterior
se queda como noncurrent para siempre, facturándose. Parecía una política de retención y era un
cambio de etiqueta.

Para el PITR habría sido peor que un coste: **el delete marker esconde el objeto al restaurador**
aunque los bytes sigan ahí. Corregido con `noncurrent_version_expiration` en todas las reglas de
todos los buckets, y con una guardia **de clase** (no de instancia) que impide que vuelva a
existir una regla con expiración y sin poda de noncurrent.

---

## 2. RPO y RTO

### RPO: 900 s (15 min), y sale de un comando

```bash
terraform -chdir=infra/terraform/envs/dev output -raw rpo_seconds     # 900
```

**No lo teclees aquí.** Ese número sale de los atributos del recurso de alarma, no de una
constante ni de una promesa:

```
RPO = umbral_de_la_alarma          + period × evaluation_periods
    = wal_archive_max_age_s (600)  + 60 × 5
    = 900 s = 15 min
```

**Por qué el segundo término existe, que es lo que hace honesta la cifra.** La tentación es decir
«`archive_timeout = 60 s` ⇒ RPO = 1 minuto». Eso toma el caso feliz de la configuración por el
peor caso. El RPO real no es lo que promete la configuración cuando todo va bien: **es la edad
del archivado a la que alguien SE ENTERA**. Si el archivado se atasca y la alarma no avisa hasta
los N segundos, durante esos N segundos se pierde WAL sin que nadie lo sepa. Y CloudWatch no
avisa al cruzar el umbral: avisa tras `evaluation_periods` periodos **seguidos** por encima —
durante esos 5 minutos se sigue acumulando WAL que no está en S3.

**Y la derivación es mentira si la alarma no está en `treat_missing_data = "breaching"`.** Si el
publicador de la métrica muere, la métrica desaparece; con `missing` o `notBreaching` la alarma
se quedaría callada para siempre y el RPO pasaría a ser ilimitado. Hay un assert de terraform
que lo exige, en dos archivos.

### RTO

- **RTO local, MEDIDO y reproducible por comando** (`make restore-drill`): ~2,3 s sobre un dump
  de ~570 KiB. Ese número **no acredita nada de producción** y el propio ensayo lo dice: no
  extrapola, porque el restore no es lineal en el tamaño (los índices se reconstruyen en tiempo
  superlineal) y la etapa de red es ortogonal al resto. Lo que sí sirve es que el procedimiento
  entero está ejercido y verificado en cada ensayo.
- **RTO de producción: SIGUE SIN MEDIR.** Faltan la descarga del dump desde S3 y la escala real.
  Es `T-2.74`.
- **Objetivo declarado: RTO ≤ 60 min** con runbook ensayado. El ensayo compara contra él y
  responde `NO COMPARABLE` a propósito — pero grita `EXCEDIDO INCLUSO EN LOCAL` si el ensayo de
  juguete ya no cabe, porque entonces producción tampoco.

---

## 3. Cómo se verifica un restore (léelo ANTES de los procedimientos)

```bash
cd api && DATABASE_URL=postgresql+psycopg://<user>:<pass>@<host>:<port>/postgres \
  uv run python -m takab_api.ops.restore_check \
    --database takab_restore \
    --baseline /tmp/takab-YYYY-MM-DD.fingerprint.json
```

22 comprobaciones con veredicto. Códigos de salida: **0 = VERDE · 1 = ROJO · 2 = INDETERMINADO**.

**El 2 importa tanto como el 1.** Sin `--baseline`, seis comprobaciones no se pueden ejercer
(inventario, columnas, constraints, privilegios, propiedad, conteos) y el veredicto es
**INDETERMINADO**, no verde: *un SKIP no es un PASS*. El operador que lee VERDE hace el swap, y
lo que no se comprobó no deja de estar roto por no haberlo mirado.

**Consecuencia operativa: la huella del origen tiene que viajar JUNTO al dump.** Se toma con
`--save-baseline`. Ver el hueco declarado en §9.1 — hoy el cron todavía no la escribe, y sin ella
un restore real solo puede acreditarse a medias.

Qué mira, agrupado por lo que se pierde si no se mira:

| Grupo | Comprobaciones |
|---|---|
| Compliance (regla de oro 11) | guardas append-only presentes **y ejercidas** — el UPDATE y el DELETE reales deben fallar, con el SQLSTATE de la guarda y no con otro cualquiera |
| Aislamiento (regla de oro 5) | RLS declarada y forzada, políticas presentes, vistas `security_barrier`, **cruce de tenants ejercido** como `takab_app`, dueños con BYPASSRLS |
| Integridad estructural | inventario de objetos, columnas, constraints validadas, índices válidos, secuencias por delante del dato, propiedad, privilegios |
| Timescale | hypertables que siguen siéndolo, políticas de retención/compresión/refresco **y que estén programadas** |
| El dato | conteos fila a fila contra el origen (incluidos los caggs materializados) y la punta de la telemetría |

---

## 4. Procedimiento A — Restore LÓGICO desde dump

Corrupción lógica, borrado accidental. Restaura a una base LATERAL primero; el swap es el último
paso y es reversible.

### 4.1 · Lo que este procedimiento decía hasta el 2026-08-08, y por qué se cambió

**Medido, y luego reproducido de forma independiente por un segundo revisor que no usó el mismo
código:** el procedimiento anterior, ejecutado literalmente, con el cliente del mismo major que
el servidor y sin ningún desajuste de versión, daba esto:

```
pg_restore: error: COPY failed for table "_hyper_1_10_chunk":
            ERROR:  could not find hypertable with id 1
pg_restore: error: could not execute query: ERROR: ONLY option not supported on hypertable operations
            Command was: ALTER TABLE ONLY public.device_health ADD CONSTRAINT device_health_pkey ...
pg_restore: warning: errors ignored on restore: 4
```

- **Decenas de miles de filas perdidas en silencio.** La magnitud es variable por corrida
  (depende de qué chunk aborta y cuánto se había copiado): tres mediciones sobre 600 000 filas
  dieron −11 471, −28 730 y −30 000. **Lo reproducible es la pérdida, no su tamaño.**
- **Las 3 PRIMARY KEY de las hypertables, desaparecidas.** Sin PK muere la idempotencia del edge
  (regla de oro 3: `ON CONFLICT DO NOTHING` ¿sobre qué?).
- **`--no-owner` traslada ~46 objetos a quien restaura**, y entonces
  `SET ROLE takab_migrator; ALTER TABLE sites …` responde `ERROR: must be owner of table sites`:
  **el siguiente `alembic upgrade head` del despliegue muere**.
- **`pg_restore` sin `--exit-on-error` sigue tras el fallo** y lo llama «errores ignorados».

Y el checklist de verificación que traía este runbook, aplicado verbatim a esa base mutilada,
**salió entero en verde**: `max(ts)` idéntico al origen, el `UPDATE audit_log` rechazado,
`extversion` correcta, 3 hypertables, RLS con sus dos banderas. Un checklist que no ve treinta mil
filas perdidas ni tres claves primarias no es una verificación: es una ceremonia.

Control causal: mismo dump, mismo cliente, mismo servidor, añadiendo los helpers de Timescale →
600 000/600 000 filas, las 3 PK, 46 objetos con su dueño, `rc = 0` y stderr vacío.

Para verlo en vivo: `make restore-drill DRILL_ARGS=--como-el-runbook` reproduce el procedimiento
viejo, imprime el checklist viejo al lado del verificador nuevo, y sale en ROJO.

### 4.2 · El procedimiento

```bash
ACCT=634882473845
# 1. Elegir el dump (el más reciente, o el anterior al incidente) y su huella:
AWS_PROFILE=takab-dev aws s3 ls s3://takab-dev-db-backups-$ACCT/ | sort | tail -5
AWS_PROFILE=takab-dev aws s3 cp s3://takab-dev-db-backups-$ACCT/takab-YYYY-MM-DD.dump /tmp/
AWS_PROFILE=takab-dev aws s3 cp s3://takab-dev-db-backups-$ACCT/takab-YYYY-MM-DD.fingerprint.json /tmp/

# 2. Restaurar a base lateral. Los helpers de Timescale NO son opcionales (§4.1).
docker exec -i takab-db psql -U postgres -c "DROP DATABASE IF EXISTS takab_restore;" \
  -c "CREATE DATABASE takab_restore;"
docker exec -i takab-db psql -U postgres -d takab_restore -v ON_ERROR_STOP=1 \
  -c "CREATE EXTENSION IF NOT EXISTS timescaledb;" \
  -c "SELECT timescaledb_pre_restore();"
docker exec -i takab-db pg_restore -U postgres -d takab_restore --exit-on-error \
  < /tmp/takab-YYYY-MM-DD.dump
docker exec -i takab-db psql -U postgres -d takab_restore -v ON_ERROR_STOP=1 \
  -c "SELECT timescaledb_post_restore();"

# 3. VERIFICAR (§3) contra takab_restore, NO contra takab. Sin verde, no hay paso 4.

# 4. Swap (VENTANA: parar API/workers primero — docker compose stop en la instancia):
docker exec -i takab-db psql -U postgres \
  -c "ALTER DATABASE takab RENAME TO takab_pre_restore;" \
  -c "ALTER DATABASE takab_restore RENAME TO takab;"
# rollback = invertir los dos RENAME. Al terminar: docker compose start.
```

Tres reglas que no están en los comandos y cuestan un restore:

1. **NO uses `--no-owner`.** Deja al rol de migraciones sin poder migrar.
2. **El restore solo vale si `rc = 0` Y stderr está vacío.** `warning: errors ignored on
   restore: N` no es un warning: es un restore roto.
3. **`pg_dump`/`pg_restore` deben ser del mismo major que el servidor (16.x).** Un cliente más
   nuevo emite `SET`s que el servidor 16 rechaza (medido: cliente 18.4 → `unrecognized
   configuration parameter "transaction_timeout"`), y `pg_restore` los reporta como «ignorados»
   — el mismo verde mentiroso por otra puerta.

---

## 5. Procedimiento B — Restore FÍSICO desde snapshot

Pérdida de instancia o de volumen.

```bash
# 1. Snapshot más reciente del volumen de DATOS (tag copiado por DLM):
AWS_PROFILE=takab-dev aws ec2 describe-snapshots --owner-ids self \
  --filters Name=tag:DlmBackup,Values=true \
  --query 'sort_by(Snapshots,&StartTime)[-3:].[SnapshotId,StartTime,VolumeId,Description]' --output table

# 2. Crear volumen en la MISMA AZ de la instancia destino:
aws ec2 create-volume --snapshot-id snap-XXXX --availability-zone us-east-2a --volume-type gp3

# 3. Parar la instancia (o usar una de recuperación), detach del volumen dañado,
#    attach del nuevo como /dev/xvdf, arrancar. El user_data ya monta /dev/xvdf y
#    levanta compose. Si se restaura la instancia COMPLETA: lanzar desde el
#    snapshot de root + attach de datos, y re-asociar la EIP del módulo serve.

# 4. Postgres se auto-recupera (crash-consistent) al arrancar takab-db.
# 5. VERIFICAR (§3) y MEDIR el RTO real (§8).
```

**Sobre un clúster LIMPIO, recrea los tres roles ANTES del restore.** Los roles son objetos de
clúster: un `pg_dump` de una base no los lleva. Si no lo haces, el verificador te lo dirá — pero
después de haber gastado la ventana. Los tres son `takab_migrator`, `takab_app` y `takab_ingest`
(este último con `BYPASSRLS`), y sus contraseñas están en Secrets Manager bajo `takab/dev/db/*`.

**Después de reponer el volumen, comprueba que el archivado de WAL volvió.** El documento SSM
reimpone la configuración una vez al día; si la instancia es nueva o el contenedor se recreó,
puede tardar hasta 24 h en converger sola. Fuérzalo:

```bash
aws ssm start-associations-once --association-ids <id>
```

---

## 6. Procedimiento C — Restore a un PUNTO EN EL TIEMPO (PITR)

**Es el procedimiento nuevo y el único que deshace un error de hace diez minutos** en vez de
«volver a ayer». Deshacer un `DELETE` accidental de las 14:32 sin perder lo escrito hasta las
14:31 es exactamente lo que los otros dos no saben hacer.

`barman-cloud` corre DENTRO del contenedor de la DB y firma con el rol de la instancia.

```bash
S3=s3://takab-dev-db-backups-634882473845/pitr
SRV=takab-dev-db

# 1. Ver los backups base disponibles y elegir uno ANTERIOR al punto objetivo:
docker exec takab-db barman-cloud-backup-list $S3 $SRV

# 2. Restaurar el base a un datadir NUEVO (jamás sobre el vivo):
docker exec takab-db barman-cloud-restore $S3 $SRV <backup_id> /home/postgres/pgdata/restore

# 3. Declarar hasta dónde reproducir el WAL y de dónde sacarlo:
#    en postgresql.auto.conf del datadir restaurado:
#      restore_command = 'barman-cloud-wal-restore <S3> <SRV> %f %p'
#      recovery_target_time = '2026-08-08 14:31:00+00'
#      recovery_target_action = 'promote'
#    y un fichero vacío `recovery.signal` en la raíz del datadir.

# 4. Arrancar un Postgres SEPARADO sobre ese datadir (otro puerto, otro contenedor).
#    Espera a que termine la recuperación; el log dice `recovery stopping before ...`.

# 5. VERIFICAR (§3) contra esa instancia. La punta del dato debe estar en el objetivo,
#    no en el presente: es la comprobación que dice si el PITR hizo lo que se le pidió.

# 6. Extraer lo que haga falta (pg_dump de una tabla) o promover la instancia entera.
```

**Este procedimiento NO está ensayado todavía.** Es parte de `T-2.74`, y es el que más
sorpresas puede dar: el sufijo de compresión de los WAL y el layout interno de barman hay que
medirlos contra el bucket real.

**Vigila el disco mientras tanto.** Con el archivado atascado, Postgres **no recicla** su WAL:
`pg_wal` crece ~16 MiB/min sobre el mismo volumen de 40 GiB donde viven los datos. **Menos de
dos días hasta llenar el disco y tumbar la DB.** La alarma de atasco (900 s) va muy por delante
de eso, pero lo primero que hay que mirar al recibirla es el espacio libre en `/data`.

---

## 7. La alarma que vigila todo esto

`takab-dev-wal-archivado-atascado` — namespace `Takab/Ops`, `Maximum > 600 s`, 5 periodos de 60 s
seguidos, `treat_missing_data = "breaching"`, y los TRES estados (ALARM, OK, INSUFFICIENT_DATA)
al topic de on-call.

- **`breaching` no es una preferencia: sostiene el RPO.** Ver §2.
- **El correo de OK importa tanto como el de ALARM**: es la única señal de que la métrica
  arrancó. Una alarma nacida en INSUFFICIENT_DATA se queda ahí para siempre, sin transición y
  sin correo.
- **Es INTOCABLE**: no se puede silenciar con una ventana de mantenimiento, y la política IAM lo
  impide además del código. El contraargumento —durante un mantenimiento el archivado se para
  legítimamente y la alarma suena— está contestado: el momento más probable de que el archivado
  se rompa **para siempre** es justo después de una ventana (config revertida, contenedor
  recreado sin `archive_mode`, credenciales que ya no resuelven), así que callarla durante la
  ventana es callar exactamente la señal de que la ventana rompió el respaldo.
- **Falso positivo conocido**: con la base COMPLETAMENTE ociosa no hay cambio forzado de
  segmento y la alarma dispara sin que nada esté roto. El error va hacia el lado seguro. Aquí es
  improbable porque los latidos de la flota escriben cada minuto; si algún día la nube se queda
  sin gabinetes conectados, esta es la explicación del correo.

---

## 8. Registro de verificación (G-09 — llenar al ejecutar; SIN marcar hasta entonces)

| # | Prueba | Esperado | Medido | OK/NO | Fecha/inicial |
|---|---|---|---|---|---|
| R-1 | Restore lógico (Proc. A) a `takab_restore` | verificador VERDE (22/22) |  |  |  |
| R-2 | Swap + rollback del swap | app funciona en ambos sentidos |  |  |  |
| R-3 | Restore físico (Proc. B) en volumen/instancia limpia | Postgres arranca y verificador VERDE |  |  |  |
| R-4 | **Restore PITR (Proc. C) a un punto elegido** | la punta del dato en el objetivo, no en el presente |  |  |  |
| R-5 | RTO medido (A, B y C) | ≤ 60 min |  |  |  |
| R-6 | RPO verificado (`max(ts)` vs hora del "desastre") | ≤ 900 s con PITR |  |  |  |
| R-7 | La alarma de archivado sale de INSUFFICIENT_DATA | correo de OK recibido |  |  |  |
| R-8 | Primer `barman-cloud-backup` ejecutado y listado | aparece en `backup-list` |  |  |  |

---

## 9. Lo que sigue faltando, con nombre

### 9.1 · La huella del origen no se sube (bloquea la acreditación de G-09)

El cron de las 08:00 sube el `.dump` y nada más. **Sin la huella del origen, el verificador
devuelve INDETERMINADO** y seis de sus comprobaciones más fuertes no se pueden ejercer — incluidas
las que cazan columnas, constraints, privilegios y conteos.

Forma exacta: que el mismo cron escriba también
`python -m takab_api.ops.restore_check --database takab --save-baseline <fichero>` y lo suba al
mismo prefijo. **El vehículo debe ser el documento SSM, no `user_data.sh.tpl`** — tocar el
user_data fuerza al provider a parar y arrancar la instancia en el siguiente apply, y la DB
caería. Hay que confirmar en la ventana que el contenedor de la nube co-locada tiene el código
del API disponible para invocarlo. Ficha: `T-2.73.a`.

### 9.2 · Deudas menores, todas con su forma escrita

- **Verificar que el WAL llegó de verdad a S3.** `pg_stat_archiver.last_archived_time` mide el
  último `archive_command` que devolvió 0; un comando que devolviera 0 sin subir nada (el
  ejemplo de la propia doc de PostgreSQL es `archive_command = /bin/true`) reportaría salud
  perfecta con cero WAL en el bucket. Forma barata ya diseñada: `last_archived_wal` da el NOMBRE
  del segmento, así que un `head-object` O(1) contra la clave esperada cierra el caso sin listar
  nada. Acopla con el sufijo de compresión de barman: se mide en la ventana.
- **No hay alarma de BACKUP BASE ausente.** La métrica mide la cadena de WAL, no su ancla. Un
  backup base que falla cada semana es invisible hasta el restore.
- **No hay alarma de espacio en disco** (exige el agente CloudWatch; `disk_used_percent` no
  existe en las métricas nativas de EC2). Ver el reloj corto del §6.
- **Punto ciego de `stats_reset`**: si las estadísticas se reinician, `last_archived_time` vuelve
  a NULL y la edad se cuenta desde el reinicio; la alarma se pone verde durante como mucho 600 s
  aunque no se archive nada. Se auto-cura.
- **El multipart huérfano del dump.** `aws s3 cp -` desde stdin es multipart obligatoriamente
  (tamaño desconocido) y su prefijo no tiene ni permiso de aborto ni regla de barrido — la cadena
  PITR sí los tiene. No es regresión (antes tampoco existían).
- **El ensayo de restore no corre en CI.** Corre el verificador entero con sus mutaciones en cada
  PR, que es la pieza que se pudre; el ensayo en sí exige fijar `postgresql-client-16` en el job
  `api`. Está escrito en el Makefile por qué.

---

## 10. Relación con el resto del sistema

- Los objetos de EVIDENCIA (miniSEED, PDFs) viven en S3 (`evidence`), fuera de esta DB y de
  este runbook; su durabilidad es la de S3. Ese bucket **no tiene lifecycle a propósito** y hay
  un test que lo exige. Este runbook cubre la base relacional.
- El spool del edge re-entrega lo no confirmado al reconectar (idempotencia por `event_uuid`):
  tras un restore, el gabinete rellena el hueco de SUS eventos aunque la nube haya perdido
  tiempo. Es una razón más por la que el camino de vida sobrevive a un restore — pero **no es un
  sustituto del respaldo**: no repone telemetría agregada, ni estado de consola, ni nada que no
  haya nacido en un gabinete.
- **La idempotencia del edge depende de las PRIMARY KEY** que el procedimiento viejo perdía
  (§4.1). Un restore mal hecho no solo pierde filas: desarma el mecanismo que iba a reponerlas.
