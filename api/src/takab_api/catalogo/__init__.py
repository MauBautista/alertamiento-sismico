"""[T-7.25] Consulta a la fuente sísmica externa después del evento.

Dos piezas con responsabilidades separadas a propósito:

* :mod:`takab_api.catalogo.fdsn` — el cliente HTTP. **No sabe nada de la base**:
  pregunta, entiende la respuesta y, cuando no la hay, dice por qué. Se prueba
  entero sin Postgres y sin red.
* :mod:`takab_api.catalogo.consulta` — la pasada del worker. Registra el intento
  **antes** de salir a la red, reutiliza el criterio de identidad de
  `forensics/correlacion.py` para decidir cuál de los eventos publicados es el
  nuestro, y escribe el desenlace. Es el único escritor de
  ``reference_earthquakes`` junto con el seed.

**Por qué sólo USGS, y por qué el papel lo dice.** El SSN publica el catálogo
mexicano y su ingesta automática está decidida (`D-06`), pero la **atribución**
de sus cifras sigue sin cerrar. Una magnitud ajena impresa en un dictamen firmado
sin poder citarla como la fuente exige es exactamente lo que `T-5.10` existe para
impedir, así que la mitad SSN de `T-3.13` se queda fuera y el dictamen **lo
declara** en vez de callarlo: un lector que vea sólo «USGS» y no sepa por qué
supondrá que el SSN falló.

**Nada de esto toca el camino crítico** (reglas de oro 1 y 4). Corre en el worker
de incidentes, post-hoc, sobre incidentes que YA entraron en revisión; su caída,
su lentitud o la ausencia de internet no afectan al gabinete, ni a los actuadores,
ni a la ingesta. Lo peor que puede pasar es que la procedencia se quede en
``consultando`` — que es la verdad.
"""

from __future__ import annotations

from takab_api.catalogo.consulta import (
    PasadaDeConsulta,
    run_consulta_catalogo_pass,
)
from takab_api.catalogo.fdsn import PROVEEDOR, Respuesta, SinRespuesta

__all__ = [
    "PROVEEDOR",
    "PasadaDeConsulta",
    "Respuesta",
    "SinRespuesta",
    "run_consulta_catalogo_pass",
]
