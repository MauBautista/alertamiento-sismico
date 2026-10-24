"""[T-2.172] El fail-open del modo prueba dice lo que pasa, y lo dice una vez.

Medido en el despliegue con `--ventana-de-mantenimiento` del 2026-08-30: mientras
`takab-gpio` se reinicia, unos 3 s, `snapshot()` lanza y `_modo_prueba_activo`
falla abierto. Se registró **24 veces** en `ERROR`, cada una con un `event_id`
distinto, diciendo que «se PUBLICA a la nube» y que podía disparar la push CRISIS.
No publicó nada: el gabinete estaba en reposo, todas las decisiones eran `NORMAL`
y el `LocalEvent` sólo sale con un tier de alerta. Cero incidentes en la nube.

Un aviso que describe el peor caso como si fuera lo ocurrido, veinticuatro veces,
justo cuando alguien mira el journal, enseña a ignorarlo. El día que el fail-open
publique de verdad, esas líneas parecerían «las de siempre».

Lo que NO se arregla aquí, y por qué: el fail-open es correcto (callar un sismo
real es peor que un incidente de más) y tiene que verse, así que el aviso sigue
en `ERROR`. Lo que cambia es que dice la verdad, una vez por ventana, y que cada
alerta publicada a ciegas sí tiene su propia línea.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime

import pytest
from simulators.rs4d import RS4DSimulator
from takab_edge.contracts import AlertSource, Tier, TierDecision
from takab_edge.gpio_link import GpioLinkUnavailable
from takab_edge.supervisor import ACKS_TOPIC, EVENTS_TOPIC

_LOGGER = "takab_edge.supervisor"


class _CosturaDelDueno:
    """La costura del gabinete, con el dueño de los pines que se cae a voluntad.

    Sólo rompe `snapshot()`, que es lo que lee el modo prueba. Las órdenes de
    relé pasan a la costura real.
    """

    def __init__(self, real) -> None:  # noqa: ANN001
        self._real = real
        self.caido = False
        self.lecturas = 0

    def snapshot(self):  # noqa: ANN201
        self.lecturas += 1
        if self.caido:
            raise GpioLinkUnavailable("el dueño de los pines no contesta")
        return self._real.snapshot()

    def __getattr__(self, name: str):  # noqa: ANN204
        return getattr(self._real, name)


@pytest.fixture
def gabinete(supervisor, caplog):  # noqa: ANN001, ANN201
    """El supervisor con la costura rompible y la nube espiada."""
    costura = _CosturaDelDueno(supervisor.gpio_link)
    supervisor.gpio_link = costura
    publicados: list[tuple[str, object]] = []
    supervisor.cloud.publish = lambda topic, payload: publicados.append((topic, payload))
    caplog.set_level(logging.INFO, logger=_LOGGER)
    caplog.clear()
    supervisor.costura = costura
    supervisor.publicados = publicados
    return supervisor


def _normal() -> TierDecision:
    # Un `event_id` nuevo en cada una, como hace el motor con `NORMAL`: por eso
    # las 24 líneas del 2026-08-30 llevaban 24 ids distintos.
    return TierDecision(tier=Tier.NORMAL, source=AlertSource.THRESHOLD)


def _alerta(
    tier: Tier, event_id: str = "EV-VENTANA", source: AlertSource = AlertSource.THRESHOLD
) -> TierDecision:
    return TierDecision(event_id=event_id, tier=tier, source=source)


def _del_modo_prueba(caplog) -> list[logging.LogRecord]:  # noqa: ANN001
    return [r for r in caplog.records if r.name == _LOGGER and "modo prueba" in r.getMessage()]


def _avisos(caplog) -> list[logging.LogRecord]:  # noqa: ANN001
    return [r for r in _del_modo_prueba(caplog) if r.levelno >= logging.WARNING]


def _a_la_nube(gabinete) -> list[tuple[str, object]]:  # noqa: ANN001
    return [(t, p) for t, p in gabinete.publicados if t in (EVENTS_TOPIC, ACKS_TOPIC)]


# ---------------------------------------------------------------------------
# La ventana de mantenimiento en reposo: la medida del 2026-08-30
# ---------------------------------------------------------------------------


def test_la_ventana_en_reposo_deja_UNA_linea_y_no_publica_nada(gabinete, caplog) -> None:  # noqa: ANN001
    gabinete.costura.caido = True
    for _ in range(24):
        gabinete._act_and_publish(_normal(), None)

    assert _a_la_nube(gabinete) == [], "en reposo el fail-open no tiene nada que publicar"
    avisos = _avisos(caplog)
    assert len(avisos) == 1, f"la ventana dejó {len(avisos)} líneas de aviso, no una"
    texto = avisos[0].getMessage()
    assert "NO se publica ninguna alerta" in texto, f"el aviso no dice lo que pasa: {texto}"
    assert "se PUBLICA a la nube" not in texto, "describe el peor caso como si fuera lo ocurrido"
    # La corrección prohibida por la ficha: bajarle el nivel. Sigue siendo un
    # fail-open armado, y tiene que verse.
    assert avisos[0].levelno == logging.ERROR
    assert avisos[0].exc_info is not None, "sin traza no hay forma de saber por qué no contestó"


def test_al_volver_el_dueno_una_linea_con_el_conteo(gabinete, caplog) -> None:  # noqa: ANN001
    gabinete.costura.caido = True
    for _ in range(24):
        gabinete._act_and_publish(_normal(), None)
    caplog.clear()

    gabinete.costura.caido = False
    gabinete._act_and_publish(_normal(), None)
    gabinete._act_and_publish(_normal(), None)

    lineas = _del_modo_prueba(caplog)
    assert len(lineas) == 1, f"la vuelta dejó {len(lineas)} líneas: {lineas}"
    texto = lineas[0].getMessage()
    assert "24 lecturas" in texto, f"la línea de salida no da el conteo: {texto}"
    # Nada salió a ciegas: la salida de una ventana rutinaria no es un aviso.
    assert lineas[0].levelno == logging.INFO
    assert "ninguna" in texto


def test_cada_ventana_tiene_su_propia_entrada(gabinete, caplog) -> None:  # noqa: ANN001
    for _ventana in range(2):
        gabinete.costura.caido = True
        for _ in range(5):
            gabinete._act_and_publish(_normal(), None)
        gabinete.costura.caido = False
        gabinete._act_and_publish(_normal(), None)

    entradas = _avisos(caplog)
    salidas = [r for r in _del_modo_prueba(caplog) if r.levelno == logging.INFO]
    assert len(entradas) == 2 and len(salidas) == 2
    assert [("5 lecturas" in r.getMessage()) for r in salidas] == [True, True], (
        "la segunda ventana arrastró el conteo de la primera"
    )
    # El número casa la entrada con su salida: con dos hilos, el orden de las
    # líneas en el journal no basta para saber qué cierra a qué.
    for n, (entrada, salida) in enumerate(zip(entradas, salidas, strict=True), start=1):
        assert f"ventana #{n}" in entrada.getMessage()
        assert f"ventana #{n}" in salida.getMessage()


# ---------------------------------------------------------------------------
# Una alerta dentro de la ventana: el fail-open de verdad
# ---------------------------------------------------------------------------


def test_una_alerta_en_la_ventana_SE_PUBLICA_y_tiene_su_linea(gabinete, caplog) -> None:  # noqa: ANN001
    """El caso por el que existe el fail-open. No puede quedar escondido en el
    conteo de una ventana rutinaria."""
    gabinete.costura.caido = True
    for _ in range(5):
        gabinete._act_and_publish(_normal(), None)
    for _ in range(3):
        gabinete._act_and_publish(_alerta(Tier.WATCH), None)
    for _ in range(2):
        gabinete._act_and_publish(_alerta(Tier.RESTRICTED), None)

    eventos = [p for t, p in gabinete.publicados if t == EVENTS_TOPIC and hasattr(p, "tier")]
    publicados = {(e.event_id, e.tier) for e in eventos if type(e).__name__ == "LocalEvent"}
    assert publicados == {("EV-VENTANA", Tier.WATCH), ("EV-VENTANA", Tier.RESTRICTED)}, (
        "falló CERRADO: la nube se quedó sin el evento por no poder leer el modo prueba"
    )

    avisos = _avisos(caplog)
    # La entrada de la ventana, y una por cada (evento, tier, fuente) publicado a
    # ciegas: la nube deduplica así, y repetirla no avisa de nada nuevo.
    assert len(avisos) == 3, [a.getMessage() for a in avisos]
    for aviso, tier in zip(avisos[1:], ("watch", "restricted"), strict=True):
        texto = aviso.getMessage()
        assert aviso.levelno == logging.ERROR
        assert "se PUBLICA a la nube" in texto
        assert "EV-VENTANA" in texto and f"tier={tier}" in texto
        assert "fuente=local_threshold" in texto
        assert "CRISIS" in texto, "el aviso tiene que decir lo que puede costar"


def test_un_SASMEX_detras_de_un_umbral_del_mismo_episodio_tiene_su_linea(
    gabinete,  # noqa: ANN001
    caplog,  # noqa: ANN001
) -> None:
    """Mismo `event_id` (un episodio) y mismo tier, pero otra fuente. Para la nube
    es otra publicación (T-9.02): es la que sube el disparo a SASMEX y ordena
    evacuar. Si salió a ciegas, no puede quedar escondida detrás de la del umbral."""
    gabinete.costura.caido = True
    gabinete._act_and_publish(_alerta(Tier.EVACUATE_OR_HOLD), None)
    gabinete._act_and_publish(_alerta(Tier.EVACUATE_OR_HOLD, source=AlertSource.SASMEX), None)

    eventos = [p for t, p in gabinete.publicados if t == EVENTS_TOPIC]
    fuentes = {e.source for e in eventos if type(e).__name__ == "LocalEvent"}
    assert fuentes == {AlertSource.THRESHOLD, AlertSource.SASMEX}, "premisa: salieron las dos"
    avisos = [a.getMessage() for a in _avisos(caplog)]
    assert len(avisos) == 2, avisos
    assert "fuente=local_threshold" in avisos[0] and "fuente=sasmex" in avisos[1]

    gabinete.costura.caido = False
    gabinete._act_and_publish(_normal(), None)
    salida = _del_modo_prueba(caplog)[-1].getMessage()
    assert "fuente=local_threshold" in salida and "fuente=sasmex" in salida


def test_manual_only_tambien_sale_a_ciegas_y_se_dice(gabinete, caplog) -> None:  # noqa: ANN001
    """`MANUAL_ONLY` no es `NORMAL`: publica su `LocalEvent`, y por tanto avisa."""
    gabinete.costura.caido = True
    gabinete._act_and_publish(_alerta(Tier.MANUAL_ONLY), None)

    eventos = [p for t, p in gabinete.publicados if t == EVENTS_TOPIC]
    assert any(type(e).__name__ == "LocalEvent" for e in eventos), "premisa: sí publica"
    avisos = [a.getMessage() for a in _avisos(caplog)]
    assert len(avisos) == 1 and "se PUBLICA a la nube" in avisos[0], avisos


def test_si_lo_primero_que_llega_es_una_alerta_basta_una_linea(gabinete, caplog) -> None:  # noqa: ANN001
    gabinete.costura.caido = True
    gabinete._act_and_publish(_alerta(Tier.RESTRICTED), None)

    avisos = _avisos(caplog)
    assert len(avisos) == 1, [a.getMessage() for a in avisos]
    texto = avisos[0].getMessage()
    assert "se PUBLICA a la nube" in texto and "EV-VENTANA" in texto
    assert "NO se publica ninguna alerta" not in texto
    assert avisos[0].exc_info is not None


def test_la_salida_de_una_ventana_con_alertas_enumera_lo_publicado(gabinete, caplog) -> None:  # noqa: ANN001
    gabinete.costura.caido = True
    gabinete._act_and_publish(_normal(), None)
    gabinete._act_and_publish(_alerta(Tier.RESTRICTED), None)
    caplog.clear()

    gabinete.costura.caido = False
    gabinete._act_and_publish(_normal(), None)

    lineas = _del_modo_prueba(caplog)
    assert len(lineas) == 1
    assert lineas[0].levelno == logging.WARNING, "salió algo a ciegas: no es una vuelta rutinaria"
    assert "EV-VENTANA" in lineas[0].getMessage()


# ---------------------------------------------------------------------------
# Lo que no se puede tocar para conseguirlo
# ---------------------------------------------------------------------------


def test_no_espera_al_dueno(gabinete) -> None:  # noqa: ANN001
    """El fail-open existe para no bloquear: esta lectura corre en el hilo de
    SeedLink, y la actuación no puede quedarse esperando a que vuelva el dueño."""
    gabinete.costura.caido = True
    antes = gabinete.costura.lecturas
    t0 = time.monotonic()
    assert gabinete._modo_prueba_activo(_normal()) is False
    assert time.monotonic() - t0 < 0.5, "la lectura del modo prueba se quedó esperando"
    assert gabinete.costura.lecturas == antes + 1, "reintentó en vez de fallar abierto"


def test_dos_hilos_a_la_vez_siguen_dejando_una_entrada(gabinete, caplog, monkeypatch) -> None:  # noqa: ANN001
    """El hilo de SeedLink y el observador del WR-1 llegan aquí por separado.

    Con el GIL la carrera casi nunca se ve sola, así que se fuerza: el primer
    hilo se queda parado DENTRO de la apertura de la ventana (en su `mono()`)
    mientras entra el segundo. Sin el lock, los dos la abren y salen dos líneas.
    """
    import takab_edge.supervisor as sup

    dentro = threading.Event()
    llamadas: list[float] = []
    real = sup.mono

    def mono_lento() -> float:
        llamadas.append(0.0)
        if len(llamadas) == 1:
            dentro.set()
            time.sleep(0.3)  # el segundo hilo entra mientras éste sigue abriendo
        return real()

    monkeypatch.setattr(sup, "mono", mono_lento)
    gabinete.costura.caido = True
    primero = threading.Thread(target=gabinete._modo_prueba_activo, args=(_normal(),))
    primero.start()
    assert dentro.wait(timeout=5), "premisa: el primer hilo no llegó a abrir la ventana"
    segundo = threading.Thread(target=gabinete._modo_prueba_activo, args=(_normal(),))
    segundo.start()
    primero.join(timeout=5)
    segundo.join(timeout=5)

    assert len(_avisos(caplog)) == 1, [a.getMessage() for a in _avisos(caplog)]
    monkeypatch.setattr(sup, "mono", real)
    gabinete.costura.caido = False
    gabinete._modo_prueba_activo(_normal())
    assert "2 lecturas" in _del_modo_prueba(caplog)[-1].getMessage()


def test_por_la_cadena_exacta_del_hilo_de_seedlink(gabinete, caplog) -> None:  # noqa: ANN001
    """La medida del gabinete, por donde llegó: paquetes del Shake en reposo.

    Con ruido de fondo y no con ceros: un canal plano no es reposo, es un
    sensor mudo, y el motor lo saca de `NORMAL`.
    """
    sim = RS4DSimulator(station=gabinete.settings.station)
    antes = gabinete.seedlink.reconnects
    gabinete.costura.caido = True
    for paquete in sim.stream("EHZ", start=datetime.now(UTC), seconds=24):
        gabinete.seedlink.feed(paquete)

    assert gabinete.rules.last_decision.tier is Tier.NORMAL, "premisa: el gabinete en reposo"
    assert gabinete.seedlink.reconnects == antes, "se disfrazó de desconexión de SeedLink"
    assert _a_la_nube(gabinete) == []
    assert len(_avisos(caplog)) == 1
