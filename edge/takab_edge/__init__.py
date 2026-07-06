"""TAKAB Ailert — software del Raspberry Pi 5 (gateway de inteligencia del gabinete).

Módulos (blueprint §4.2): seedlink · signal · buffer · gpio · rules · actuators ·
cloud · health · config · security · local_api, orquestados por `supervisor`.

Regla de oro del edge (blueprint §4.2): `gpio` (+ signal→rules→actuators) funciona
SIN nube, y el reflejo SASMEX→sirena funciona incluso sin los demás módulos.
"""

__version__ = "0.1.0"
