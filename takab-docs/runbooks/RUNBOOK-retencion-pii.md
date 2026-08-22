# RUNBOOK · Retención de PII (T-2.81 · T-2.81.a · T-2.81.b)

> **Qué cambia respecto de ayer.** El job de retención existía y era invocable, y **no lo llamaba
> nadie**. Una retención que nadie ejecuta es una política escrita, no una cumplida — y la
> diferencia importa el día que un cliente pregunta cuánto tiempo guardamos su teléfono. Ahora lo
> llama un cron declarado en Terraform, cada corrida deja fila en la base, y una alarma suena si
> deja de correr.

---

## 1. Qué corre, dónde y cuándo

| Pieza | Dónde vive |
|---|---|
| El plan (qué caduca, con qué reloj y por qué) | `api/src/takab_api/privacy/retention.py` |
| El job (se degrada de rol, deriva del catálogo qué es intocable, simula y poda) | `api/src/takab_api/ops/prune_pii.py` |
| El cron | documento SSM `takab-dev-retencion-pii` + asociación `rate(1 day)` (`infra/terraform/modules/database`) |
| En la máquina | `/opt/takab/bin/takab-prune-pii.sh` · `/etc/cron.d/takab-prune-pii` · `/var/log/takab-prune-pii.log` |
| La constancia de cada corrida | tabla `pii_retention_runs` |
| La alarma | `takab-dev-retencion-pii-detenida` (`Takab/Ops/PiiRetentionAgeSeconds`) |

**Cadencia: 06:00 UTC.** Los snapshots DLM van a las 03:00, el backup base a las 04:00, su scan a
las 05:00 y el dump lógico a las 08:00. Las 06:00 es la única franja libre y, además, deja la
corrida **antes** del dump: así el respaldo del día se lleva la PII ya podada.

**El job corre con `--apply` y aun así hoy no poda nada**, porque los plazos no están decididos
(§2). Sin plazo, cada regla queda **deshabilitada**: el default bajo incertidumbre es no borrar
nada. Mientras tanto la corrida diaria sirve para lo que sí se puede afirmar hoy — que el reloj se
revisa y que el mecanismo funciona.

---

## 2. Declarar los plazos (DECISIÓN DE NEGOCIO, no de programador) — `HUMANO`

Cuánto tiempo se guarda el teléfono de una persona sale de la ficha legal y del contrato con cada
cliente. Se declaran en `infra/terraform/envs/dev` con la **clave de la regla**:

```hcl
module "database" {
  # ...
  pii_retention_windows_days = {
    "push_tokens.token"      = 400   # token de dispositivo sin verse
    "life_checkins.geom"     = 90    # ubicación GPS de un check-in cerrado
    "user_profiles.identity" = 365   # nombre y teléfono TRAS LA BAJA de la cuenta
  }
}
```

Las tres reglas del plan de hoy son exactamente esas tres claves; cualquier otra la rechaza la
validación de la variable (un plural de más no puede salir verde y no podar nada).

**LATENCIA, y aquí importa más que en el PITR:** cambiar esta variable crea una **versión nueva**
del documento SSM pero **no modifica ningún atributo de la asociación**, así que Terraform informa
`apply complete` y el cambio aterriza en la siguiente pasada — hasta 24 h después. Para que surta
efecto ya:

```bash
aws ssm start-associations-once --association-ids <id> --profile takab-dev --region us-east-2
```

---

## 3. Antes de podar de verdad: el simulacro — `HUMANO`

El job simula por defecto. Es la corrida que hay que mirar antes de declarar plazos en producción:

```bash
# En la instancia, con la imagen desplegada:
docker run --rm --network host --env-file /run/takab-prune-pii.XXXX/db.env \
  --entrypoint python "$TAKAB_CLOUD_IMAGE" -m takab_api.ops.prune_pii \
  --days 365 --json /tmp/simulacro.json
```

El informe trae, por regla y por tenant, cuántas filas caducarían. Nada se toca sin `--apply`, y
con `--apply` el conteo previo **es la autorización**: si el `ROW_COUNT` no cuadra con lo contado,
la corrida entera se revierte.

---

## 4. Comprobar que la retención se está ejecutando

```sql
-- Las últimas corridas, con su desenlace y su razón si falló.
SELECT finished_at, mode, ok, total_due, total_applied, error
  FROM pii_retention_runs ORDER BY finished_at DESC LIMIT 10;
```

Una corrida abortada **también deja fila** (`ok = false` con su razón): la constancia se escribe
**fuera** de la transacción del job, precisamente para que el rollback no se lleve por delante el
registro de la corrida que falló.

De ahí sale la métrica: el publicador de la instancia pregunta `max(finished_at) WHERE ok` y
publica su **edad** cada minuto. Por eso la alarma mide la retención y no el cron: un job que
falla todos los días no refresca esa edad y la alarma sube sola.

---

## 5. La alarma · `takab-dev-retencion-pii-detenida`

`Takab/Ops/PiiRetentionAgeSeconds`, `Maximum > cadencia × margen` (**2 días** con los valores de
hoy), 2 periodos de 5 min, `treat_missing_data = breaching`, los TRES estados al topic de on-call.

