"""T-2.60.a · La métrica que delata al gabinete retirado que sigue latiendo.

La consola ya lo pinta arriba y en rojo (PR #51), pero eso solo funciona si
alguien está mirando la pantalla. El fallo del 2026-08-04 duró horas justamente
porque nadie miraba: se supo cuando el operador preguntó por su estación.

Esta métrica es la mitad que no depende de que haya un humano delante.

Lo que estos tests fijan, y por qué cada uno existe:

1. **Se publica SIEMPRE, también el cero.** Es la lección de la alarma de
   gabinete mudo: si la métrica solo aparece cuando hay algo que contar, la
   alarma vive en INSUFFICIENT_DATA y todo depende de `treat_missing_data`, que
   ya nos falló de cuatro maneras distintas. Con un 0 cada minuto, "sin datos"
   pasa a significar UNA sola cosa —el worker está caído—, que es un problema
   distinto y ya vigilado.
2. **Nunca puede tumbar al worker.** `notify` existe para avisar de incidentes
   sísmicos. Una métrica de operación que reventase su bucle cambiaría un
   problema de inventario por uno de alertamiento; el trueque es inaceptable.
3. **Estrangulada.** El bucle de notify despierta cada 2 s. Publicar ahí sería
   ~43 000 llamadas al día por una cifra que CloudWatch agrega por minuto.
"""

from __future__ import annotations

import logging

import pytest

from takab_api.ops.metrics import GhostGauge


