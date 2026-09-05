"""[T-2.84.a · huecos RO-9.a y RO-9.b] La regla de oro 9, sostenida por una prueba.

La regla dice: *sin streaming de forma de onda cruda; el waveform crudo (100 sps) no
se sube en continuo, el miniSEED crudo sube a S3 solo en eventos confirmados*. Es
además **invariante permanente** del `BLUEPRINT §14` — prohibición, no diferido.

Estaba escrita en tres documentos y **sostenida por ninguna prueba**: cero asserts
sobre un conjunto cerrado de topics, sobre volumen publicado, o sobre que un
`WaveformPacket` jamás alcance el camino de publicación continua. Añadir un
publicador continuo no rompía un solo test. **Se habría descubierto en la factura.**

LA PROPIEDAD ESTRUCTURAL, Y POR QUÉ ÉSTA
----------------------------------------
Una lista de topics prohibidos escrita a mano se queda atrás en cuanto alguien añade
el siguiente. Hace falta una propiedad que distinga *sola* «esto puede publicarse en
continuo» de «esto solo en evento confirmado». La elegida:

    Un payload es publicable EN CONTINUO si y sólo si su tamaño serializado está
    ACOTADO POR SU PROPIO ESQUEMA, con independencia del flujo de muestras.

Y su contrapositiva, que es la que caza: una **serie de muestras** —un array numérico
sin `maxItems` en el esquema, o un blob crudo (`format: binary/base64`) sin
`maxLength`— **no** está acotada: su tamaño crece con `sample_rate × duración`. Eso
es precisamente lo que la regla de oro 9 prohíbe subir en continuo, y es exactamente
lo que distingue `WaveformPacket.samples: list[int]` (100 valores por segundo y canal,
para siempre) de `FeatureBatch.features` (`max_length=256`, cota EN el esquema) o de
`HealthSnapshot` (escalares).

Por qué esa y no las tres alternativas obvias, cada una descartada por su motivo:

* **Una lista de topics prohibidos.** Fail-open: pasa cualquier topic que nadie haya
  escrito, y el publicador nuevo siempre trae topic nuevo.
* **Una cota de bytes o de mensajes por segundo.** Medir volumen exige un escenario
  representativo; un publicador continuo con un `sleep` largo, o un test corto, lo
  deja por debajo del umbral. Verde que no atrapa nada.
* **Prohibir `WaveformPacket` por su nombre.** Se rodea renombrando la clase, o
  envolviéndola, o mandando `list[int]` sin envoltorio. El esquema no se rodea: si el
  payload lleva una serie de números sin cota, la lleva se llame como se llame.

La propiedad se **deriva del esquema JSON del modelo** (`serie_de_muestras()`, en
`takab_edge.cloud.continuo`), y el conector la **impone en la puerta**: hoy sí hay algo
que impide el streaming crudo continuo, y no es la buena voluntad de quien escriba el
siguiente módulo.

LOS TRES CENSOS (ninguno enumerado a mano)
------------------------------------------
1. **Publicadores** — AST de TODO `takab_edge/**`: cada llamada a `.publish(...)` /
   `.publish_direct(...)`, con el tipo de su payload resuelto. *Fail-closed*: un sitio
   cuyo tipo no se pueda resolver sale ROJO, no verde. Un publicador nuevo entra solo.
2. **Topics** — introspección: toda constante de módulo `*_TOPIC` del árbol más toda
   propiedad `*_topic` de `EdgeSettings`. Un topic nuevo entra solo y sale rojo hasta
   que alguien lo declare con su razón al lado.
3. **Payloads** — todos los `BaseModel` definidos en `takab_edge`, clasificados por el
   esquema. Un contrato nuevo entra solo.

LO QUE ESTA GUARDA NO CUBRE, dicho con todas las letras
--------------------------------------------------------
* **Los campos `dict` libres** (`HealthSnapshot.audio`, `CommandAck.results`). Su
  esquema es `{"type": "object"}` sin `properties`: no restringe NADA, así que un
  waveform metido ahí pasaría. No se disimula —
  `test_los_campos_dict_libres_estan_declarados` los censa y los ancla: un campo
  `dict` libre NUEVO en un payload publicable pone el build en rojo.
* **La ruta S3 de backfill y evidencia**, que sube bytes por HTTP PUT pre-firmado y no
  por el conector. Su gate es el de RO-9.b (abajo) y el umbral de `backfill_threshold_s`.
* **El preview/debug por UDP del Shake**, que existe y está permitido (jamás
  producción, `CLAUDE.md §8`). No es publicación a la nube y no entra aquí.
* **La nube.** Esto vigila el lado edge del enlace; que la nube no pida waveform
  continuo es otra prueba y otro fichero.

RO-9.b · EL UMBRAL DE LA EVIDENCIA, TAMBIÉN DERIVADO
-----------------------------------------------------
«Solo en eventos confirmados» necesitaba una definición mecánica de *confirmado*, no un
literal `(EVACUATE_OR_HOLD, RESTRICTED)` copiado del supervisor a un assert — copiar el
literal prueba que el literal es igual a sí mismo. La definición usada es la que ya
existe y significa algo: **un evento está confirmado cuando COMANDA actuación**, y ese
conjunto se lee de `rules.TIER_ACTUATION` (los tiers con demandas no vacías). Bajar el
umbral —meter `watch`, que no comanda nada— pone el test en rojo por construcción.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel
from simulators.mqtt import FakeMqttTransport
from takab_edge.cloud import CloudConnector
from takab_edge.cloud.continuo import campos_de_dict_libre, serie_de_muestras
from takab_edge.config import EdgeSettings
from takab_edge.contracts import (
    AlertSource,
    Feature1s,
    FeatureBatch,
    HealthSnapshot,
    LocalEvent,
    Tier,
    TierDecision,
    WaveformPacket,
)
from takab_edge.rules import TIER_ACTUATION

_RAIZ = Path(__file__).resolve().parents[1] / "takab_edge"

#: El ÚNICO fichero donde se toca el transporte MQTT en crudo (bytes). Es la costura:
#: `CloudConnector` serializa el modelo y se lo entrega al transporte. Cualquier otro
#: sitio del árbol que hable bytes con el broker se salta el clasificador de payloads,
#: y por eso el censo lo saca en rojo en vez de ignorarlo.
_COSTURA = _RAIZ / "cloud" / "__init__.py"

#: Receptores exentos DENTRO de la costura: son el transporte, no el conector.
_RECEPTORES_DE_TRANSPORTE = frozenset({"self._transport", "self._conn"})

_METODOS_DE_PUBLICACION = frozenset({"publish", "publish_direct"})

#: Topics del gabinete, cada uno con su dirección y su razón. Añadir uno es una
#: decisión sobre la factura de AWS y sobre la regla de oro 9, no un trámite: el
#: censo derivado de `_topics_del_arbol()` obliga a pasar por aquí.
_TOPICS_DECLARADOS: dict[str, str] = {
    "takab/events": (
        "edge→nube · LocalEvent de un evento confirmado. Uno por episodio, no por muestra"
    ),
    "takab/health": (
        "edge→nube · heartbeat de salud (regla de oro 10: por transición + latido periódico)"
    ),
    "takab/acks": (
        "edge→nube · ActuatorAck/CommandAck. Uno por actuación; es evidencia de compliance"
    ),
    "takab/audit": (
        "edge→nube · ActuationRecord (T-2.86.a): la bitácora del gabinete, UNA fila por "
        "actuación, con actor y causa. No es caudal: sale del mismo hecho que ya produce "
        "un ack, y solo drena cuando VUELVE el enlace (regla de oro 10). Fila plana sin "
        "listas, así que el clasificador de la regla 9 la deja pasar por su esquema"
    ),
    "takab/features": (
        "edge→nube · Feature1s a 1 Hz y SOLO en tier watch+. Son AGREGADOS de 1 s "
        "(pga/pgv/rms/sta_lta), no muestras: 8 escalares por segundo, no 100 counts"
    ),
    "takab/features/batch": (
        "edge→nube · lote de features en tier normal (T-1.56). La cota vive EN el "
        "esquema (`max_length=256` ≈ 64 KB) — por eso pasa el clasificador"
    ),
    "takab/status/<thing>": (
        "edge→nube · beacon retained de presencia. Punto-en-tiempo, sin spool, dos "
        "publicaciones por sesión MQTT (online al conectar, LWT al caer)"
    ),
    "takab/backfill/request/<thing>": (
        "edge→nube · PIDE una URL pre-firmada. El dato viaja por S3, jamás por MQTT"
    ),
    "takab/backfill/grant/<thing>": "nube→edge · grant pre-firmado (entrante, no publicamos)",
    "takab/cmd/<thing>": "nube→edge · comando firmado de actuador (entrante, no publicamos)",
    "takab/cfg/<thing>": "nube→edge · config firmada (entrante, no publicamos)",
    "takab/catalog/<thing>": "nube→edge · catálogo SSN firmado (entrante, no publicamos)",
}

#: Campos `dict` libres en payloads publicables. El esquema no restringe su contenido,
#: así que el clasificador NO puede verlos: son el agujero declarado de esta guarda.
#: Cada uno está aquí porque su productor es conocido y acotado; uno nuevo tiene que
#: pasar por esta lista, y ése es el punto.
_DICTS_LIBRES_DECLARADOS: dict[str, str] = {
    "HealthSnapshot.audio": (
        "T-2.49 · perfil de tonos EFECTIVO (IDs aplicados/rechazados). Lo llena "
        "`audio.catalog` con un puñado de identificadores, no con señal"
    ),
    "CommandAck.results": (
        "T-1.59 · resultado por relé del self_test (5 canales). Lo llena `dispatch`, "
        "acotado por el número de relés cableados"
    ),
}


# --------------------------------------------------------------- censo de payloads


def _modelos_del_edge() -> dict[str, type[BaseModel]]:
    """Todos los `BaseModel` DEFINIDOS en `takab_edge` (derivado, no enumerado)."""
    import takab_edge

    for info in pkgutil.walk_packages(takab_edge.__path__, "takab_edge."):
        if info.name.endswith("__main__"):
            continue  # ejecutable, no biblioteca: importarlo correría el proceso gpio
        importlib.import_module(info.name)
    encontrados: dict[str, type[BaseModel]] = {}
    pendientes = list(BaseModel.__subclasses__())
    vistos: set[type] = set()
    while pendientes:
        cls = pendientes.pop()
        if cls in vistos:
            continue
        vistos.add(cls)
        pendientes.extend(cls.__subclasses__())
        if cls.__module__.startswith("takab_edge"):
            encontrados[cls.__name__] = cls
    return encontrados


# ------------------------------------------------------------ censo de publicadores


@dataclass(frozen=True)
class _Publicacion:
    archivo: str
    linea: int
    receptor: str
    metodo: str
    expr_payload: str
    tipo: str | None
    porque: str

    @property
    def sitio(self) -> str:
        return f"{self.archivo}:{self.linea}"


def _normalizar(anotacion: str) -> str:
    """`list[ActuatorAck]` → `ActuatorAck`; `Feature1s | None` → `Feature1s`."""
    texto = anotacion.strip().strip("'\"")
    for envoltorio in ("list[", "Sequence[", "Iterable[", "tuple[", "Optional["):
        if texto.startswith(envoltorio) and texto.endswith("]"):
            texto = texto[len(envoltorio) : -1]
    texto = texto.split("|", 1)[0].strip()
    texto = texto.split(",", 1)[0].strip()
    return texto.rsplit(".", 1)[-1]


def _anotaciones_de_retorno(arboles: dict[Path, ast.Module]) -> dict[str, str | None]:
    """`nombre de función → anotación de retorno`. Ambigua (dos firmas distintas) → None."""
    retornos: dict[str, str | None] = {}
    for arbol in arboles.values():
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            anotacion = ast.unparse(nodo.returns) if nodo.returns is not None else None
            if nodo.name in retornos and retornos[nodo.name] != anotacion:
                retornos[nodo.name] = None  # firmas en conflicto: no se adivina
            else:
                retornos[nodo.name] = anotacion
    return retornos


class _Resolutor:
    """Resuelve el TIPO del payload de una llamada a publish, dentro de su función.

    Cinco reglas, y nada más. Lo que no cae en ninguna se declara IRRESOLUBLE y el
    test se pone rojo: una guarda que dijera «no sé qué tipo es esto, adelante» sería
    fail-open, que es justo lo que teníamos.
    """

    def __init__(self, funcion: ast.AST | None, retornos: dict[str, str | None]) -> None:
        self._fn = funcion
        self._retornos = retornos

    def tipo_de(self, expr: ast.expr, profundidad: int = 0) -> tuple[str | None, str]:
        if profundidad > 4:
            return None, "cadena de asignaciones demasiado larga para resolver"
        if isinstance(expr, ast.Call):  # R1 — construcción directa: publish(t, Modelo(...))
            nombre = _normalizar(ast.unparse(expr.func))
            if isinstance(expr.func, ast.Attribute):  # R5 — <algo>.f(...) → retorno de f
                anotacion = self._retornos.get(expr.func.attr, "")
                if anotacion:
                    return _normalizar(anotacion), f"retorno de {expr.func.attr}()"
                return None, f"llamada a .{expr.func.attr}() sin anotación de retorno"
            return nombre, "construcción en el propio argumento"
        if not isinstance(expr, ast.Name):
            if _es_contenedor_vacio(expr):
                return None, "_VACUO_"  # `acks = []`: no aporta tipo, tampoco lo contradice
            return None, f"expresión no resoluble: {ast.unparse(expr)!r}"
        if self._fn is None:
            return None, "nombre suelto fuera de una función"
        nombre = expr.id

        candidatos: list[tuple[str | None, str]] = []
        for nodo in ast.walk(self._fn):
            # R3 — parámetro anotado de la función que publica
            if isinstance(nodo, ast.arg) and nodo.arg == nombre and nodo.annotation is not None:
                candidatos.append(
                    (_normalizar(ast.unparse(nodo.annotation)), "anotación del parámetro")
                )
            # R2 — `x: T = ...` / `x = Modelo(...)` / `x = <algo>.f(...)`
            elif isinstance(nodo, ast.AnnAssign) and _es_target(nodo.target, nombre):
                candidatos.append(
                    (_normalizar(ast.unparse(nodo.annotation)), "anotación de la asignación")
                )
            elif isinstance(nodo, ast.Assign) and any(_es_target(t, nombre) for t in nodo.targets):
                candidatos.append(self.tipo_de(nodo.value, profundidad + 1))
            # R4 — `for x in <iterable>`
            elif isinstance(nodo, ast.For) and _es_target(nodo.target, nombre):
                tipo, porque = self.tipo_de(nodo.iter, profundidad + 1)
                candidatos.append((tipo, f"elemento de {porque}"))

        # Un nombre puede tener VARIAS ligaduras en la misma función (el caso real:
        # `acks = []` en la rama solo-aviso y `acks = execute_sequence(...)` en la
        # otra). Las vacuas —un contenedor literal vacío— no aportan tipo; de las
        # demás tiene que salir UNO solo, o esto es ambiguo y sale rojo.
        utiles = [(t, p) for t, p in candidatos if p != "_VACUO_"]
        if not utiles:
            return None, f"no se encontró de dónde sale {nombre!r} en esta función"
        tipos = {t for t, _p in utiles}
        if len(tipos) > 1:
            return None, f"{nombre!r} tiene ligaduras de tipos distintos: {sorted(map(str, tipos))}"
        tipo, porque = utiles[0]
        return tipo, porque


def _es_contenedor_vacio(expr: ast.expr) -> bool:
    """`[]`, `()`, `{}` — una ligadura que no dice nada del tipo de sus elementos."""
    if isinstance(expr, ast.List | ast.Tuple | ast.Set):
        return not expr.elts
    return isinstance(expr, ast.Dict) and not expr.keys


def _es_target(target: ast.expr, nombre: str) -> bool:
    return isinstance(target, ast.Name) and target.id == nombre


def _censar_publicadores() -> list[_Publicacion]:
    """Cada `.publish(...)`/`.publish_direct(...)` del árbol, con su payload resuelto."""
    arboles = {ruta: ast.parse(ruta.read_text()) for ruta in sorted(_RAIZ.rglob("*.py"))}
    retornos = _anotaciones_de_retorno(arboles)
    censo: list[_Publicacion] = []
    for ruta, arbol in arboles.items():
        padres: dict[ast.AST, ast.AST] = {}
        for nodo in ast.walk(arbol):
            for hijo in ast.iter_child_nodes(nodo):
                padres[hijo] = nodo
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Attribute):
                continue
            if nodo.func.attr not in _METODOS_DE_PUBLICACION:
                continue
            receptor = ast.unparse(nodo.func.value)
            if ruta == _COSTURA and receptor in _RECEPTORES_DE_TRANSPORTE:
                continue  # la costura misma: serializa y entrega bytes, por definición
            funcion = _funcion_contenedora(nodo, padres)
            # Posicional o por palabra clave: las dos formas llaman al mismo sitio, y
            # mirar sólo la posicional habría sido un agujero fail-OPEN en una guarda
            # que se vende como fail-closed.
            payload = nodo.args[1] if len(nodo.args) > 1 else None
            if payload is None:
                payload = next(
                    (kw.value for kw in nodo.keywords if kw.arg == "payload"),
                    None,
                )
            if payload is None:
                tipo, porque, expr = None, "la llamada no enseña su payload", "—"
            else:
                tipo, porque = _Resolutor(funcion, retornos).tipo_de(payload)
                expr = ast.unparse(payload)
            censo.append(
                _Publicacion(
                    archivo=ruta.relative_to(_RAIZ.parent).as_posix(),
                    linea=nodo.lineno,
                    receptor=receptor,
                    metodo=nodo.func.attr,
                    expr_payload=expr,
                    tipo=tipo,
                    porque=porque,
                )
            )
    return censo


def _funcion_contenedora(nodo: ast.AST, padres: dict[ast.AST, ast.AST]) -> ast.AST | None:
    actual = padres.get(nodo)
    while actual is not None:
        if isinstance(actual, ast.FunctionDef | ast.AsyncFunctionDef):
            return actual
        actual = padres.get(actual)
    return None


# ----------------------------------------------------------------- censo de topics


def _topics_del_arbol(settings: EdgeSettings) -> dict[str, str]:
    """`topic → dónde está declarado`. Constantes `*_TOPIC` + propiedades `*_topic`."""
    import takab_edge

    topics: dict[str, str] = {}
    for info in pkgutil.walk_packages(takab_edge.__path__, "takab_edge."):
        if info.name.endswith("__main__"):
            continue
        modulo = importlib.import_module(info.name)
        for nombre, valor in vars(modulo).items():
            if nombre.endswith("_TOPIC") and isinstance(valor, str) and valor:
                topics.setdefault(valor, f"{info.name}.{nombre}")
    for nombre in dir(type(settings)):
        if not nombre.endswith("_topic") or not isinstance(
            getattr(type(settings), nombre, None), property
        ):
            continue
        valor = getattr(settings, nombre)
        if isinstance(valor, str) and valor:
            generico = valor.replace(settings.thing_name, "<thing>")
            topics.setdefault(generico, f"EdgeSettings.{nombre}")
    return topics


# ------------------------------------------------------------------------ fixtures


@pytest.fixture
def conector(settings: EdgeSettings, tmp_path: Path) -> CloudConnector:
    transporte = FakeMqttTransport()
    conn = CloudConnector(settings, transport=transporte, spool_dir=tmp_path / "spool")
    conn.set_online(True)
    return conn


def _paquete_crudo(muestras: int = 100) -> WaveformPacket:
    return WaveformPacket(
        station="R4F74",
        channel="EHZ",
        starttime=datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC),
        samples=list(range(muestras)),
    )


# ============================================================== RO-9.a · la puerta


def test_el_clasificador_distingue_serie_de_muestras_de_payload_acotado() -> None:
    """NO-VACUIDAD del clasificador: si dejara de distinguir, todo lo demás es verde falso.

    `WaveformPacket` lleva `samples: list[int]` sin cota — crece con
    `sample_rate × duración`. `FeatureBatch` lleva `max_length=256` EN el esquema.
    Ésa es la diferencia entera, y se lee del esquema, no de los nombres.
    """
    motivo = serie_de_muestras(WaveformPacket)
    assert motivo is not None, (
        "el clasificador NO ve la serie de muestras de WaveformPacket.samples. "
        "Con esto roto, todos los tests de este fichero son verde vacío."
    )
    assert "samples" in motivo, f"el motivo debe NOMBRAR el campo culpable; salió {motivo!r}"

    for acotado in (FeatureBatch, HealthSnapshot, LocalEvent, Feature1s, TierDecision):
        assert serie_de_muestras(acotado) is None, (
            f"{acotado.__name__} está acotado por su esquema y el clasificador lo "
            f"marcó como serie de muestras: {serie_de_muestras(acotado)}. La guarda "
            "prohibiría de más y rompería el camino legítimo."
        )

    # Y no se rodea envolviéndolo ni renombrándolo: la propiedad es del ESQUEMA.
    class LoteDeVentanas(BaseModel):
        paquetes: list[WaveformPacket]

    class ContadorSuelto(BaseModel):
        cuentas: list[int]

    class DisfrazDeBlob(BaseModel):
        mseed: bytes

    for disfraz in (LoteDeVentanas, ContadorSuelto, DisfrazDeBlob):
        assert serie_de_muestras(disfraz) is not None, (
            f"{disfraz.__name__} se coló: se puede subir waveform crudo en continuo "
            "envolviéndolo, aplanándolo o mandándolo como bytes."
        )


def test_ningun_publicador_del_edge_pasa_una_serie_de_muestras() -> None:
    """CENSO DERIVADO: un publicador nuevo entra solo, y sin tipo resoluble sale rojo.

    Esto es lo que hace que la guarda no envejezca. No hay lista de módulos
    autorizados a publicar: se recorre el AST del árbol entero y cada
    `.publish(...)` que aparezca tiene que enseñar un payload de tipo conocido y
    acotado. El día que alguien añada `WaveformStreamer`, este test lo NOMBRA.
    """
    censo = _censar_publicadores()
    assert len(censo) >= 5, (
        f"el censo de publicadores salió ridículo ({len(censo)} sitios): no se está "
        "leyendo el árbol. Con el censo vacío esta guarda no vigila nada."
    )

    modelos = _modelos_del_edge()
    irresolubles = [p for p in censo if p.tipo is None or p.tipo not in modelos]
    assert not irresolubles, (
        "hay publicaciones cuyo payload NO se puede resolver, y esta guarda es "
        "fail-closed: sin tipo no hay veredicto.\n"
        + "\n".join(
            f"  · {p.sitio} — {p.receptor}.{p.metodo}(…, {p.expr_payload}) ⇒ {p.porque}"
            for p in irresolubles
        )
        + "\n\nAnota el tipo del payload (parámetro o asignación) para que el censo "
        "lo vea. Si lo que publicas no es un modelo Pydantic, estás saltándote la "
        "costura tipada y ése es exactamente el camino que la regla de oro 9 cierra."
    )

    culpables = [(p, serie_de_muestras(modelos[p.tipo])) for p in censo]
    rotos = [(p, motivo) for p, motivo in culpables if motivo is not None]
    assert not rotos, (
        "REGLA DE ORO 9 · streaming crudo continuo: hay publicadores que suben una "
        "serie de muestras por el enlace continuo.\n"
        + "\n".join(
            f"  · {p.sitio} — {p.receptor}.{p.metodo}(…, {p.expr_payload}) "
            f"publica {p.tipo}, que NO está acotado por su esquema: {motivo}"
            for p, motivo in rotos
        )
        + "\n\nEl waveform crudo NO se sube en continuo. Sube como evidencia miniSEED "
        "a S3 en un evento CONFIRMADO (`backfill.queue_evidence`), y solo ahí."
    )


def test_el_conector_rechaza_una_serie_de_muestras_en_la_puerta(
    conector: CloudConnector,
) -> None:
    """El invariante se IMPONE, no solo se observa: el conector es la única puerta."""
    transporte = conector._transport
    antes = len(transporte.published)

    assert conector.publish("takab/waveform", _paquete_crudo()) is False
    assert conector.publish_direct("takab/waveform", _paquete_crudo()) is False

    assert conector.rechazos_regla_9 == 2, (
        f"el conector debería haber rechazado 2 publicaciones; contó {conector.rechazos_regla_9}"
    )
    assert len(transporte.published) == antes, (
        "un WaveformPacket ALCANZÓ el transporte: eso es waveform crudo saliendo "
        f"hacia AWS IoT. Publicado: {transporte.published[antes:]}"
    )
    assert conector.queued == 0, (
        "el WaveformPacket quedó en el spool durable: no salió hoy, sale al "
        "reconectar. Un rechazo tiene que ser un rechazo, no un aplazamiento."
    )


def test_el_camino_legitimo_sigue_publicando(supervisor) -> None:
    """La guarda distingue, no prohíbe en bloque. Si prohibiera de más, esto sale rojo."""
    from takab_edge.supervisor import ACKS_TOPIC, EVENTS_TOPIC, HEALTH_TOPIC

    supervisor.cloud.publish(HEALTH_TOPIC, supervisor.health.snapshot())
    supervisor.cloud.publish(
        EVENTS_TOPIC,
        LocalEvent(
            tenant_id=supervisor.settings.tenant_id,
            site_id=supervisor.settings.site_id,
            source=AlertSource.SASMEX,
            tier=Tier.EVACUATE_OR_HOLD,
        ),
    )
    assert supervisor.cloud.queued_by_topic(HEALTH_TOPIC) >= 1
    assert supervisor.cloud.queued_by_topic(EVENTS_TOPIC) >= 1
    assert supervisor.cloud.queued_by_topic(ACKS_TOPIC) == 0  # nada que ackear aún
    assert supervisor.cloud.rechazos_regla_9 == 0, (
        "la guarda rechazó telemetría legítima: está prohibiendo de más y el "
        "gabinete se acaba de quedar mudo hacia la nube."
    )


def test_los_topics_del_gabinete_son_un_conjunto_cerrado_y_declarado(
    settings: EdgeSettings,
) -> None:
    """Un topic nuevo —el que necesitaría un publicador de waveform— entra solo y sale rojo."""
    encontrados = _topics_del_arbol(settings)
    assert len(encontrados) >= 8, (
        f"el censo de topics salió ridículo ({sorted(encontrados)}): no se está leyendo el árbol."
    )

    sin_declarar = {t: d for t, d in encontrados.items() if t not in _TOPICS_DECLARADOS}
    assert not sin_declarar, (
        "topics del gabinete SIN declarar en `_TOPICS_DECLARADOS`:\n"
        + "\n".join(f"  · {topic}  (en {donde})" for topic, donde in sorted(sin_declarar.items()))
        + "\n\nDeclara cada uno con su dirección y su razón. Si el topic nuevo lleva "
        "waveform crudo en continuo, la respuesta no es declararlo: es la regla de "
        "oro 9, y el dato va a S3 como evidencia de un evento confirmado."
    )

    fantasmas = set(_TOPICS_DECLARADOS) - set(encontrados)
    assert not fantasmas, (
        f"topics declarados que YA NO existen en el árbol: {sorted(fantasmas)}. "
        "Una lista con muertos dentro deja de leerse y acaba autorizando lo que no debe."
    )


def test_los_campos_dict_libres_estan_declarados() -> None:
    """EL AGUJERO DECLARADO: un `dict` suelto no lo puede ver el clasificador.

    `{"type": "object"}` sin `properties` no restringe nada, así que un waveform
    metido en un `dict` libre pasaría la puerta. No se disimula: se censa. Un campo
    `dict` libre NUEVO en un payload publicable tiene que pasar por esta lista.
    """
    censo = _censar_publicadores()
    modelos = _modelos_del_edge()
    publicables = {p.tipo for p in censo if p.tipo in modelos}
    assert publicables, "sin payloads publicables el censo no vigila nada"

    encontrados: dict[str, str] = {}
    for nombre in sorted(publicables):
        for campo in campos_de_dict_libre(modelos[nombre]):
            encontrados[f"{nombre}.{campo}"] = nombre

    sin_declarar = sorted(set(encontrados) - set(_DICTS_LIBRES_DECLARADOS))
    assert not sin_declarar, (
        "campos `dict` LIBRES nuevos en payloads publicables: el clasificador de la "
        "regla de oro 9 no puede ver lo que va dentro.\n  · "
        + "\n  · ".join(sin_declarar)
        + "\n\nDeclara cada uno con quién lo llena y por qué está acotado, o tipa el "
        "campo para que el esquema lo cubra."
    )

    fantasmas = sorted(set(_DICTS_LIBRES_DECLARADOS) - set(encontrados))
    assert not fantasmas, (
        f"declarados como agujero pero ya no existen: {fantasmas}. Bórralos de la lista."
    )


# ================================================= RO-9.b · el umbral de la evidencia


def test_el_miniseed_crudo_solo_se_encola_en_tiers_que_comandan_actuacion(
    supervisor, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bajar el umbral por accidente se pone rojo — y el umbral no está tecleado aquí.

    «Evento confirmado» se define por lo que el sistema HACE: un tier confirmado es
    el que comanda actuación, y ese conjunto se lee de `TIER_ACTUATION`. Meter
    `watch` (que no comanda nada) en la puerta de la evidencia pone esto en rojo
    solo; y un tier NUEVO entra en el barrido sin que nadie toque el test.
    """
    esperado = {tier for tier in Tier if TIER_ACTUATION[tier]}
    assert esperado, "TIER_ACTUATION no declara ningún tier que actúe: censo roto"

    encolados: list[Tier] = []
    tier_en_curso: list[Tier] = []
    monkeypatch.setattr(
        supervisor.backfill,
        "queue_evidence",
        lambda *_a, **_k: encolados.append(tier_en_curso[-1]),
    )

    for tier in Tier:
        tier_en_curso.append(tier)
        supervisor._act_and_publish(TierDecision(tier=tier, source=AlertSource.SASMEX), None)

    obtenido = set(encolados)
    assert obtenido == esperado, (
        "REGLA DE ORO 9 (RO-9.b): el miniSEED crudo tiene que subir SOLO en eventos "
        "confirmados, y «confirmado» = el tier COMANDA actuación.\n"
        f"  · tiers que comandan actuación (TIER_ACTUATION): {sorted(t.value for t in esperado)}\n"
        f"  · tiers que encolaron evidencia:                 {sorted(t.value for t in obtenido)}\n"
        f"  · de más (umbral BAJADO, sube waveform de lo que no es un evento): "
        f"{sorted(t.value for t in obtenido - esperado)}\n"
        f"  · de menos (evidencia PERDIDA de un evento real): "
        f"{sorted(t.value for t in esperado - obtenido)}"
    )
    assert len(encolados) == len(obtenido), (
        f"un mismo tier encoló evidencia más de una vez: {encolados}"
    )


