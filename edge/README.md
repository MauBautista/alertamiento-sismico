# edge

Software del Raspberry Pi 5 (gateway de inteligencia del gabinete). Módulos (ver
`takab-docs/BLUEPRINT-TECNICO-TAKAB.md §4.2`): `seedlink`, `signal`, `buffer`, `gpio`, `rules`,
`actuators`, `cloud`, `health`, `config`, `security`, `local_api`, `supervisor` + units de systemd
y `simulators/` (RS4D · WR-1 · BACnet — todo el edge se desarrolla y testea sin hardware).

- `gpio` = WR-1 (entrada dry-contact) + relés locales fail-safe (NO/NC/fail-close por canal) +
  **reflejo SASMEX→sirena in-process** `[SUPUESTO plan-maestro-01 #6 — confirmar]`. El quórum
  colaborativo vive en la **nube**, no aquí.
- Actuación primaria del MVP: **relés** `[SUPUESTO #4]`; `actuators` es el adaptador BACnet/IP
  (gas, ascensores, puertas) detrás de la misma interfaz, activable por contrato.
- Lee SeedLink del Raspberry Shake (100 sps). **No tocar Shake OS.**

Placeholder — implementación en Bloque B de `takab-docs/TASKS.md` (T-1.2 a T-1.14); secuencia y
gates en `takab-docs/PLAN-MAESTRO-TAKAB.md`.
