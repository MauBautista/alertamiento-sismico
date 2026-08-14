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
| **Huella del origen (`restore_check --save-baseline`)** | el MISMO cron de las 08:00, anclada al mismo snapshot que el dump | contra qué comparar el restore: inventario, columnas, constraints, privilegios, propiedad, conteos | 60 d (mismo prefijo, misma regla) | `s3://takab-dev-db-backups-<ACCT>/takab-YYYY-MM-DD.fingerprint.json` |

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

**Consecuencia operativa: la huella del origen viaja JUNTO al dump** (T-2.73.a). El mismo cron de
las 08:00 la escribe con `--save-baseline` y la sube al mismo prefijo, con la misma fecha en el
nombre: para el dump `takab-2026-08-09.dump` la huella es `takab-2026-08-09.fingerprint.json`.

**Y va anclada al MISMO snapshot que el dump**, que es lo que la hace utilizable. `row_counts`
exige igualdad exacta fila a fila —es la comprobación que caza las decenas de miles de filas
del §4.1— y la base de producción no está quieta: los latidos de la flota escriben cada minuto.
Una huella tomada a las 08:00:00 contra un dump que termina a las 08:04 daría **ROJO sobre un
restore perfecto**, y un falso rojo el día del desastre enseña al operador a desconfiar del
verificador. Por eso la huella abre una transacción `REPEATABLE READ`, exporta su snapshot con
`pg_export_snapshot()` y `pg_dump --snapshot=<id>` lo consume. Coste extra sobre la base:
ninguno — `pg_dump` ya sostenía una transacción idéntica durante todo el volcado.

**Si algún día falta la huella de una fecha, el veredicto de ese día es INDETERMINADO y eso es
la verdad.** El mecanismo es asimétrico a propósito: el `.dump` es *fail-open* (si la
coordinación se rompe, el volcado sale igual, sin ancla) y la huella es *fail-closed* (si no
queda anclada, no se sube). Una huella desalineada produciría ROJO, que sería mentira. El motivo
concreto queda escrito en `/var/log/takab-backup.log` de la instancia.

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

## 7. Las alarmas que vigilan todo esto

> **Son TRES, y cada una mira una cosa distinta.** Hasta T-2.72.b/c había una sola
> (`wal-archivado-atascado`) y su propio comentario dejaba fichadas las dos ausencias: mide la
> **cadena** de WAL, no su **ancla** ni el **disco** sobre el que vive todo.
>
> | Alarma | Qué mide | `treat_missing_data` |
> |---|---|---|
> | `takab-dev-wal-archivado-atascado` | la cadena de WAL (RPO) | `breaching` |
> | `takab-dev-backup-base-ausente` | el ancla de la cadena | `breaching` |
> | `takab-dev-disco-datos-lleno` | ocupación de `/data` | `missing` |

### 7.0 · `takab-dev-backup-base-ausente` (T-2.72.b)

`Takab/Ops/BaseBackupAgeSeconds`, `Maximum > base_backup_interval_days × chain_margin` (14 días
con los valores de hoy), 2 periodos de 5 min, `treat_missing_data = "breaching"`, los TRES estados
al topic de on-call.

- **Por qué hacía falta:** un `barman-cloud-backup` que falle cada semana **no mueve
  `WalArchiveAgeSeconds` ni un segundo**. El archivado sigue impecable y la cadena está rota,
  porque un WAL sin backup base no arranca. Es invisible hasta el día del restore.
- **El umbral NO es un número tecleado:** sale de las mismas variables que gobiernan la retención
  (`modules/database` lo deriva; `terraform output -json` del entorno lo enseña). Cambiar la
  política de retención mueve la alarma en el mismo commit.
- **NO es un aviso temprano, y hay que saberlo:** cuando dispara ya han fallado `chain_margin`
  backups base seguidos, y con los valores por defecto `7 × 2 = 14` días es **exactamente**
  `wal_retention_days` — o sea que el correo llega justo cuando la ventana de recuperación se
  cierra. Cazar el PRIMER backup base fallido exigiría una segunda alarma a `intervalo` días.
