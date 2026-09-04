"""El aislamiento de la demo se IMPONE, y aquí se comprueba que no se puede saltar.

Antes de `T-5.08` la demo no despertaba a nadie porque **el guion no lanzaba el
worker de notificación**. Eso no es aislamiento: es una coincidencia de arranque.
Un `make soc-local` a medio apagar —que sí levanta el worker— habría bastado para
que la cascada saliera por los canales configurados hacia teléfonos reales, y no
había nada que lo impidiera ni nada que lo dijera.

Estos tests fijan las tres piezas que lo convierten en un estado del sistema:
encenderlo, **verificar** que quedó vivo, y **contar** al final lo que salió.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from demo import aislamiento  # noqa: E402


@dataclass
class _Cur:
    filas: list[tuple]

    def fetchone(self) -> tuple | None:
        return self.filas[0] if self.filas else None

    def fetchall(self) -> list[tuple]:
        return self.filas


class _Conn:
    """Conexión de mentira: registra lo que se le pide y devuelve un guion."""

    def __init__(self, respuestas: list[list[tuple]]) -> None:
        self._respuestas = respuestas
        self.consultas: list[str] = []

    def execute(self, sql: str, params: object = None) -> _Cur:  # noqa: ARG002
        self.consultas.append(" ".join(sql.split()))
        return _Cur(self._respuestas.pop(0) if self._respuestas else [])


def test_sin_el_cliente_de_la_demo_NO_arranca() -> None:
    """Un tenant que no existe no puede tener modo demostración, y entonces la
    demo correría con la cascada viva. Se para antes, y dice por qué."""
    conn = _Conn([[]])
    with pytest.raises(RuntimeError, match="no existe en la DB"):
        aislamiento.imponer(conn, tenant_code="no-existe")  # type: ignore[arg-type]


def test_si_la_ventana_NO_queda_viva_la_demo_se_niega(monkeypatch: pytest.MonkeyPatch) -> None:
    """La verificación es la pieza que impide volver a suponer.

    Encender y no comprobar habría dejado el mismo agujero con otra forma: un
    `INSERT` que falla en silencio —o un reloj movido— y la demo arrancaría
    creyéndose aislada. Aquí se simula justo eso: el encendido «ocurre» y la
    ventana sale muerta.
    """
    conn = _Conn([[("d0000000-0000-0000-0000-000000000001",)]])
    monkeypatch.setattr(aislamiento, "asyncio", type("A", (), {"run": staticmethod(lambda c: c.close())})())
    monkeypatch.setattr(aislamiento, "ventana_viva_sync", lambda *a, **k: None)

    with pytest.raises(RuntimeError, match="MODO DEMOSTRACIÓN"):
        aislamiento.imponer(conn, tenant_code="tenant-dev")  # type: ignore[arg-type]


def test_la_ventana_pedida_cabe_en_el_tope_de_la_BASE() -> None:
    """El CHECK de `demo_mode` acota la ventana a 8 h. Pedir más no es «una demo
    larga»: es un cliente sin avisos, y el INSERT lo rechazaría en mitad del guion."""
    assert 0 < aislamiento.VENTANA_S <= 8 * 3600


def test_solo_cuenta_como_entrega_lo_que_de_verdad_SALIO() -> None:
    """`sent` y nada más.

    `simulated` es lo que produce un canal sin credenciales, así que contarlo como
    entrega haría que la comprobación pasara en verde por la razón equivocada — y
    desaparecería justo en el entorno donde se hace la demostración, que es donde
    los canales SÍ tienen credenciales.
    """
    conn = _Conn([[("sms", 2)]])
    salidas = aislamiento.entregas_reales(conn)  # type: ignore[arg-type]

    assert salidas == [("sms", 2)]
    sql = conn.consultas[0]
    assert "status = 'sent'" in sql, f"la consulta no filtra por entrega real: {sql}"
    assert "simulated" not in sql


def test_el_actor_del_modo_es_un_UUID() -> None:
    """`demo_mode.enabled_by` es una columna uuid: un `"demo:run.py"` revienta el
    INSERT en mitad del guion (pasó al escribirlo). Y el mismo valor viaja al
    `actor` de la auditoría, donde tiene que poder leerse como «no fue una persona».
    """
    import uuid

    assert uuid.UUID(aislamiento._ACTOR)
