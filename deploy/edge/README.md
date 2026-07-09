# Runbook · Desplegar el edge al Pi 5 (T-1.40)

```bash
deploy/edge/deploy.sh            # default: host ssh «takab-pi5»
deploy/edge/deploy.sh otro-host  # otro gabinete
```

Qué hace: rsync de `edge/` + `shared/schemas/` a `/opt/takab/` (preserva el
`.venv` del Pi), `uv sync --extra hardware`, instala las unidades systemd
versionadas (`edge/systemd/`) y reinicia `takab-edge` verificando que quede
activo. **No toca credenciales**: `/etc/takab/{certs,edge.env}` son territorio
de `infra/scripts/provision_gateway.sh`.

Orden con la nube (cambios de contrato como el de T-1.40): **primero la nube**
(`make cloud-images && make cloud-deploy` — tolera los campos nuevos ausentes),
**después el edge** (empieza a mandarlos). Al revés, un ingest viejo rechazaría
los payloads nuevos.

Verificación post-deploy:

```bash
ssh takab-pi5 'journalctl -u takab-edge -n 20 --no-pager'   # arranque limpio
# y en la consola SOC: /fleet debe mostrar NTP/cert/RTT reales y «UPS · S/D».
```
