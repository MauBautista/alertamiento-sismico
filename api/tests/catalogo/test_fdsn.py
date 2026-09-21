"""T-7.25 · El cliente FDSN de USGS: lo que pregunta, lo que entiende y cómo calla.

Tres familias, por orden de lo que costaría equivocarse:

1. **Lo que se pregunta.** La ventana y el radio de la consulta salen del MISMO
   `Criterio` que después decide la identidad (`forensics/correlacion.py`,
   `T-5.11`). Si la consulta se acotara con números propios habría dos criterios
   y el segundo no estaría escrito en ninguna parte.
2. **Lo que se entiende.** El sobre GeoJSON trae las coordenadas en el orden
   `[lon, lat, prof]` y la hora en milisegundos; leerlos al revés no produce un
   error, produce un epicentro en otro hemisferio.
3. **Cómo calla.** Ningún fallo de red levanta una excepción cualquiera: todos
   salen como `SinRespuesta` **con motivo**, que es lo que se escribe en la base
   para poder decir `consultando` en vez de inventar.

Sin red: el transporte se inyecta con `httpx.MockTransport`, igual que en
`tests/narrative/test_openrouter.py`. `respx` no existe en este repositorio y no
se añade.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from takab_api.catalogo import fdsn
from takab_api.settings import Settings
from tests.catalogo.fixtures import (
    CRUDA_AUTOMATICA,
    CRUDA_TEHUANTEPEC,
    cruda,
    geojson,
    geojson_de,
)

DESDE = datetime(2023, 12, 7, 19, 55, 0, tzinfo=UTC)
HASTA = datetime(2023, 12, 7, 20, 10, 0, tzinfo=UTC)
CDMX = (19.43, -99.13)


def _settings(**over) -> Settings:
    return Settings(catalog_usgs_enabled=True, **over)


def _cliente(handler, **over) -> tuple[Settings, httpx.MockTransport]:
    return _settings(**over), httpx.MockTransport(handler)


def _pregunta(handler, **over) -> fdsn.Respuesta:
    s, t = _cliente(handler, **over)
    return fdsn.consulta(
        s, desde=DESDE, hasta=HASTA, lat=CDMX[0], lon=CDMX[1], radio_km=1200.0, transport=t
    )


def _responde(payload: dict, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(status, json=payload)

    return handler


# ---- lo que se pregunta ------------------------------------------------------


def test_la_consulta_lleva_la_ventana_y_el_radio_que_se_le_dan() -> None:
    visto: dict[str, list[str]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        visto.update(parse_qs(urlsplit(str(request.url)).query))
        return httpx.Response(200, json=geojson([]))

    _pregunta(handler)
    assert visto["format"] == ["geojson"]
    assert visto["starttime"] == ["2023-12-07T19:55:00Z"]
    assert visto["endtime"] == ["2023-12-07T20:10:00Z"]
    assert visto["latitude"] == ["19.43"]
    assert visto["longitude"] == ["-99.13"]
    assert visto["maxradiuskm"] == ["1200"]
    # Los dos que nadie miraba: borrar cada uno dejaba 43 pruebas en verde.
    # `limit` es la cota de la respuesta —de él sale el peor caso de bytes que
    # justifica `catalog_usgs_max_bytes`—, y `orderby=time` es lo que hace que
    # el recorte sea DETERMINISTA: si la fuente trunca en el límite, con otro
    # orden el evento que se queda fuera cambia entre dos consultas iguales.
    assert visto["limit"] == [str(Settings().catalog_usgs_limite)]
    assert visto["orderby"] == ["time"]


def test_la_url_devuelta_es_la_que_se_pidio_y_sirve_de_cita() -> None:
    """`reference_earthquakes.source_ref` es una CITA: tiene que poder repetirse."""
    r = _pregunta(_responde(geojson([])))
    assert r.url.startswith("https://earthquake.usgs.gov/fdsnws/event/1/query?")
    assert "maxradiuskm=1200" in r.url


def test_la_pregunta_ARCHIVADA_es_la_que_el_codigo_hace_hoy() -> None:
    """La respuesta cruda trae dentro la URL que la produjo (`metadata.url`).

    Es la guarda más barata y la más difícil de engañar: si alguien quita
    `limit`, cambia `orderby`, reordena los parámetros o toca el formato de las
    fechas, la pregunta que hace el código deja de ser la que archivamos, y
    entonces el fichero ya no prueba nada sobre lo que el sistema pregunta hoy.

    Los números de la ventana salen del evento archivado: origen
    2026-09-12T19:18:05.903Z, detección 20 s después, y a los dos lados el
    retraso máximo del criterio de `T-5.11` (363.33 s).
    """
    archivo = cruda(CRUDA_AUTOMATICA)
    (evento,) = archivo["features"]
    origen = datetime.fromtimestamp(evento["properties"]["time"] / 1000, tz=UTC)
    detectado = origen + timedelta(seconds=20)
    tope = timedelta(seconds=1200 / 3.6 + 30)
    url = fdsn.url_de_consulta(
        Settings().catalog_usgs_url,
        desde=detectado - tope,
        hasta=detectado + tope,
        lat=61.49,
        lon=-146.12,
        radio_km=1200.0,
        limite=Settings().catalog_usgs_limite,
    )
    assert url == archivo["metadata"]["url"]


def _bytes_por_evento() -> dict[pathlib.Path, float]:
    """Lo que pesa CADA respuesta cruda archivada, por evento. Medido, no dicho."""
    pesos = {}
    for ruta in (CRUDA_AUTOMATICA, CRUDA_TEHUANTEPEC):
        bruto = ruta.read_bytes()
        pesos[ruta] = len(bruto) / len(json.loads(bruto)["features"])
    return pesos


def test_el_tope_de_bytes_se_deriva_del_peor_caso_MEDIDO() -> None:
    """`catalog_usgs_max_bytes` contra lo que la fuente manda DE VERDAD.

    El comentario de `Settings` decía «~6 KB medido sobre una ventana global de
    diez minutos, once eventos», y esa cifra no se podía re-derivar del árbol:
    el fichero grabado está DESTILADO (es el nuestro, no el suyo), y aquella
    consulta global de veinticuatro horas no tiene la forma de la que este
    worker hace. Aquí la cifra sale de dos respuestas crudas archivadas, con su
    URL dentro, y se mide con el mismo aritmética que el comentario afirma.
    """
    por_evento = max(_bytes_por_evento().values())
    s = Settings()
    peor_caso = por_evento * s.catalog_usgs_limite
    assert 500 < por_evento < 1500, f"el peso por evento cambió: {por_evento:.0f} B"
    assert peor_caso < s.catalog_usgs_max_bytes, (
        "el tope no cubre la respuesta más pesada que esta consulta puede pedir"
    )
    # Y la holgura tampoco puede ser cualquiera: un tope diez veces mayor de lo
    # necesario deja de acotar lo que una respuesta desbocada le cuesta a la
    # memoria del worker, que es para lo único que existe.
    assert s.catalog_usgs_max_bytes < 5 * peor_caso


def test_el_COMENTARIO_de_la_cota_dice_las_mismas_cifras_que_esta_medicion() -> None:
    """⚠️ El comentario y el test que lo respalda hacían aritméticas DISTINTAS.

    El comentario de `catalog_usgs_max_bytes` afirmaba «~780 B por evento ⇒ ~156
    KB» —el promedio del fichero de Tehuantepec— y remitía al test de arriba,
    que toma `max(pesos)`: 1097 B por evento y 214 KB. Una cifra que el test que
    la cita no reproduce no es una medición, es una impresión; y ésta es la que
    justifica un tope de memoria del worker.

    Así que el comentario se LEE y se compara. No es exceso de celo: los dos
    números salen del mismo párrafo, y quien cambie una respuesta archivada ha
    de enterarse por los dos lados a la vez.
    """
    fuente = (pathlib.Path(__file__).resolve().parents[2] / "src/takab_api/settings.py").read_text(
        encoding="utf-8"
    )
    bloque = re.search(
        r"# Tope de la respuesta, DERIVADO(.*?)\n    catalog_usgs_max_bytes", fuente, re.S
    )
    assert bloque, "no se encontró el comentario de `catalog_usgs_max_bytes`"
    texto = bloque.group(1)

    pesos = _bytes_por_evento()
    s = Settings()
    # 1) El peso de cada fichero, con su número de eventos.
    for ruta, por_evento in pesos.items():
        assert f"{ruta.read_bytes().__len__()} B" in texto, (
            f"el comentario no cita los bytes medidos de {ruta.name}"
        )
        assert f"{round(por_evento)} B" in texto or f"({round(por_evento)} B cada uno)" in texto, (
            f"el comentario no cita los {round(por_evento)} B por evento de {ruta.name}"
        )
    # 2) La cota, con la MISMA aritmética del test de arriba: el peor caso.
    peor_kb = round(max(pesos.values()) * s.catalog_usgs_limite / 1024)
    assert f"{peor_kb} KB" in texto, (
        f"el comentario no dice los {peor_kb} KB que mide el peor caso; una cifra "
        "que el test que la respalda no reproduce no es una medición"
    )
    # 3) Y la holgura que se afirma sobre esa cota.
    holgura = s.catalog_usgs_max_bytes / (max(pesos.values()) * s.catalog_usgs_limite)
    assert f"{holgura:.1f}×" in texto, f"el comentario no dice la holgura medida ({holgura:.1f}×)"


# ---- lo que se entiende ------------------------------------------------------


def test_lee_el_sobre_CRUDO_tal_como_lo_da_el_servicio() -> None:
    """Contra el sobre de verdad, no contra nuestra reconstrucción de él.

    `fixtures.geojson()` vuelve a montar el sobre a partir de seis campos
    grabados, así que una prueba sobre él sólo demuestra que sabemos leer lo que
    nosotros mismos escribimos. Éste trae las 26 propiedades por evento que
    manda USGS, incluidas las que no miramos.
    """
    r = _pregunta(_responde(cruda(CRUDA_AUTOMATICA)))
    (evento,) = r.eventos
    assert evento.provider_event_id == "aka2026scqemw"
    assert evento.magnitude == pytest.approx(3.5)
    assert evento.mag_type == "ml"
    assert evento.lat == pytest.approx(61.29)
    assert evento.lon == pytest.approx(-146.12)
    assert evento.depth_km == pytest.approx(12.7)
    # Lo que este fichero existe para traer: un estado que NO es `reviewed`.
    assert evento.estado_en_la_fuente == "automatic"
    assert evento.review_status == fdsn.PRELIMINAR


def test_lee_los_once_eventos_de_la_respuesta_grabada() -> None:
    r = _pregunta(_responde(geojson_de("NUEVO-2023-12-07-HUEH")))
    assert len(r.eventos) == 11
    assert {e.provider_event_id for e in r.eventos} >= {"us7000lh50", "us7000lgwp"}


def test_el_epicentro_sale_de_geojson_en_el_orden_correcto() -> None:
    """`[lon, lat, prof]`. Invertirlo no da error: da otro hemisferio."""
    r = _pregunta(_responde(geojson_de("NUEVO-2023-12-07-HUEH")))
    huehuetlan = next(e for e in r.eventos if e.provider_event_id == "us7000lh50")
    assert huehuetlan.lat == pytest.approx(18.2702)
    assert huehuetlan.lon == pytest.approx(-98.7384)
    assert huehuetlan.depth_km == pytest.approx(54.0)
    assert huehuetlan.magnitude == pytest.approx(5.7)


def test_la_hora_de_origen_sale_de_los_milisegundos_en_utc() -> None:
    r = _pregunta(_responde(geojson_de("NUEVO-2023-12-07-HUEH")))
    huehuetlan = next(e for e in r.eventos if e.provider_event_id == "us7000lh50")
    assert huehuetlan.origin_time == datetime(2023, 12, 7, 20, 3, 38, 568000, tzinfo=UTC)


def test_reviewed_es_confirmado_y_lo_demas_es_preliminar() -> None:
    """La dirección de la duda: `confirmado` exige que la fuente lo diga con esa
    palabra. Todo lo demás —`automatic`, un estado que no conocemos, vacío— se
    cita como `preliminar`, que es la afirmación más débil («puede cambiar»).
    Al revés se prometería una revisión que nadie hizo."""
    assert fdsn.review_status("reviewed") == "confirmado"
    assert fdsn.review_status("automatic") == "preliminar"
    assert fdsn.review_status("") == "preliminar"
    assert fdsn.review_status("algo-que-usgs-invente-manana") == "preliminar"


def test_un_evento_sin_epicentro_se_descarta_sin_tumbar_la_respuesta() -> None:
    """No se puede verificar la identidad de lo que no tiene coordenadas, y una
    fila mala no puede costar las diez buenas."""
    payload = geojson_de("NUEVO-2023-12-07-HUEH")
    payload["features"][0]["geometry"] = None
    r = _pregunta(_responde(payload))
    assert len(r.eventos) == 10


def test_un_evento_sin_id_se_descarta() -> None:
    """Sin `provider_event_id` la fila no tiene identidad y el catálogo la
    duplicaría en la siguiente consulta."""
    payload = geojson_de("NUEVO-2023-12-07-HUEH")
    payload["features"][0]["id"] = ""
    r = _pregunta(_responde(payload))
    assert len(r.eventos) == 10


# ---- cómo calla --------------------------------------------------------------


def test_un_5xx_es_sin_respuesta_con_motivo() -> None:
    with pytest.raises(fdsn.SinRespuesta) as e:
        _pregunta(_responde({}, status=503))
    assert "503" in e.value.motivo


def test_un_corte_de_red_es_sin_respuesta_con_motivo() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Name or service not known", request=request)

    with pytest.raises(fdsn.SinRespuesta) as e:
        _pregunta(handler)
    assert "ConnectError" in e.value.motivo


def test_un_timeout_es_sin_respuesta_con_motivo() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("se acabó el tiempo", request=request)

    with pytest.raises(fdsn.SinRespuesta) as e:
        _pregunta(handler)
    assert "ReadTimeout" in e.value.motivo


def test_un_cuerpo_ilegible_es_sin_respuesta_y_no_media_respuesta() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(200, content=b"<html>mantenimiento</html>")

    with pytest.raises(fdsn.SinRespuesta):
        _pregunta(handler)


def test_un_cuerpo_gigante_se_corta_MIENTRAS_se_lee() -> None:
    """Y se mide que se corta **mientras**, que es lo único que el tope promete.

    ⚠️ La primera versión de esta prueba era CIEGA a eso: mandaba un cuerpo
    entero de 5 KB y sólo comprobaba que saliera `SinRespuesta`. Sacar el corte
    del bucle y ponerlo detrás —que es exactamente el defecto que el tope existe
    para no tener— la dejaba en verde: el cuerpo ya estaba en memoria, que es el
    precio que no se quería pagar. Medido.

    Lo que sí lo demuestra es contar los trozos que el lector llegó a pedir. El
    cuerpo se sirve como un generador de cincuenta trozos de 1 KB; con el tope
    en 1 KB, un lector que corte mientras lee pide dos y se va.
    """
    pedidos: list[int] = []

    def cuerpo():  # noqa: ANN202
        for i in range(50):
            pedidos.append(i)
            yield b"x" * 1024

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(200, content=cuerpo())

    with pytest.raises(fdsn.SinRespuesta) as e:
        _pregunta(handler, catalog_usgs_max_bytes=1024)
    assert "tope" in e.value.motivo.lower() or "bytes" in e.value.motivo.lower()
    assert len(pedidos) <= 3, (
        f"se leyeron {len(pedidos)} trozos de los 50: el tope no cortó mientras "
        "se leía, sino después — y para entonces ya se había pagado la memoria"
    )


def test_sin_cliente_HTTP_instalado_tambien_es_sin_respuesta() -> None:
    """Propiedad 1 de la cabecera: de aquí NO sale una excepción cualquiera.

    `import httpx` estaba FUERA del `try`, así que en una imagen sin el cliente
    —una recortada, un `uv sync` que podó el extra: este repositorio ya se comió
    esa— el `ImportError` subía tal cual hasta el bucle del worker, que es el
    que mueve fases, dictámenes y cierres. Y el motivo dice lo que pasa de
    verdad: falta el cliente, no «la fuente no respondió».
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "httpx", None)
        with pytest.raises(fdsn.SinRespuesta) as e:
            _pregunta(_responde(geojson([])))
    assert "httpx" in e.value.motivo