# --- Un topic sin su línea en la política del fleet DESCONECTA al gabinete -----
#
# [T-2.86.a] La política IoT lista los topics **uno a uno, sin comodines**. Un
# `publish` a uno que no esté ahí no falla solo: el broker **corta la sesión
# MQTT**, y el gabinete entra en flapping cada 10 s — visto en producción el
# 2026-07-12. O sea que añadir un topic al edge sin tocar Terraform no degrada
# una función, deja MUDO al gabinete entero, camino de vida incluido.
#
# Ese acoplamiento vivía en la cabeza de quien lo había sufrido y en un comentario.
# Aquí se vuelve un test: el censo de topics de arriba —que ya se deriva del
# árbol— tiene que estar contenido en la política.

_POLITICA_FLEET = (
    Path(__file__).resolve().parents[2] / "infra" / "terraform" / "modules" / "iot-core" / "main.tf"
)

#: El censo escribe `<thing>` donde Terraform interpola el nombre del gabinete.
_MARCA_DEL_THING = "${local.thing_name}"


def _topics_publicables_del_terraform() -> set[str]:
    """Los `iot:Publish` de la política del fleet, tal como los declara Terraform."""
    # Los COMENTARIOS se quitan antes de nada, y no es celo: la primera versión de
    # esto buscaba el `]` de cierre sobre el texto crudo y lo encontró dentro de
    # `# [T-2.86.a] …` —el corchete de la propia ficha—, así que dio la lista por
    # terminada tres topics antes y habría dejado pasar justo el que se estaba
    # añadiendo. Un extractor que lee HCL a ojo tiene que ignorar lo que no es HCL.
    crudo = _POLITICA_FLEET.read_text(encoding="utf-8")
    texto = "\n".join(re.sub(r"#.*$", "", linea) for linea in crudo.splitlines())
    i = texto.find('Action = "iot:Publish"')
    assert i != -1, (
        f"no se encontró el statement `iot:Publish` en {_POLITICA_FLEET.name}: "
        "si la política cambió de forma, este test hay que reescribirlo, no borrarlo"
    )
    fin = texto.index("]", i)
    return set(re.findall(r":topic/([^\"]+)\"", texto[i:fin]))


def test_todo_topic_que_el_gabinete_publica_esta_en_la_politica_del_fleet() -> None:
    autorizados = _topics_publicables_del_terraform()
    assert autorizados, "la política del fleet no autoriza NINGÚN topic: algo se rompió al leerla"

    del_edge = {
        t.replace("<thing>", _MARCA_DEL_THING)
        for t, razon in _TOPICS_DECLARADOS.items()
        if razon.startswith("edge→nube")
    }
    sin_autorizar = del_edge - autorizados
    assert not sin_autorizar, (
        f"el gabinete publica en {sorted(sin_autorizar)} y la política del fleet NO lo "
        f"autoriza (autorizados: {sorted(autorizados)}).\n"
        "Esto no degrada una función: el broker CORTA la sesión MQTT en cada publish y el "
        "gabinete se queda mudo, camino de vida incluido (producción, 2026-07-12).\n"
        "Añade la línea en `infra/terraform/modules/iot-core/main.tf` — y recuerda que la "
        "política no lleva comodines, así que un sub-topic necesita su propia línea."
    )
