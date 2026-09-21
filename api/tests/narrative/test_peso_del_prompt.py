"""T-7.27 · Cuánto pesa la petición cuando lleva seis fotografías, MEDIDO.

La pregunta no se contesta con una opinión: un prompt que no cabe falla exactamente en
el incidente más cargado —seis fotos, red entera, cronología larga—, que es el que
importa y el que nadie tiene delante mientras desarrolla.

**MEDIDO** con `pytest -s` sobre el caso de abajo —seis fotografías densas de 768×1024
tapadas, la red entera, la cronología y un reporte de daños—, el 2026-09-21, después de
`T-7.27·A`:

| pieza                                   | bytes       |
|-----------------------------------------|-------------|
| prompt de sistema                       |       2 187 |
| petición entera SIN fotos               |       5 699 |
| cada fotografía (JPEG tapado, antes de base64) |  78 313 |
| **petición entera con 6 fotos**         | **633 683** (0.60 MiB) |
| tope declarado (`TOPE_PETICION_BYTES`)  |   1 294 336 (1.23 MiB) |

⚠️ **El «peor caso» de la versión anterior de esta cabecera NO era el peor caso**, y hay
que decirlo porque la conclusión que sacaba —«cabe por construcción y no por suerte»— era
más fuerte que la medición. Daba por FIJO el bloque de texto en los 5 699 B medidos sobre
un incidente con DOS estaciones y UNA acción; ni la red ni `incident_actions` —append-only
y exenta de poda por la regla de oro 11— tienen cota, así que el texto puede crecer sin
techo. Medido abajo (`test_el_TEXTO_puede_rebasar_el_margen_...`): con 50 estaciones y
500 acciones el bloque de texto pasa de los 64 KiB de margen.

Lo que cambia con `T-7.27·A` es que **el tope dejó de ser una cota declarada que nadie
leía**. Se comprueba antes de emitir, y un incidente que no cabe se degrada al
determinista con su razón impresa (`MOTIVO_PETICION_ENORME`) en vez de mandar un cuerpo
que el proveedor va a rechazar con un estado que no explica nada.

Y las fotografías sí caben por construcción: cada una viaja con el techo de
`marca.tapar_banda_forense` (`min(peso de la impresa, MAX_BYTES_SALIDA)`) y son seis como
mucho, o sea `PRESUPUESTO_FOTOS_BYTES` exactos en el peor caso.

⚠️ Lo que este fichero **no** puede decir: si OpenRouter acepta ese cuerpo. Eso exige la
clave real y salir a la red (`GATE-AWS`). Lo que sí se puede afirmar es que el cuerpo
está acotado, por cuánto, y qué pasa cuando no lo está.
"""

from __future__ import annotations

import json

import httpx

from takab_api.dictamen.model import ActionRow, EstacionFila
from takab_api.narrative.base import MOTIVO_PETICION_ENORME, NarrativeRequest
from takab_api.narrative.openrouter import (
    MARGEN_TEXTO_BYTES,
    TOPE_PETICION_BYTES,
    OpenRouterProvider,
    cuerpo_de,
)
from takab_api.narrative.redact import (
    MAX_FOTOS_IA,
    PRESUPUESTO_FOTOS_BYTES,
    facts_from,
    imagenes_de,
)
from takab_api.settings import Settings
from tests.dictamen.test_pdf import model
from tests.narrative.test_lo_que_ve_la_ia import _dano, _foto_cruda, _foto_fila
from tests.narrative.test_redact import BASIS


def _peor_caso():
    """El incidente más cargado EN FOTOGRAFÍAS que el sistema puede producir hoy.

    Seis fotografías DENSAS —cada una en el techo de `preparar`— más la tabla por
    estación, la cronología y los daños. El ruido de 2 px es el patrón que
    `documentos/fotos.py` midió como «denso»: una grieta o un plafón caído caen ahí. Y
    2000×2600 y no 2000×2000: la cámara del móvil está fijada en vertical, y una captura
    cuadrada no pasa el tapado de la marca (`narrative/marca.py`).
    """
    fotos = [_foto_fila(_foto_cruda(2000, 2600, exif=False, ruido=2), f"ev-{i}") for i in range(6)]
    return model(danos=[_dano(fotos)], verdict_basis=BASIS)


def _cargado(estaciones: int, acciones: int):
    """Un incidente sin una sola fotografía y con la red y la bitácora crecidas.

    Es el otro eje del peso, y es el que no tiene cota: `incident_actions` es append-only
    y exenta de poda, y el número de estaciones de la red lo decide el despliegue.
    """
    abierto = model().opened_at
    return model(
        danos=[],
        estaciones=[
            EstacionFila(
                site_name=f"Inmueble {i}",
                site_code=f"SITE-{i:04d}",
                sensor_code=f"AM.R{i:05d}",
                dist_km=10.0 + i,
                t_teorico_s=2.0 + i / 10,
                t_medido_s=2.1 + i / 10,
                peak_pga_g=0.01 + i / 1000,
                tier="watch",
                umbral_pga_g=0.07,
                umbral_origen="referencia",
            )
            for i in range(estaciones)
        ],
        station_count=estaciones,
        actions=[
            ActionRow(abierto, f"verbo_largo_de_otro_productor_{i}", f"user:sub-{i}")
            for i in range(acciones)
        ],
        verdict_basis=BASIS,
    )


