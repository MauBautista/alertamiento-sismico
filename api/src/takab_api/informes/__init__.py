"""[T-9.42 · D-48] El informe posterior al evento, generado por el sistema, solo.

Un PDF por incidente, al estilo ShakeReport, que llega en ≤ 30 min desde la
apertura sin que nadie pulse «generar». El worker (`python -m takab_api.informes`)
corre la pasada de `pasada.py`; el aviso (correo a la cascada del sitio + push OPS
al círculo táctico) lo encola el orquestador de notificaciones al ver la acción
`post_event_report` que la pasada deja al terminar.
"""
