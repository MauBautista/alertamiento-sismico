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