def _medir(m, *, con_fotos: bool) -> tuple[int, int]:
    imagenes = imagenes_de(m) if con_fotos else ()
    req = NarrativeRequest(
        facts=facts_from(m, imagenes=imagenes), model="anthropic/claude-sonnet-5", images=imagenes
    )
    cuerpo = json.dumps(cuerpo_de(req), ensure_ascii=False).encode("utf-8")
    return len(cuerpo), len(imagenes)


def test_el_peor_caso_CABE_en_la_cota_declarada() -> None:
    m = _peor_caso()
    con, cuantas = _medir(m, con_fotos=True)
    sin, _ = _medir(m, con_fotos=False)

    print(
        f"\n[T-7.27] peso de la petición · texto solo: {sin:,} B · "
        f"con {cuantas} fotos: {con:,} B ({con / 1024 / 1024:.2f} MiB) · "
        f"tope declarado: {TOPE_PETICION_BYTES:,} B "
        f"({TOPE_PETICION_BYTES / 1024 / 1024:.2f} MiB)"
    )

    assert cuantas == MAX_FOTOS_IA, "el peor caso no llegó a las seis fotos"
    assert con <= TOPE_PETICION_BYTES, (
        f"la petición del peor caso ({con:,} B) rebasa el tope declarado "
        f"({TOPE_PETICION_BYTES:,} B)"
    )
    # Y las fotos son lo que pesa: si el texto se acercara al cuerpo entero, la cota
    # estaría vigilando la parte equivocada.
    assert sin < con / 4, f"el texto ({sin:,} B) pesa más de lo que esta cota supone"


def test_la_cota_se_DERIVA_del_presupuesto_de_las_fotos() -> None:
    """Un tope tecleado se queda viejo en cuanto alguien suba la calidad de las
    derivadas; derivado, se mueve solo. Base64 son 4 bytes por cada 3."""
    assert TOPE_PETICION_BYTES > PRESUPUESTO_FOTOS_BYTES * 4 / 3
    assert PRESUPUESTO_FOTOS_BYTES == MAX_FOTOS_IA * 150 * 1024


def test_el_texto_del_peor_caso_no_se_come_el_margen() -> None:
    """La otra mitad de la cota: el margen que queda para los hechos. Con la tabla por
    estación y la cronología dentro, el bloque de texto creció y nadie lo había medido."""
    sin, _ = _medir(_peor_caso(), con_fotos=False)
    margen = TOPE_PETICION_BYTES - int(PRESUPUESTO_FOTOS_BYTES * 4 / 3)
    assert sin <= margen, f"los hechos ocupan {sin:,} B y el margen declarado es {margen:,} B"


def test_el_TEXTO_puede_rebasar_el_margen_y_por_eso_el_tope_se_COMPRUEBA() -> None:
    """La medición que desmiente el «cabe por construcción» de la cabecera anterior.

    El techo de las fotografías está garantizado; el del texto **no lo está por nada**.
    Esto no es un caso de laboratorio: 50 estaciones son una red mediana y 500 acciones
    son las de un incidente largo en una tabla que no se poda.
    """
    sin, _ = _medir(_cargado(50, 500), con_fotos=False)
    print(f"\n[T-7.27·A] texto de un incidente con 50 estaciones y 500 acciones: {sin:,} B")
    assert sin > MARGEN_TEXTO_BYTES, (
        f"el incidente cargado ocupa {sin:,} B y el margen de texto declarado es "
        f"{MARGEN_TEXTO_BYTES:,} B: si esto deja de ser cierto, vuelve a medir dónde está "
        "el techo del texto antes de relajar la comprobación"
    )


async def test_una_peticion_QUE_NO_CABE_se_degrada_y_se_dice_en_vez_de_mandarse() -> None:
    """`TOPE_PETICION_BYTES` era una cota declarada sin una sola lectura en producción.

    Ahora se comprueba antes de emitir: el socket no se abre, el papel imprime por qué y
    la exportación sale entera con el texto determinista.
    """
    salidas: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        salidas.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    m = _cargado(600, 6000)
    req = NarrativeRequest(facts=facts_from(m), model="algun/modelo")
    pesa = len(json.dumps(cuerpo_de(req), ensure_ascii=False).encode("utf-8"))
    assert pesa > TOPE_PETICION_BYTES, (
        f"el fixture solo pesa {pesa:,} B y el tope es {TOPE_PETICION_BYTES:,} B: "
        "la guarda sería vacua"
    )

    proveedor = OpenRouterProvider(
        Settings(openrouter_enabled=True, openrouter_model="algun/modelo"),
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
    )
    out = await proveedor.generate(req)
    assert out.provider == "deterministic"
    assert MOTIVO_PETICION_ENORME in (out.degraded_reason or "")
    assert salidas == [], "se emitió una petición que no cabía"
    assert out.photos_sent == (), "se anotaron fotografías que no salieron"
    assert len(out.sections) == 6, "el respaldo determinista no salió entero"
