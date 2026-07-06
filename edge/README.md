# edge — Raspberry Pi 5 (gateway de inteligencia del gabinete)

Software del **Pi 5** (el cerebro del gabinete). Lee SeedLink del Raspberry Shake,
recibe SASMEX por el contacto seco del WR-1, corre reglas deterministas, dispara
actuadores (relés fail-safe + BACnet/IP) y sincroniza a la nube — **operando sin
internet**. **No se toca Shake OS.** Documento canónico: `takab-docs/BLUEPRINT-TECNICO-TAKAB.md §4`.

> Estado: **T-1.2 (scaffold + simuladores)** COMPLETA. Cada módulo expone su interfaz
> y un ciclo de vida mínimo; el cuerpo pleno de cada uno se implementa en su tarea
> (T-1.3…T-1.14, ver `takab-docs/TASKS.md`). Todo se desarrolla y prueba **sin
> hardware** vía los simuladores.

## Módulos (`takab_edge/`)

| Módulo | Rol | Tarea |
|---|---|---|
| `gpio` | WR-1 (contacto seco) + relés fail-safe (NO/NC/fail-close por canal) + **reflejo SASMEX→sirena in-process** (<100 ms). Canal primario y autoritativo. | T-1.3 |
| `seedlink` | Cliente SeedLink contra el RS4D (TCP 18000) → bus local. | T-1.5 |
| `signal` | Features 1 s (PGA, PGV, RMS, STA/LTA, clipping, health). | T-1.6 |
| `buffer` | Ring buffer crudo + extracción de ventana de evento. | T-1.7 |
| `rules` | Motor determinista tierizado (5 tiers) — **sin IA**. | T-1.8 |
| `actuators` | Interfaz `Actuator` única: driver relés (primario) + adaptador BACnet/IP. | T-1.9 |
| `health` | Autodiagnóstico por transición + heartbeat. | T-1.10 |
| `cloud` | MQTT mTLS + cola offline idempotente (nunca prerequisito para actuar). | T-1.11 |
| `config` | Store de umbrales/reglas/tenant + sync firmada. | T-1.12 |
| `security` | Comandos firmados (HMAC) + nonce anti-replay; mTLS/X.509. | T-1.12 |
| `local_api` | Dashboard/control local en LAN sin internet. | T-1.13 |
| `supervisor` | Arranque por orden de dependencias, cableado y watchdog. | T-1.2 |

**Reglas de oro respetadas:** el reflejo SASMEX→sirena vive en `gpio`, es
determinista, in-process y no depende de nube ni IA (`CLAUDE.md §2`). El quórum
colaborativo **no** vive aquí: se correlaciona en la nube (T-1.19).

## Simuladores (`simulators/`) — el edge se levanta sin hardware

- `rs4d` — feed SeedLink sintético **100 sps** (miniSEED) con inyección de eventos.
- `wr1`  — contacto seco del WR-1: alerta SASMEX + pulso de prueba de CIRES.
- `bacnet` — device BACnet/IP mock (gas/ascensores/puertas) que confirma escrituras.

## Uso

Requiere [`uv`](https://docs.astral.sh/uv/). Python 3.12 lo gestiona `uv` (`.python-version`).

```bash
uv sync --extra dev                         # entorno + deps (fija Python 3.12)
uv run ruff check . && uv run ruff format --check .   # lint + formato
GPIOZERO_PIN_FACTORY=mock uv run pytest -q   # tests, sin hardware
uv run takab-edge                            # levanta el gabinete completo (dev, simuladores)
```

En el Pi 5 real, instala el backend de hardware y desactiva el modo dev. En
producción la clave HMAC de comandos es **obligatoria** (nunca se hardcodea,
`CLAUDE.md §2.6`); inyéctala desde el entorno / Secrets Manager:

```bash
uv sync --extra dev --extra hardware         # + lgpio (GPIO nativo BCM2712)
export TAKAB_EDGE_HMAC_KEY="$(cat /run/secrets/takab_hmac_key)"
TAKAB_EDGE_DEV_MODE=false uv run takab-edge
```

Configuración por entorno con prefijo `TAKAB_EDGE_` (ver `takab_edge/config/settings.py`).