- **NACE EN ALARM el día del despliegue inicial, y es correcto:** todavía no se ha tomado ningún
  backup base. El publicador mide la edad **desde que se configuró el PITR**, no desde cero.
  **El correo de OK al terminar el primer `barman-cloud-backup` es el acuse de que la cadena
  consiguió ancla** — y es la única señal automática de que el respaldo base funcionó alguna vez.
- **Qué hacer cuando suena:** `/var/log/takab-pitr.log` en la instancia → ejecutar
  `/opt/takab/bin/takab-base-backup.sh` a mano → confirmar con `barman-cloud-backup-list`.
- **Cómo se publica:** dos piezas separadas a propósito. El *scan* (diario, 05:00) pregunta a
  `barman-cloud-backup-list` y guarda el instante en `/var/lib/takab/base-backup-last-epoch`; la
  *publicación* (cada minuto) deriva la edad de ese instante, porque la edad es función del reloj
  y no del listado. Publicar solo una vez al día sobre un periodo de un día dejaría ventanas de
  CloudWatch vacías en cuanto el cron se desplazara un minuto — y sobre `breaching`, cada ventana
  vacía es un correo diciendo que no hay respaldo.
- **Es INTOCABLE** (no silenciable por ventana de mantenimiento): callarla no pausa el riesgo, se
  come el margen que ya no queda.

### 7.1 · `takab-dev-disco-datos-lleno` (T-2.72.c)

`Takab/Ops/DataDiskUsedPercent`, `Maximum > 80 %`, 2 periodos de 5 min,
`treat_missing_data = "missing"` **con** `insufficient_data_actions`.

- **Por qué hacía falta:** con el archivado atascado Postgres **no recicla** su WAL y `pg_wal`
  crece ~16 MiB/min sobre el mismo volumen de 40 GiB donde vive el datadir: menos de dos días
  hasta llenar el disco. Eso ya lo cubría `wal-archivado-atascado` **por accidente** (900 s ≪ 48 h),
  pero por la vía indirecta — mide el archivado, no el disco. Cualquier **otra** causa de disco
  lleno (un log desbocado, un restore a base lateral, imágenes de docker acumuladas) era invisible.
- **`disk_used_percent` no existe en las métricas nativas de EC2:** el hipervisor no ve dentro del
  filesystem. Se publica desde la instancia por el cron que ya existe (`/etc/cron.d/takab-pitr`),
  no con el agente de CloudWatch: un demonio más en la máquina que sostiene DB + API + workers es
  un demonio más que puede morir en silencio.
- **`missing` y no `breaching`, al revés que sus dos vecinas:** el correo de esta alarma **afirma
  una medida** ("el disco pasó del 80 %"). Sin datapoint esa medida no existe. Una alarma que
  afirma lo que no sabe se deja de creer, y arrastra a las que sí saben.
- **La ceguera no queda tapada:** las dos causas del silencio ya paginan por otro lado — instancia
  caída ⇒ `ec2-status-check`, cron muerto ⇒ `wal-archivado-atascado`, las dos en `breaching`.
- **INSUFFICIENT_DATA aquí significa algo concreto y peor que el disco lleno:** el publicador se
  NIEGA a publicar si `/data` **no está montado** (`df /data` respondería con las cifras del
  volumen raíz, que se ven sanas). Si esta alarma queda en INSUFFICIENT_DATA, comprobar el montaje
  antes que nada.
- **Aritmética del margen:** cada punto porcentual son ~25 min a 16 MiB/min. Al 80 % quedan ~8 GiB
  ≈ 8,5 h. Por eso el umbral está validado a `(0, 90]`: por encima del 90 % el aviso llega
  demasiado tarde para hacer algo con la base en marcha.
- **Es INTOCABLE**: una ventana de 4 h puede comerse la mitad del margen del umbral.

### 7.2 · Comprobación POST-APPLY, obligatoria (~15 min después)

`insufficient_data_actions` **solo dispara al TRANSITAR**. Una métrica que no arranca NUNCA deja
la alarma **nacida** en INSUFFICIENT_DATA y aparcada ahí: sin correo, y con cara de "todavía no
hay datos". El script de configuración publica una primera medida de las tres métricas justo al
terminar, precisamente para forzar la transición — pero **eso hay que verificarlo una vez**:

