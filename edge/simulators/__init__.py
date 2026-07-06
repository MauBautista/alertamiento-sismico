"""Simuladores del edge — desarrollar y testear el gabinete completo sin hardware.

- ``rs4d``   : feed SeedLink sintético 100 sps (miniSEED) + inyección de eventos.
- ``wr1``    : contacto seco del WR-1 (alerta SASMEX + pulso de prueba de CIRES).
- ``bacnet`` : device BACnet/IP mock (gas/ascensores/puertas) que confirma escrituras.

Ciudadanos de primera clase (PLAN-MAESTRO §5, bus factor 1): todo el edge se
valida contra ellos; el hardware-in-the-loop es opcional y hardware-gated.
"""

from simulators.bacnet import BacnetSimulator
from simulators.rs4d import DEFAULT_CHANNELS, RS4DSimulator
from simulators.wr1 import WR1Simulator

__all__ = [
    "DEFAULT_CHANNELS",
    "BacnetSimulator",
    "RS4DSimulator",
    "WR1Simulator",
]
