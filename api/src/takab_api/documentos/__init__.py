"""[T-7.21] El papel oficial: el chasis que comparte todo documento que sale.

`membrete.MembretePDF` es la promoción de lo que era `dictamen/layout.py::TakabPDF`:
cabecera, pie, tipografía, paleta y primitivas. Lo hereda el dictamen pericial, el
reporte de simulacro y —desde `T-7.22`— el informe del evento.

Vive fuera de `dictamen/` porque un reporte de simulacro no es un dictamen y el
informe del evento tampoco: el chasis era compartido de hecho desde que
`drill_report.py` empezó a instanciar `TakabPDF`, y esto sólo reconoce el reparto
que ya existía.
"""