```bash
aws cloudwatch describe-alarms --profile takab-dev --region us-east-2 \
  --alarm-names takab-dev-wal-archivado-atascado takab-dev-backup-base-ausente \
                takab-dev-disco-datos-lleno \
  --query 'MetricAlarms[].[AlarmName,StateValue]' --output table
```

Ninguna debe seguir en `INSUFFICIENT_DATA`. Estados esperados el primer día:
`wal-archivado-atascado` → `OK`; `backup-base-ausente` → **`ALARM`** (aún no hay backup base:
es correcto, y pasa a OK al terminar el primero); `disco-datos-lleno` → `OK`.
Si alguna sigue en `INSUFFICIENT_DATA`, el publicador no está corriendo: mirar
`/etc/cron.d/takab-pitr` y `/var/log/takab-pitr.log`.

### 7.3 · `takab-dev-wal-archivado-atascado`

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

### 9.1 · La huella del origen: CERRADO en software (T-2.73.a), pendiente de desplegar

Ya no falta el mecanismo; falta llevarlo a la máquina. Cómo quedó:

- **Quién la escribe:** el MISMO cron de las 08:00 (`/etc/cron.d/takab-backup`), a través del
  script `/opt/takab/bin/takab-backup.sh`. No hay una segunda entrada de cron: el script
  *sustituye* la línea que había puesto `user_data`.
- **El vehículo es el documento SSM `takab-dev-respaldo-logico`, con su asociación diaria**, no
  `user_data.sh.tpl`. Tocar `user_data` cambia un atributo de `aws_instance.db` y el provider
  responde **parando y arrancando la instancia** en el siguiente apply: la DB caería en un apply
  que nadie esperaba que la tocara. Además `user_data` corre una sola vez, en el primer boot, y
  aborta si encuentra `/var/lib/takab/.provisioned` — habría dado un `apply complete` que no
  cambia nada en la máquina que existe hoy. Hay una guardia de Terraform que pone el módulo en
  rojo si el mecanismo reaparece en `user_data.sh.tpl`
  (`modules/database/tests/huella_del_origen.tftest.hcl`).
- **Quién ejecuta el código:** el contenedor de la nube co-locada, con el mismo patrón que ya usa
  el `alembic upgrade head` del despliegue —
  `docker run --entrypoint python $TAKAB_CLOUD_IMAGE -m takab_api.ops.restore_check …`. La
  referencia de la imagen sale de `/etc/takab/deploy.env`.
- **Como superusuario `postgres`**, no `takab_app`: la huella tiene que ver exactamente lo mismo
  que ve el `pg_dump`. Con RLS forzada los conteos saldrían recortados y la huella mentiría hacia
  abajo. La contraseña se resuelve en la máquina contra Secrets Manager y vive en un env-file
  0600 en tmpfs que muere con la corrida; nunca en la línea de comando (`ps` la delataría).
- **Anclada al snapshot del dump** (§3), y con retención gratis: la clave comparte prefijo con la
  del dump, así que la misma regla de expiración y el mismo `s3:PutObject` la cubren sin tocar
  IAM ni `modules/storage`.

**Lo que hacía falta en la imagen, y no estaba.** El módulo sí viaja en `takab/cloud` (`COPY
api/src` en `api/Dockerfile`, y `psycopg[binary]` es dependencia de runtime), pero `db/schema.sql`
**no viaja**, y `capture_baseline()` lo leía. El comando habría muerto con `FileNotFoundError` la
primera madrugada. Se desacopló: la huella es el retrato de lo que el origen **tiene** y se toma
del catálogo (la función guarda sale de los bits de `pg_trigger.tgtype`); las *expectativas* —lo
que el esquema dice que debería tener— siguen siendo cosa de `verify()`, que corre con el repo
delante. Lo único que la huella sigue leyendo del repo son los roles, y salen de la migración
0001, que la imagen sí lleva.

**Código de salida propio:** al tomar la huella, `3` significa «no se pudo anclar, así que no hay
huella» — ni 0 (verde), ni 1 (rojo), ni 2 (indeterminado): «no hay huella» no es un veredicto
sobre ninguna base. El `.dump` de esa noche sí está en el bucket.

