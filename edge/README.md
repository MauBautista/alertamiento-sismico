# edge

Software del Raspberry Pi 5 (gateway de inteligencia del gabinete). Módulos (ver
`takab-docs/BLUEPRINT-TECNICO-TAKAB.md §4.2`): `seedlink`, `signal`, `buffer`, `sasmex`, `rules`,
`actuators`, `quorum`, `cloud`, `health`, `config`, `security`, `supervisor` + units de systemd.

Lee SeedLink del Raspberry Shake, recibe SASMEX por GPIO, dispara actuadores BACnet/IP (sirena,
gas, ascensores, puertas) y sincroniza a la nube. **No tocar Shake OS.**

Placeholder — implementación en Bloque B de `takab-docs/TASKS.md` (T-1.2 a T-1.14).
