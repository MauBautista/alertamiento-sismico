"""T-7.24 · Mini-ShakeMap por evento.

Tres módulos con tres responsabilidades que no se cruzan:

* :mod:`calculo` — las tres capas en lógica PURA (sin base, sin red, sin reloj).
* :mod:`servicio` — la pasada del worker que las calcula y persiste el snapshot.
* :mod:`lectura` — leer el snapshot ya calculado, para el endpoint y para el PDF.

**No es un microservicio** (`design/BLOQUE-IV-ARQUITECTURA.md §A.4`): se calcula
por evento en el worker de incidentes que ya existe. Un servicio más sería un
despliegue más, una alarma más y una superficie más que puede caerse, y lo que se
calcula aquí no es continuo.
"""

from __future__ import annotations