**Pendiente, y es lo único:** `terraform apply` del módulo + una imagen nueva de la nube. Hasta
que la imagen desplegada acepte `--coordinate-with-dump`, el dump seguirá subiendo **sin** huella
y el propio documento SSM lo dirá en voz alta en cada pasada (busca `AVISO: la imagen … NO
acepta` en la salida del comando). Checklist en §9.3.

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
- **`/var/log/takab-backup.log` no rota.** El cron del respaldo escribe ahí (antes su salida iba
  al correo de root de un EC2 sin MTA, o sea a ningún sitio). Son unas líneas por noche, así que
  es deuda de años, no de meses — pero está sin `logrotate`, igual que `/var/log/takab-pitr.log`.
- **El snapshot de la huella retiene tuplas muertas mientras está abierto**, igual que el propio
  `pg_dump` (no es coste nuevo: son dos transacciones concurrentes en vez de una). Si el script
  del cron muriera con `SIGKILL`, el `trap` no correría y el contenedor de la huella seguiría
  sosteniendo su snapshot hasta agotar `dump_coordination_timeout_s` (1 h). Está acotado y se
  auto-cura; se anota para que no se investigue como un misterio si algún día se ve.

### 9.3 · Puesta en marcha de la huella (para la ventana de `T-2.74`)

Cinco pasos, en orden. Los tres primeros son los que dejan la huella viva; los dos últimos son
la comprobación de que de verdad lo está.

```bash
export AWS_PROFILE=takab-dev AWS_REGION=us-east-2 ACCT=634882473845
DB_ID=$(terraform -chdir=infra/terraform/envs/dev output -raw db_instance_id)

# 1. Imagen nueva de la nube: la desplegada hoy NO conoce --coordinate-with-dump.
#    (~40 min; renueva SSO justo antes, el token expira a mitad del build).
make cloud-images && make cloud-deploy

# 2. Terraform: crea el documento SSM `takab-dev-respaldo-logico` y su asociación.
#    NO toca `user_data`, así que NO para la instancia. Confírmalo antes de aplicar:
#    en el plan, `aws_instance.db` no debe aparecer ni como update ni como replace.
terraform -chdir=infra/terraform/envs/dev plan  | grep -E 'aws_instance.db|user_data'
terraform -chdir=infra/terraform/envs/dev apply

# 3. La asociación NO se relanza sola al crearse la versión del documento: puede
#    tardar hasta 24 h. Fuérzala (mismo paso que el PITR de T-2.72):
aws ssm describe-instance-associations-status --instance-id "$DB_ID" \
  --query "InstanceAssociationStatusInfos[?AssociationName=='takab-dev-respaldo-logico'].AssociationId" --output text
aws ssm start-associations-once --association-ids <id>

# 4. LA INCÓGNITA, respondida en un comando: la salida de esa pasada dice si la
#    imagen desplegada sabe tomar la huella. Busca una de estas dos líneas:
#      OK: la imagen <...> sabe tomar la huella anclada
#      AVISO: la imagen <...> NO acepta --coordinate-with-dump
aws ssm list-command-invocations --instance-id "$DB_ID" --details \
  --query 'CommandInvocations[0].CommandPlugins[0].Output' --output text | tail -20

# 5. No esperes a las 08:00: dispara el respaldo a mano. Es ASÍNCRONO — espera a
#    que la invocación pase a Success antes de mirar el bucket.
CMD=$(aws ssm send-command --instance-ids "$DB_ID" --document-name AWS-RunShellScript \
  --parameters 'commands=["/opt/takab/bin/takab-backup.sh"]' \
  --query Command.CommandId --output text)
aws ssm get-command-invocation --command-id "$CMD" --instance-id "$DB_ID" \
  --query '{estado:Status,salida:StandardOutputContent}' --output text
aws s3 ls "s3://takab-dev-db-backups-$ACCT/takab-$(date +%F)"
#   -> deben aparecer LOS DOS: .dump y .fingerprint.json
```

Y el cierre del círculo, que es lo que acredita `R-1` del §8: descargar los dos objetos y correr
el §3 con `--baseline`. Si el veredicto sale **INDETERMINADO**, no marques nada: significa que la
huella no estaba o no se pudo leer, y `/var/log/takab-backup.log` de la instancia dice por qué.

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
