# Runbook · Desplegar el edge al Pi 4 (T-1.40)

```bash
deploy/edge/deploy.sh            # default: host ssh «takab-pi5»
deploy/edge/deploy.sh otro-host  # otro gabinete
```

Qué hace: rsync de `edge/` + `shared/schemas/` a una **release nueva**
(`/opt/takab/releases/<ts>-<sha>/`) con su **propio venv**, `uv sync`, instala
las unidades systemd versionadas (`edge/systemd/`) y **activa** la release por
`/opt/takab/bin/canary.sh`. **No toca credenciales**:
`/etc/takab/{certs,edge.env}` son territorio de `infra/scripts/provision_gateway.sh`.

## Layout A/B y vuelta atrás (T-2.70)

```
/opt/takab/
├── edge -> releases/<id>/edge     ← SYMLINK: es lo que los ExecStart nombran
├── releases/<id>/
│   ├── edge/{takab_edge,.venv,FW_VERSION,systemd}
│   └── shared/schemas/            ← los contratos viajan CON su código
└── bin/canary.sh                  ← el reversor, FUERA de toda release
```

**La activación no es un `restart`.** `canary.sh` repunta el symlink, reinicia
al **cliente** (`takab-edge`, nunca `takab-gpio`) y mide salud **sostenida**
durante el remojo: unidad activa, MainPID sin relevo (un crash-loop se delata
ahí y no en `is-active`), pines con dueño y panel contestando. Si falla, vuelve
sola a la release anterior — código **y** dependencias.

```bash
ssh takab-pi5 'sudo /opt/takab/bin/canary.sh estado'    # veredicto de la última activación
ssh takab-pi5 'sudo /opt/takab/bin/canary.sh revertir --motivo "..."'   # vuelta atrás a mano
```

> ### ⚠️ Revertir después de una ventana de mantenimiento deja al dueño MÁS NUEVO
> `canary.sh revertir` sólo reinicia `takab-edge`. Si el despliegue que se revierte
> reinició también a `takab-gpio` (`--ventana-de-mantenimiento`) y su release
> añadía un campo a la instantánea del gabinete —T-9.75 añade `siren_demanded`—,
> el cliente viejo **rechaza cada instantánea** del dueño nuevo
> (`pinlink/codec.py`, «el despliegue va al revés»). El reflejo SASMEX y las
> órdenes de relé siguen funcionando, pero:
> - el panel se queda sin datos;
> - la nube ve el gabinete DEGRADADO;
> - el re-armado no llega a los secundarios.
>
> Esa vuelta atrás se hace **en la misma ventana** y reiniciando también
> `takab-gpio` a la release anterior.

### Qué release ejecuta el dueño de los pines (T-8.17 · A-076)

Un despliegue normal no reinicia `takab-gpio`, así que el dueño puede seguir en
una release que el symlink ya no nombra. Él mismo lo dice en el registro del
cerrojo:

```bash
ssh takab-pi5 'cat /var/lib/takab/gpio.lock'
# pid=812  unit=takab-gpio  release=/opt/takab/releases/<id>/edge  version=<sha>
```

`deploy.sh` lo usa para dos cosas:
- **7.b** da por nuevo al dueño sólo si esa release **es** la activa; si no,
  compara su código contra ella. Antes comparaba contra la que el symlink
  apuntaba antes del despliegue (un segundo despliegue sin ventana daba ✓ con el
  dueño todavía en código anterior) y miraba la hora de arranque.
- **La poda** nunca la borra.

Un dueño anterior a T-8.17 no escribe `release=`. Mientras siga vivo, 7.b sale ✗
(«no dice desde qué release arrancó») y **la poda se aplaza**. La ventana de
mantenimiento que lo reinicia deja la línea escrita. Un registro **vacío** (disco
lleno al arrancar el dueño) también aplaza la poda, y en un gabinete D3 sin
ventana sale ✗: mira `df -h /var/lib/takab`.

> ### ⚠️ El primer despliegue A/B de un gabinete es una MIGRACIÓN
> Convierte `/opt/takab/edge` de directorio a symlink, o sea que **cambia la ruta
> desde la que arranca el camino de vida**. `deploy.sh` se niega a hacerlo sin
> `--ventana-de-mantenimiento`, y **no se declara bueno con tests en verde**:
> exige el gate **`G-01`** (restart en frío del Pi con las dos unidades volviendo
> solas). Ver `takab-docs/runbooks/RUNBOOK-sesion-de-vida.md`.

Orden con la nube (cambios de contrato como el de T-1.40): **primero la nube**
(`make cloud-images && make cloud-deploy` — tolera los campos nuevos ausentes),
**después el edge** (empieza a mandarlos). Al revés, un ingest viejo rechazaría
los payloads nuevos.

Verificación post-deploy:

```bash
ssh takab-pi5 'journalctl -u takab-edge -n 20 --no-pager'   # arranque limpio
# y en la consola SOC: /fleet debe mostrar NTP/cert/RTT reales y «UPS · S/D».
```