- **`breaching`** por lo mismo que `backup-base-ausente`: lo que el correo afirma no es una medida
  instantánea sino un grado de cumplimiento. Sin métrica eso es DESCONOCIDO — y una retención
  desconocida es, ante el cliente que pregunta, igual de defendible que una que no corre. Además
  el que publica y el que poda son el mismo host y el mismo `/etc/cron.d/takab-prune-pii`.
- **NACE EN ALARM el día del apply**, y está bien: todavía no consta ninguna corrida. **El correo
  de OK tras la primera corrida es el acuse** de que la retención llegó a ejecutarse alguna vez.
  Si ese correo no llega, *eso* es el hallazgo.
- **Es INTOCABLE** (`ops/muting.py`): no se puede silenciar en una ventana de mantenimiento. No hay
  ruido que evitar —su umbral ya son dos días— y lo que se perdería callándola es el único aviso.

Qué mirar cuando suene, en este orden:

```bash
sudo tail -100 /var/log/takab-prune-pii.log          # 1. qué dijo la última corrida
sudo /opt/takab/bin/takab-prune-pii.sh               # 2. correrla a mano
sudo /opt/takab/bin/takab-prune-pii-age.sh           # 3. republicar la edad
```

---

## 6. El reloj del nombre y el teléfono (T-2.81.b) — lo que hay que saber

`user_profiles.display_name` y `phone` **no caducan por antigüedad del perfil**. Su reloj es la
**baja de la cuenta**, que se registra en `user_deactivations` cuando el administrador del cliente
deshabilita (`PATCH {"enabled": false}`) o borra (`DELETE /users/{u}`) la cuenta desde la consola,
en la misma transacción que ya deja la fila de `audit_log`. Volver a habilitarla **para** el reloj.

Usar `updated_at` como reloj habría borrado antes los nombres de quien más tiempo lleva en el
edificio — exactamente al revés de lo que la retención pretende.

**HUECO CERRADO el 2026-08-22 (`T-2.143`).** Una cuenta retirada **directamente en el pool de
Cognito** (consola de AWS, CLI) no pasa por la API, así que no deja reloj por sí sola. Ahora el
propio job lo reconcilia **antes de podar**: `privacy/reconcile.py` compara el padrón con el
directorio y arranca el reloj (`via = 'account_deleted'`) de quien ya no está. Corre por defecto;
`--sin-reconciliar` lo apaga —el flag **apaga, no enciende**, porque un paso de cumplimiento que
hay que acordarse de pedir es exactamente el defecto que la ficha cerraba—.

> **Lo que NO sabe, y conviene tenerlo presente:** *cuándo* se borró la cuenta. El pool no guarda
> fecha de lo que ya no está, así que el reloj arranca el día en que la reconciliación se entera y
> no el del hecho. Alarga el plazo real, que es el lado seguro del error. Por eso esto sigue siendo
> una red de seguridad: **las bajas se hacen desde la consola de TAKAB**.

> **Y se niega a actuar con una lectura a medias.** Si el directorio no responde, si la paginación
> no termina o si el pool devuelve **cero** cuentas, la corrida **aborta entera** y lo dice en el
> log (`RECONCILIACIÓN OMITIDA · …`). Los tres casos son indistinguibles de «los han borrado a
> todos», y actuar sobre ellos pondría en marcha el borrado del nombre de cada persona de cada
> edificio. Un fallo aquí **no aborta la poda**: se avisa y se sigue, porque el peor caso es que
> unos relojes arranquen una corrida más tarde.

Para auditar el desfase a mano (misma consulta que usa el job):

```sql
-- Perfiles del padrón sin baja registrada, ordenados por antigüedad.
SELECT p.tenant_id, p.user_sub, p.updated_at
  FROM user_profiles p
  LEFT JOIN user_deactivations d USING (tenant_id, user_sub)
 WHERE d.user_sub IS NULL ORDER BY p.updated_at;
```

y contrastar con `aws cognito-idp list-users`. Si esa consulta devuelve a alguien que **tampoco
está en el pool**, es que la reconciliación no ha corrido todavía o abortó: mira el log del cron
por `RECONCILIACIÓN`.

---

## 7. Comportamiento con volumen — MEDIDO

La corrida entera es **una sola transacción**, y es una decisión: el conteo previo es la
autorización de la poda, y media poda con informe en verde es peor que ninguna.

**Medido el 2026-08-14** (Postgres 16, 1 000 000 de filas de `push_tokens`, todas caducadas,
cuatro tenants): **41.8 s de transacción abierta**, ~42 µs/fila, lineal. Re-medible con
`api/tests/perf/test_prune_pii_volumen.py`.

Consecuencias que hay que tener presentes en la ventana:

- El job **no lleva `statement_timeout`**, y no es un olvido: cualquiera de los topes existentes
  (request 20 s, worker 15 s) mataría esa corrida legítima a mitad. Convertir trabajo correcto en
  fallo no es una mejora.
- **Sí lleva `lock_timeout` (30 s)**, que es otro modo de fallo: sin él, una fila bloqueada por
  otra sesión deja al job esperando para siempre dentro de una transacción que ya sostiene el
  horizonte de `xmin`. El número vive en `api/src/takab_api/db/session.py` con el resto de la
  política de topes.
- La **primera** corrida tras declarar los plazos es la cara (procesa todo el histórico); las
  siguientes son el delta diario. Si el histórico fuera de varios millones de filas, conviene
  lanzarla a mano y fuera de horario la primera vez, mirando `pg_stat_activity`.
