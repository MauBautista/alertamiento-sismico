"""[T-8.12 · A-144] Lo que la base guarda en inglés sale en castellano en el papel.

Dos mitades, y ninguna basta sola:

1. **El registro es COMPLETO por construcción.** Cada vocabulario se DERIVA de
   su fuente —el CHECK del DDL, `settings`, `schemas.mobile`, `cctv`, la matriz
   de roles, `incident.classification`, `shakemap.calculo`— y cada valor tiene
   que tener rótulo. Un valor nuevo en la fuente pone esta suite roja en el mismo
   commit, en vez de salir crudo en el papel que se entrega. Donde el rótulo es el
   ESPEJO de otra superficie (el panel del gabinete, el formulario de la app, la
   consola) se compara con esa superficie, no con una copia escrita aquí.
2. **El papel USA el registro.** Se renderiza el documento con cada valor del
   enum en el campo que lo imprime y se exige que el identificador crudo NO
   aparezca y el rótulo SÍ. Sin esta mitad, un registro perfecto al que nadie
   llama pasaría en verde — que es exactamente cómo estaba `STATUS_LABELS` para
   la severidad: el diccionario de al lado existía y la portada imprimía
   `warning`.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from takab_api import cctv
from takab_api.auth.matrix import ROLE_ACTION_MATRIX
from takab_api.dictamen import rotulos as r
from takab_api.dictamen.bitacora import SIN_ROTULO
from takab_api.dictamen.model import (
    ActionRow,
    CctvBlock,
    CctvObjectRow,
    DanoFila,
    EvidenceRow,
    NivelFueraFila,
)
from takab_api.dictamen.pdf import render
from takab_api.incident.classification import CLASIFICACIONES
from takab_api.schemas.mobile import DAMAGE_CATEGORY_KEYS, DAMAGE_SEVERITIES
from takab_api.settings import RANK, SEVERITY_RANK
from takab_api.shakemap import calculo as shk
from tests.dictamen.test_avisos_impresos import _sacudida
from tests.dictamen.test_pdf import _OPENED, model
from tests.documentos.espia import espia_del_render

_RAIZ = Path(__file__).resolve().parents[3]
_DDL = (_RAIZ / "db" / "schema.sql").read_text(encoding="utf-8")


def _check_del_ddl(tabla: str, columna: str) -> set[str]:
    """Los valores del `CHECK (<columna> IN (...))` de `CREATE TABLE <tabla>`.

    Del DDL y no de una lista escrita aquí: es la fuente de verdad del esquema
    (`CLAUDE.md §5`), y una copia a mano es justo lo que diverge en silencio.
    """
    inicio = _DDL.index(f"CREATE TABLE {tabla} (")
    fin = _DDL.index("\n);", inicio)
    bloque = _DDL[inicio:fin]
    m = re.search(rf"CHECK \({columna} IN\s*\(([^)]*)\)", bloque)
    assert m, f"no encuentro el CHECK de {tabla}.{columna} en db/schema.sql"
    return set(re.findall(r"'([^']+)'", m.group(1)))


#: (registro, fuente DERIVADA, de dónde sale). Una fila por vocabulario que el
#: papel imprime.
VOCABULARIOS = [
    pytest.param(r.SEVERIDAD, _check_del_ddl("incidents", "severity"), id="incidents.severity"),
    pytest.param(r.SEVERIDAD, set(SEVERITY_RANK), id="settings.SEVERITY_RANK"),
    pytest.param(r.NIVEL, set(RANK), id="settings.RANK (nivel del gabinete)"),
    pytest.param(r.SENSOR, _check_del_ddl("sensors", "kind"), id="sensors.kind"),
    pytest.param(r.MONTAJE, _check_del_ddl("sensors", "mount"), id="sensors.mount"),
    pytest.param(r.EVIDENCIA, _check_del_ddl("evidence_objects", "kind"), id="evidence.kind"),
    pytest.param(r.CATEGORIA_DE_DANO, set(DAMAGE_CATEGORY_KEYS), id="damage.categories.key"),
    pytest.param(r.SEVERIDAD_DE_DANO, set(DAMAGE_SEVERITIES), id="damage.categories.severity"),
    pytest.param(r.ROL, set(ROLE_ACTION_MATRIX), id="matriz de roles"),
    pytest.param(r.PAPEL_CCTV, set(cctv.PAPELES), id="cctv.PAPELES"),
    pytest.param(r.CLASIFICACION, set(CLASIFICACIONES), id="incident.classification"),
    pytest.param(
        r.CLASIFICACION,
        _check_del_ddl("incident_classifications", "classification"),
        id="incident_classifications.classification",
    ),
    pytest.param(r.UMBRAL, set(shk.UMBRALES), id="shakemap.calculo.UMBRALES"),
    pytest.param(
        r.FUENTE_DEL_EVENTO, _check_del_ddl("seismic_events", "source"), id="seismic_events.source"
    ),
]


@pytest.mark.parametrize(("registro", "fuente"), VOCABULARIOS)
def test_todo_valor_de_la_fuente_tiene_ROTULO(registro: dict[str, str], fuente: set[str]) -> None:
    assert fuente, "la fuente derivada salió vacía: esta guarda estaría aprobando sobre la nada"
    faltan = sorted(fuente - set(registro))
    assert not faltan, (
        f"valores sin rótulo en castellano: {faltan}. Saldrían declarados como "
        f"«{SIN_ROTULO}» en el papel que se entrega; añádelos a `dictamen/rotulos.py`"
    )


@pytest.mark.parametrize(("registro", "fuente"), VOCABULARIOS)
def test_ningun_rotulo_repite_el_IDENTIFICADOR_crudo(
    registro: dict[str, str], fuente: set[str]
) -> None:
    """Un rótulo que es el mismo `snake_case` no traduce nada."""
    for clave, texto in registro.items():
        assert "_" not in texto, f"el rótulo de {clave!r} lleva un guion bajo: {texto!r}"
        assert texto.strip(), f"el rótulo de {clave!r} está vacío"


# ─────────────────────────────── los espejos: la MISMA palabra en las dos superficies


def test_el_NIVEL_es_el_espejo_del_PANEL_del_gabinete() -> None:
    """Quien miró el panel durante el sismo y quien lee el papel leen la misma palabra."""
    html = (_RAIZ / "edge" / "takab_edge" / "local_api" / "index.html").read_text("utf-8")
    bloque = html[html.index("const TIERS = {") : html.index("};", html.index("const TIERS = {"))]
    panel = {
        clave: re.sub(r"^[^A-ZÁÉÍÓÚÑ]+", "", etiqueta)
        for clave, etiqueta in re.findall(r"(\w+):\s*\{\s*label:\s*'([^']+)'", bloque)
    }
    assert set(panel) == set(RANK), "el panel y el motor no tienen los mismos niveles"
    assert panel == r.NIVEL, f"el papel no dice lo mismo que el panel: {panel} ≠ {r.NIVEL}"


def test_la_CATEGORIA_de_dano_es_el_espejo_del_FORMULARIO_de_la_app() -> None:
    """El papel dice lo mismo que eligió quien reportó."""
    ts = (_RAIZ / "mobile" / "src" / "features" / "damage" / "categories.ts").read_text("utf-8")
    app = dict(re.findall(r'\{\s*key:\s*"(\w+)",\s*label:\s*"([^"]+)"\s*\}', ts))
    assert app, "no se pudo leer el formulario de la app"
    assert app == r.CATEGORIA_DE_DANO


def test_la_SEVERIDAD_de_dano_cubre_TAMBIEN_lo_que_ofrece_la_app() -> None:
    """⚠️ La app ofrece `high` y la API no lo acepta (`DAMAGE_SEVERITIES`).

    La columna es `jsonb` sin CHECK: el día que alguien alinee los dos lados, el
    papel no puede imprimirlo crudo. Se exige la UNIÓN de las dos fuentes.
    """
    ts = (_RAIZ / "mobile" / "src" / "features" / "damage" / "categories.ts").read_text("utf-8")
    m = re.search(r"SEVERITIES = \[([^\]]+)\]", ts)
    assert m
    app = set(re.findall(r'"(\w+)"', m.group(1)))
    assert (app | set(DAMAGE_SEVERITIES)) <= set(r.SEVERIDAD_DE_DANO)


def test_la_CLASIFICACION_es_el_espejo_de_la_CONSOLA() -> None:
    ts = (_RAIZ / "web" / "src" / "features" / "triage" / "useClassification.ts").read_text("utf-8")
    consola = dict(re.findall(r'value:\s*"(\w+)",\s*label:\s*"([^"]+)"', ts))
    assert consola == r.CLASIFICACION


# ─────────────────────────────────────────────── las funciones, sin render


def test_un_valor_DESCONOCIDO_se_declara_y_no_se_cuela() -> None:
    assert r.rotulo(r.SEVERIDAD, "catastrophic") == f"catastrophic · {SIN_ROTULO}"
    assert r.rotulo(r.SEVERIDAD, None) == "SIN DATO"
    assert r.rotulo(r.SEVERIDAD, "") == "SIN DATO"


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("user:0f1e2d3c-aaaa-bbbb-cccc-000000000000", "OPERADOR 0f1e2d3c"),
        ("system:edge", "SISTEMA · gabinete"),
        ("system:notify:push:enqueue", "SISTEMA · notificaciones (push:enqueue)"),
        ("edge:gw-dev-0001", "GABINETE gw-dev-0001"),
    ],
)
def test_el_ACTOR_de_la_cronologia_en_castellano(crudo: str, esperado: str) -> None:
    assert r.actor(crudo) == esperado


def test_el_actor_de_una_PERSONA_no_imprime_el_uuid_entero() -> None:
    """Espejo de `actorLabel` de la consola: ocho caracteres, no el `sub` completo."""
    sub = "0f1e2d3c-aaaa-bbbb-cccc-000000000000"
    assert sub not in r.actor(f"user:{sub}")


# ─────────────────────────────────────── [A-150] la hora local junto a la UTC


def test_la_hora_local_va_JUNTO_a_la_UTC() -> None:
    cuando = datetime(2026, 9, 22, 18, 2, 5, tzinfo=UTC)
    assert r.instante(cuando, segundos=False) == "2026-09-22 18:02 UTC · 12:02 hora del centro"
    assert r.instante(cuando) == "2026-09-22 18:02:05 UTC · 12:02:05 hora del centro"


def test_si_la_fecha_LOCAL_es_otra_se_dice() -> None:
    """A las 02:00 UTC en el centro todavía es el día ANTERIOR (20:00). Sin la fecha
    local, «20:00 hora del centro» pondría el suceso en el día equivocado."""
    cuando = datetime(2026, 9, 23, 2, 0, 0, tzinfo=UTC)
    assert r.instante(cuando, segundos=False) == (
        "2026-09-23 02:00 UTC · 2026-09-22 20:00 hora del centro"
    )


def test_una_zona_desconocida_NO_inventa_un_desfase() -> None:
    cuando = datetime(2026, 9, 22, 18, 2, tzinfo=UTC)
    texto = r.instante(cuando, "Marte/Olympus_Mons", segundos=False)
    assert texto.startswith("2026-09-22 18:02 UTC")
    assert "no disponible" in texto


def test_la_hora_ingenua_se_toma_como_UTC_y_no_como_local() -> None:
    ingenua = datetime(2026, 9, 22, 18, 2)
    assert r.instante(ingenua, segundos=False).startswith("2026-09-22 18:02 UTC")


# ────────────────────────── la otra mitad: el PAPEL usa el registro, valor a valor


def _texto(m, variante: str = "technical") -> str:  # noqa: ANN001 - ReportModel
    with espia_del_render() as cap:
        render(m, variante)
    return cap.texto


def _ausente(crudo: str, texto: str) -> bool:
    """¿Falta el identificador como PALABRA? `watch` no puede casar con `watchdog`."""
    return re.search(rf"(?<![\w:]){re.escape(crudo)}(?![\w])", texto) is None


@pytest.mark.parametrize("severidad", sorted(SEVERITY_RANK))
def test_la_SEVERIDAD_de_la_portada_sale_en_castellano(severidad: str) -> None:
    with espia_del_render() as cap:
        render(model(severity=severidad))
    portada = cap.portada()
    assert r.SEVERIDAD[severidad] in portada
    assert _ausente(severidad, portada), f"la portada imprime `{severidad}` crudo"


@pytest.mark.parametrize("nivel", sorted(RANK))
def test_el_NIVEL_de_cada_estacion_sale_en_castellano(nivel: str) -> None:
    base = model()
    m = replace(base, estaciones=[replace(base.estaciones[0], tier=nivel)])
    with espia_del_render() as cap:
        render(m)
    seccion = cap.seccion("RED DE ESTACIONES")
    assert r.NIVEL[nivel] in seccion
    assert _ausente(nivel, seccion), f"la §7 imprime `{nivel}` crudo"
    assert "TIER" not in seccion, "la cabecera de la columna sigue en inglés"


def test_el_SENSOR_y_su_MONTAJE_salen_en_castellano() -> None:
    for kind in r.SENSOR:
        for mount in r.MONTAJE:
            with espia_del_render() as cap:
                render(model(sensors=[{"kind": kind, "model": "RS4D", "mount": mount}]))
            seccion = cap.seccion("INSTRUMENTACIÓN")
            assert r.SENSOR[kind] in seccion
            assert r.MONTAJE[mount] in seccion
            assert _ausente(kind.upper(), seccion) and _ausente(mount, seccion)


def test_la_CUSTODIA_nombra_el_objeto_en_castellano() -> None:
    evidencia = [EvidenceRow(k, "a" * 64, _OPENED) for k in sorted(r.EVIDENCIA)]
    with espia_del_render() as cap:
        render(model(evidence=evidencia))
    seccion = cap.seccion("CADENA DE CUSTODIA")
    for k in r.EVIDENCIA:
        assert r.EVIDENCIA[k] in seccion
        assert _ausente(k.upper(), seccion), f"la custodia imprime `{k.upper()}`"


def test_QUIEN_de_la_cronologia_sale_en_castellano() -> None:
    sub = "0f1e2d3c-aaaa-bbbb-cccc-000000000000"
    acciones = [
        ActionRow(_OPENED, "siren_on", "system:edge"),
        ActionRow(_OPENED, "ack", f"user:{sub}"),
    ]
    with espia_del_render() as cap:
        render(model(actions=acciones))
    seccion = cap.seccion("CRONOLOGÍA DEL INCIDENTE")
    assert "system:edge" not in seccion
    assert sub not in seccion
    assert "SISTEMA · gabinete" in seccion and "OPERADOR 0f1e2d3c" in seccion


def test_QUIEN_FIRMO_sale_en_la_cronologia_como_en_el_FIRMO_y_no_como_OPERADOR() -> None:
    """[T-8.12 · 2ª vuelta] La acción de FIRMA salía «OPERADOR 0f1e2d3c» cuatro
    renglones encima de «FIRMÓ INSPECTOR · Ing. Laura Méndez»: la misma persona,
    con dos rótulos, y el de la cronología equivocado.

    * quien firmó la CABEZA, exactamente como el FIRMÓ;
    * quien firmó un dictamen SUSTITUIDO, por su rol y el prefijo de la consola,
      y sin su nombre: el papel no lo imprime en ningún otro sitio, y la
      cronología no puede ser la puerta de un dato personal nuevo;
    * cualquier otra persona, como en la consola."""
    from takab_api.dictamen.model import DictamenRow  # noqa: PLC0415

    cabeza = "0f1e2d3c-aaaa-bbbb-cccc-000000000000"
    sustituido = "5a5a5a5a-aaaa-bbbb-cccc-000000000000"
    otro = "7c1d2e3f-aaaa-bbbb-cccc-000000000000"
    m = model(
        verdict_signed=True,
        dictamens=[
            DictamenRow(
                "d-3", "inhabit_monitor", _OPENED, cabeza, "v1", "d-2", "Ing. Laura Méndez"
            ),
            DictamenRow("d-2", "inhabit_monitor", _OPENED, sustituido, "v1", "d-1", "Arq. Otro"),
            DictamenRow("d-1", "inhabit_monitor", _OPENED, None, "v1", None),
        ],
        actions=[
            ActionRow(_OPENED, "ack", f"user:{otro}"),
            ActionRow(_OPENED, "dictamen_signed", f"user:{sustituido}"),
            ActionRow(_OPENED, "dictamen_signed", f"user:{cabeza}"),
        ],
    )
    with espia_del_render() as cap:
        render(m)
    seccion = cap.seccion("CRONOLOGÍA DEL INCIDENTE")
    rol = r.rol_que_firma()
    assert f"{rol} · Ing. Laura Méndez" in seccion
    assert f"{rol} 5a5a5a5a" in seccion
    assert "Arq. Otro" not in cap.texto, "imprimió el nombre de un firmante SUSTITUIDO"
    assert "OPERADOR 0f1e2d3c" not in seccion and "OPERADOR 5a5a5a5a" not in seccion
    assert "OPERADOR 7c1d2e3f" in seccion, "quien no firmó sigue como en la consola"


def test_la_CABEZA_firmada_sin_nombre_sale_por_su_ROL_como_en_el_FIRMO() -> None:
    sub = "0f1e2d3c-aaaa-bbbb-cccc-000000000000"
    assert r.firmantes_de_la_cadena([(sub, None), (None, None)]) == {sub: r.rol_que_firma()}
    assert r.actor(f"user:{sub}", r.firmantes_de_la_cadena([(sub, None)])) == r.rol_que_firma()


def test_los_DANOS_salen_en_castellano_rol_categoria_y_severidad() -> None:
    danos = [
        DanoFila(
            report_id=f"d-{i}",
            rol=rol,
            zona="Nivel 3",
            categorias=[
                {"key": k, "severity": s}
                for k, s in zip(
                    sorted(r.CATEGORIA_DE_DANO), sorted(r.SEVERIDAD_DE_DANO) * 2, strict=False
                )
            ],
            personas_en_riesgo=False,
            notas=None,
            ts=_OPENED,
        )
        for i, rol in enumerate(sorted(r.ROL))
    ]
    with espia_del_render() as cap:
        render(model(danos=danos))
    seccion = cap.seccion("DAÑOS REPORTADOS EN CAMPO")
    for crudo in (*r.ROL, *r.CATEGORIA_DE_DANO, *r.SEVERIDAD_DE_DANO):
        assert _ausente(crudo, seccion), f"la §14 imprime `{crudo}` crudo"
    for texto in (*r.ROL.values(), *r.CATEGORIA_DE_DANO.values()):
        assert texto in seccion


def test_la_custodia_del_VIDEO_nombra_el_papel_en_castellano() -> None:
    objetos = [
        CctvObjectRow("captura", papel, "b" * 64, _OPENED, "disponible") for papel in cctv.PAPELES
    ] + [CctvObjectRow("clip", None, "c" * 64, _OPENED, "disponible")]
    with espia_del_render() as cap:
        render(model(cctv=CctvBlock(objetos=objetos)))
    seccion = cap.seccion("EVACUACIÓN OBSERVADA (CCTV)")
    for papel in cctv.PAPELES:
        assert r.PAPEL_CCTV[papel] in seccion
        assert _ausente(papel, seccion), f"la §15 imprime `{papel}` crudo"
    assert r.TIPO_CCTV["clip"] in seccion


def test_el_NIVEL_suprimido_del_mapa_sale_en_castellano() -> None:
    m = model(
        shakemap=_sacudida(
            anillos=[],
            fuera_de_alcance=[
                NivelFueraFila(umbral=shk.UMBRAL_WATCH, pga_g=0.040, motivo="bajo_la_superficie")
            ],
        )
    )
    with espia_del_render() as cap:
        render(m)
    seccion = cap.seccion("MAPA DE LA SACUDIDA")
    assert r.UMBRAL[shk.UMBRAL_WATCH] in seccion
    assert shk.UMBRAL_WATCH not in seccion


# ───────────── [T-8.12 · 2ª vuelta] la §16: la prosa que el papel imprime DE VERDAD
#
# ⚠️ Las pruebas de arriba renderizan modelos SIN narrativa, así que la «prueba de
# que ningún valor del enum sale crudo» pasaba EN VACÍO sobre la §16 ANÁLISIS. Y
# `generate_report` aplica SIEMPRE una narrativa: con la IA apagada o degradada
# (tiempo agotado, clave, cuota, modelo no listado) es la DETERMINISTA, que
# interpolaba `severidad warning`, `fuente: local_quorum`, `gas_closed ×1` y
# `2026-08-03T10:00:00+00:00`. Lo vio el verificador adversarial extrayendo el
# texto del PDF; ninguna guarda lo miraba porque el guion de revisión le ponía
# prosa de relleno. Aquí se aplica la prosa REAL, por los dos caminos que llegan
# a ella en producción: la IA apagada y la IA que degrada.


class _ProveedorQueCae:
    """Un proveedor remoto que falla: `build_narrative` degrada al determinista."""

    name = "openrouter"

    async def generate(self, req):  # noqa: ANN001, ANN201 - doble de prueba
        raise TimeoutError("el proveedor no respondió")


@pytest.fixture(params=["ia_apagada", "ia_degradada"])
def camino(request: pytest.FixtureRequest) -> str:
    return request.param


async def _analisis(m, camino: str) -> str:  # noqa: ANN001 - ReportModel
    """El §16 tal como sale de una exportación: `build_narrative` + `apply_narrative`."""
    from takab_api.narrative import apply_narrative, build_narrative  # noqa: PLC0415
    from takab_api.narrative.deterministic import DeterministicProvider  # noqa: PLC0415

    proveedor = DeterministicProvider() if camino == "ia_apagada" else _ProveedorQueCae()
    narrativa = await build_narrative(m, provider=proveedor)
    assert narrativa.provider == "deterministic", "la prueba no ejerce la prosa determinista"
    assert (narrativa.degraded_reason is not None) == (camino == "ia_degradada")
    apply_narrative(m, narrativa)
    with espia_del_render() as cap:
        render(m)
    return cap.seccion("ANÁLISIS")


def _basis(severidad: str) -> dict:
    from tests.narrative.test_redact import BASIS  # noqa: PLC0415

    return {**BASIS, "evidence": {**BASIS["evidence"], "severity": severidad}}


@pytest.mark.parametrize("severidad", sorted(SEVERITY_RANK))
async def test_la_SEVERIDAD_de_la_prosa_del_16_sale_en_castellano(
    severidad: str, camino: str
) -> None:
    """Dos sitios: el resumen («se abrió con severidad …») y el porqué («la
    severidad del incidente en el momento de dictaminar era …», del `basis`)."""
    texto = await _analisis(model(severity=severidad, verdict_basis=_basis(severidad)), camino)
    assert _ausente(severidad, texto), f"la §16 imprime `{severidad}` crudo:\n{texto}"
    assert texto.count(r.SEVERIDAD[severidad]) >= 2, texto


@pytest.mark.parametrize("fuente", sorted(_check_del_ddl("seismic_events", "source")))
async def test_la_FUENTE_del_epicentro_de_la_prosa_del_16_sale_en_castellano(
    fuente: str, camino: str
) -> None:
    texto = await _analisis(model(event_source=fuente), camino)
    assert _ausente(fuente, texto), f"la §16 imprime `{fuente}` crudo:\n{texto}"
    assert r.FUENTE_DEL_EVENTO[fuente] in texto


async def test_los_VERBOS_de_la_bitacora_de_la_prosa_del_16_salen_rotulados(camino: str) -> None:
    """Cada `kind` del registro, en la frase «Acciones registradas en la bitácora».

    `dictamen` se exceptúa de la ausencia —no del rótulo— porque es TAMBIÉN la
    palabra castellana que la prosa usa diez veces: su ausencia no se puede pedir.
    """
    from takab_api.dictamen.bitacora import ROTULOS  # noqa: PLC0415

    acciones = [ActionRow(_OPENED, kind, "system:edge") for kind in sorted(ROTULOS)]
    texto = await _analisis(model(actions=acciones), camino)
    for kind, rotulo in ROTULOS.items():
        assert rotulo in texto, f"falta el rótulo de `{kind}` en la §16"
        if kind != "dictamen":
            assert _ausente(kind, texto), f"la §16 imprime `{kind}` crudo"


async def test_un_verbo_SIN_rotulo_se_declara_en_la_prosa_del_16(camino: str) -> None:
    texto = await _analisis(model(actions=[ActionRow(_OPENED, "bms_fan_off", "edge:x")]), camino)
    assert f"bms_fan_off · {SIN_ROTULO}" in texto


async def test_la_APERTURA_de_la_prosa_del_16_lleva_la_hora_LOCAL_del_inmueble(
    camino: str,
) -> None:
    """Ni ISO ni sólo UTC: el mismo instante que la portada, con la zona del sitio."""
    m = model(zona_horaria="America/Cancun")
    texto = await _analisis(m, camino)
    assert "T10:00:00" not in texto and "+00:00" not in texto, texto
    assert r.instante(_OPENED, "America/Cancun") in texto
    assert "hora del sureste" in texto


def test_lo_que_ve_la_IA_de_la_severidad_la_fuente_y_la_apertura_va_en_castellano() -> None:
    """La IA real recibe los MISMOS hechos, y lo que recibe crudo lo puede repetir."""
    from takab_api.narrative.redact import facts_from  # noqa: PLC0415

    f = facts_from(model(severity="warning", event_source="local_quorum"))
    assert f.severity == r.SEVERIDAD["warning"]
    assert f.event_source == r.FUENTE_DEL_EVENTO["local_quorum"]
    assert f.opened_at == r.instante(_OPENED), f.opened_at
    assert facts_from(model(event_source=None)).event_source is None, (
        "sin fuente, el hecho es la AUSENCIA: no la cadena «SIN DATO»"
    )


async def test_las_LIMITACIONES_del_16_no_desmienten_la_custodia_del_12(camino: str) -> None:
    """[T-8.12 · 2ª vuelta] Visto al MIRAR la §16 real: con un miniSEED en la custodia
    que esta exportación no pudo leer, la §3 dice —desde T-7.38·L— «consta un objeto
    miniSEED… no se obtuvo traza», la §16 «Qué se midió» dice lo mismo, y las
    Limitaciones de la MISMA §16 decían «este incidente no tiene miniSEED archivado»:
    la mitad de la ficha T-7.38·L que no llegó a `absences_of`."""
    from takab_api.dictamen.model import NO_SPECTRUM, ONDA_NO_LEIDA  # noqa: PLC0415

    con = await _analisis(model(evidence=[EvidenceRow("miniseed", "a" * 64, _OPENED)]), camino)
    assert "no tiene miniSEED archivado" not in con, con
    assert ONDA_NO_LEIDA in con
    sin = await _analisis(model(evidence=[]), camino)
    assert NO_SPECTRUM in sin, "sin miniSEED en la custodia, la ausencia sigue diciéndose"