def test_apagado_no_se_puede_consultar() -> None:
    """El cliente no decide si se enciende, pero tampoco se deja usar apagado:
    quien lo llame con la bandera en `False` se lleva un error, no una respuesta
    vacía que se confundiría con «la fuente no tiene nada»."""
    with pytest.raises(fdsn.SinRespuesta):
        fdsn.consulta(
            Settings(),
            desde=DESDE,
            hasta=HASTA,
            lat=CDMX[0],
            lon=CDMX[1],
            radio_km=1200.0,
            transport=httpx.MockTransport(_responde(geojson([]))),
        )


def test_una_fuente_que_GOTEA_no_secuestra_el_bucle_del_worker() -> None:
    """El timeout de `httpx` es POR OPERACIÓN, y eso deja un agujero.

    Cada trozo que llega reinicia el de lectura, así que una fuente que mande
    poquito y a menudo no lo dispara nunca: el worker se queda leyendo, y con él
    el bucle que mueve fases, dictámenes y la actuación comandada por el quórum.
    Es peor que el tope de dos minutos que esta revisión vino a quitar, porque
    no tiene fin. El plazo de la llamada entera lo corta.

    Se mide con reloj de pared: 200 trozos a 0.05 s serían diez segundos; con el
    plazo en 0.2 s no llega ni al medio.
    """

    def cuerpo():  # noqa: ANN202
        for _ in range(200):
            time.sleep(0.05)
            yield b"x"

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(200, content=cuerpo())

    arranque = time.monotonic()
    with pytest.raises(fdsn.SinRespuesta) as e:
        _pregunta(handler, catalog_usgs_timeout_s=0.2)
    gastado = time.monotonic() - arranque
    # La medición primero: es lo que se está acotando.
    assert gastado < 1.0, f"la fuente tuvo al worker leyendo {gastado:.2f} s con un plazo de 0.2 s"
    assert "tardó más" in e.value.motivo