class _FakeClock:
    """Reloj de mentira: el estrangulamiento se mide, no se espera dormido."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def avanza(self, s: float) -> None:
        self.t += s


class _FakeCW:
    def __init__(self, *, revienta: bool = False) -> None:
        self.puestas: list[dict] = []
        self._revienta = revienta

    def put_metric_data(self, **kw: object) -> None:
        if self._revienta:
            raise RuntimeError("CloudWatch dice que no")
        self.puestas.append(kw)


def _gauge(cw: _FakeCW, clock: _FakeClock, *, cuenta: int = 0, every_s: float = 60.0) -> GhostGauge:
    return GhostGauge(
        namespace="Takab/Test",
        every_s=every_s,
        client=cw,
        clock=clock,
        counter=lambda _conn: cuenta,
    )


def test_publica_el_CERO_para_que_la_alarma_no_viva_en_sin_datos() -> None:
    cw, clock = _FakeCW(), _FakeClock()
    _gauge(cw, clock, cuenta=0).maybe_publish(conn=object())

    assert len(cw.puestas) == 1, "no publicó nada con cero fantasmas"
    dato = cw.puestas[0]["MetricData"][0]
    assert dato["Value"] == 0
    assert dato["MetricName"] == "GhostGatewaysAlive"
    assert dato["Unit"] == "Count"


def test_publica_la_cuenta_real() -> None:
    cw, clock = _FakeCW(), _FakeClock()
    _gauge(cw, clock, cuenta=3).maybe_publish(conn=object())
    assert cw.puestas[0]["MetricData"][0]["Value"] == 3


def test_estrangula_no_publica_en_cada_vuelta_del_bucle() -> None:
    cw, clock = _FakeCW(), _FakeClock()
    g = _gauge(cw, clock, cuenta=1, every_s=60.0)

    g.maybe_publish(conn=object())  # primera: publica
    # 29 vueltas de 2 s = 58 s. Se queda DEBAJO del intervalo a propósito: a los
    # 60 s exactos volver a publicar es la cadencia correcta, no una fuga (eso lo
    # cubre `test_pasado_el_intervalo_vuelve_a_publicar`). Aquí se mide lo otro:
    # que las vueltas intermedias del bucle no publiquen.
    for _ in range(29):
        clock.avanza(2.0)
        g.maybe_publish(conn=object())

    assert len(cw.puestas) == 1, (
        f"publicó {len(cw.puestas)} veces en 58 s con 30 vueltas de bucle: el "
        "estrangulador no está reteniendo, y a 2 s por vuelta esto serían "
        "~43 000 llamadas al día por una cifra que CloudWatch agrega por minuto"
    )


def test_pasado_el_intervalo_vuelve_a_publicar() -> None:
    cw, clock = _FakeCW(), _FakeClock()
    g = _gauge(cw, clock, cuenta=1, every_s=60.0)
    g.maybe_publish(conn=object())
    clock.avanza(61.0)
    g.maybe_publish(conn=object())
    assert len(cw.puestas) == 2


def test_un_fallo_de_cloudwatch_NO_tumba_al_worker(caplog: pytest.LogCaptureFixture) -> None:
    """`notify` avisa de sismos. Una métrica de ops no puede llevárselo por delante."""
    cw, clock = _FakeCW(revienta=True), _FakeClock()
    g = _gauge(cw, clock, cuenta=1)

    with caplog.at_level(logging.WARNING):
        g.maybe_publish(conn=object())  # no debe propagar

    assert any("fantasma" in r.message.lower() for r in caplog.records), (
        "se tragó el fallo SIN dejar rastro: un error silencioso aquí es peor "
        "que el propio fallo, porque la alarma parece sana y no lo está"
    )


def test_un_fallo_de_la_consulta_TAMPOCO_lo_tumba() -> None:
    cw, clock = _FakeCW(), _FakeClock()

    def _explota(_conn: object) -> int:
        raise RuntimeError("la DB dice que no")

    g = GhostGauge(
        namespace="Takab/Test",
        every_s=60.0,
        client=cw,
        clock=clock,
        counter=_explota,
    )
    g.maybe_publish(conn=object())  # no propaga
    assert cw.puestas == [], "publicó un valor inventado tras fallar la consulta"


def test_sin_cliente_no_hace_nada_y_no_revienta() -> None:
    """En local no hay CloudWatch: el worker tiene que correr igual."""
    clock = _FakeClock()
    g = GhostGauge(
        namespace="Takab/Test", every_s=60.0, client=None, clock=clock, counter=lambda _c: 5
    )
    g.maybe_publish(conn=object())  # y ya está: sin excepción


def test_el_fallo_de_una_vuelta_no_bloquea_la_siguiente() -> None:
    """Tras un error, el estrangulador no puede quedarse trabado para siempre."""
    cw, clock = _FakeCW(revienta=True), _FakeClock()
    g = _gauge(cw, clock, cuenta=1, every_s=60.0)
    g.maybe_publish(conn=object())
    clock.avanza(61.0)
    cw._revienta = False
    g.maybe_publish(conn=object())
    assert len(cw.puestas) == 1, "el estrangulador se quedó trabado tras el fallo"


# ---- el enganche al bucle de notify ----------------------------------------


def test_el_worker_arranca_INERTE_sin_la_metrica_habilitada() -> None:
    """Por defecto no se habla con AWS: en local no hay CloudWatch."""
    from takab_api.notify.worker import build_ghost_gauge
    from takab_api.settings import Settings

    gauge = build_ghost_gauge(Settings())
    gauge.maybe_publish(conn=object())  # no revienta, no publica, no pide credenciales


def test_la_metrica_NO_puede_tumbar_el_aviso_de_un_sismo(monkeypatch) -> None:
    """El contrato que de verdad importa de este enganche.

    `notify` existe para avisar de incidentes sísmicos. Si un fallo publicando
    una métrica de inventario propagara, cambiaríamos un problema administrativo
    por uno de alertamiento. Aquí se comprueba en el BUCLE real, no en la clase.
    """
    from takab_api.notify.worker import NotifyWorker
    from takab_api.settings import Settings

    pases: list[int] = []

    class _GaugeQueRevienta:
        def maybe_publish(self, *, conn: object) -> None:
            raise RuntimeError("CloudWatch caído")

    class _Conn:
        closed = False

        def execute(self, *_a: object, **_k: object) -> _Conn:
            return self

        def fetchone(self) -> tuple:
            return (0,)

        def fetchall(self) -> list:
            return []

        def rollback(self) -> None: ...
        def close(self) -> None: ...
        def notifies(self, **_k: object) -> list:
            return []

    worker = NotifyWorker(
        lambda: _Conn(),  # type: ignore[arg-type,return-value]
        Settings(),
        poll_s=0.0,
        providers={},
        ghost_gauge=_GaugeQueRevienta(),  # type: ignore[arg-type]
    )

    def _pass(*_a: object, **_k: object) -> None:
        pases.append(1)
        if len(pases) >= 3:
            worker.stop()

    monkeypatch.setattr("takab_api.notify.worker.run_notify_pass", _pass)
    worker.run()  # no debe propagar el fallo del gauge

    assert len(pases) >= 3, (
        f"el bucle solo dio {len(pases)} pases: un fallo de la métrica de "
        "inventario está frenando el despacho de notificaciones de sismo"
    )
