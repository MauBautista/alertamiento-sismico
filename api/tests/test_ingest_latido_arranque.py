"""[T-7.05 · H-1] El latido de ARRANQUE, el que fue a la cola de mensajes muertos.

El 2026-09-10 un latido de `gw-dev-0001` acabó en `takab-dev-dlq-telemetry` y
dejó su alarma encendida. La razón que registró el rechazo fue literal::

    health_snapshot: None is not of type 'number' (en packet_loss_pct)

Ese `None` **no era un fallo del gabinete: era la verdad**. Al arrancar todavía
no ha visto un solo paquete de SeedLink, no ha medido un PUBACK y no tiene UPS,
así que las cuatro sondas de `sondas_sin_dato` dicen «sin dato». Un `0` en su
lugar se lee «enlace perfecto» y «UPS llena» dicho por quien no ha mirado, que
es justo la mentira que prohíbe la regla de oro 7 — la misma que ya corrigieron
`relays` (T-2.70.a·B1) y el propio `packet_loss_pct` en el gabinete (T-5.24).

Lo que se prueba aquí es el camino ENTERO que el mensaje recorre en la nube, con
el cuerpo del latido que murió (`shared/schemas/tests/`) y **por el consumidor de
verdad**: cola SQS → envoltorio `meta_*` de la regla IoT → `split_meta` → el
validador de contrato → el handler → la fila en `device_health`, o el enrutado a
la DLQ cuando el contrato dice que no. Ese enrutado es donde el mensaje murió, así
que se ejerce en los dos sentidos: con el esquema de aquel día acaba en la cola de
mensajes muertos con su motivo exacto, y con el de hoy entra y deja la fila con
**NULL**, no con ceros.

El cuerpo se LEYÓ de la cola el 2026-09-12, antes de drenarla, y de ahí salen sus
valores; la lectura se truncó a media lista de relés y el fichero del vector
enumera una por una las cuatro cosas que quedaron detrás del corte y cómo se
completaron. Ni el mensaje ni su volcado existen ya, así que ese fichero es la
única memoria del incidente — y la procedencia no se afirma sólo de palabra: con
el esquema que la nube servía aquel día —traído de git, no transcrito— el vector
reproduce la razón del rechazo carácter por carácter, y quitarle el `null` de
`packet_loss_pct` la hace desaparecer. El `null` es la causa, no una
coincidencia.

Por qué el fallo ocurrió con el arreglo ya escrito: `packet_loss_pct` se relajó
a `null` el 2026-09-03 (T-5.24, `d67d079`) y el gabinete corría `f19aa06`, del
2026-09-10, que YA lo contiene; la nube seguía corriendo la imagen anterior, cuyo
esquema publicado aún decía ``"type": "number"``. El contrato no se rompió por
ignorancia sino por **desfase de despliegue**, y el único seguro contra eso es
una prueba que viaje con el código.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import psycopg
import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from psycopg.rows import dict_row

from conftest import _dsn
from takab_api.contracts import loader
from takab_api.contracts.loader import ContractError, kind_for_topic, validate
from takab_api.contracts.meta import split_meta
from takab_api.ingest.consumer import SqsConsumer
from takab_api.ingest.handlers import HANDLERS, GatewayCtx, Outcome, handle_health_snapshot
from takab_api.ingest.registry import Registry
from takab_api.settings import Settings

# Y para el camino ENTERO —cola, consumidor, DLQ— la flota COMMITEADA y la cola
# moto que ya monta el E2E fino de ingesta: el worker abre sus propias conexiones
# y no vería una flota sembrada dentro de una transacción que se revierte.
from test_ingest_e2e import (  # noqa: F401 — fixtures reutilizadas
    _ingest_conn,
    _n_messages,
    queues,
    sqs,
)
from test_ingest_e2e import fleet as flota_commiteada  # noqa: F401 — fixture reutilizada

# La flota mínima y el contexto de identidad ya están montados —y son los de la
# convención dev que usa el gabinete real—; volver a sembrarlos aquí crearía un
# segundo seed que diverge del primero en el primer cambio de esquema.
from test_ingest_handlers import GW, ctx, fleet  # noqa: F401 — fixtures reutilizadas

_RAIZ = Path(__file__).resolve().parents[2]
CUERPO = _RAIZ / "shared/schemas/tests/latido_arranque_sin_dato.json"


def _fixture() -> tuple[dict, list[str]]:
    doc = json.loads(CUERPO.read_text("utf-8"))
    return doc["mensaje"], doc["sondas_sin_dato"]


def test_el_latido_de_arranque_pasa_el_validador_de_ingesta() -> None:
    """La puerta donde el mensaje real murió: el contrato compartido."""
    mensaje, _sondas = _fixture()
    payload, meta = split_meta(mensaje)

    assert meta.topic == "takab/health"
    assert meta.principal == "gw-dev-0001"

    kind = kind_for_topic(meta.topic)
    assert kind == "health_snapshot"
    try:
        validate(kind, payload)
    except ContractError as exc:  # pragma: no cover — es el defecto que se cierra
        pytest.fail(f"el latido de arranque volvería a la DLQ de telemetría: {exc}")


@pytest.mark.parametrize("campo", _fixture()[1])
def test_cada_sonda_sin_dato_admite_null_en_el_esquema_publicado(campo: str) -> None:
    """Campo a campo, y derivado del fichero: no se enumeran aquí a mano.

    `packet_loss_pct` fue el que rompió, pero los otros tres llegan `null` en el
    MISMO mensaje: si mañana uno solo vuelve a estrecharse, el latido de
    arranque muere igual y la razón de la DLQ apunta a otro nombre.
    """
    mensaje, _sondas = _fixture()
    payload, _meta = split_meta(mensaje)
    assert payload[campo] is None, "el fixture dejó de ejercer «sin dato» en este campo"
    validate("health_snapshot", payload)


def test_el_latido_de_arranque_se_guarda_con_NULL_y_no_con_ceros(
    fleet: psycopg.Connection,  # noqa: F811 — fixture
    ctx: GatewayCtx,  # noqa: F811 — fixture
) -> None:
    """Aceptarlo no basta: un `0.0` en la fila sería la misma mentira, más tarde."""
    mensaje, sondas = _fixture()
    payload, meta = split_meta(mensaje)

    resultado = handle_health_snapshot(fleet, payload, meta, ctx)
    assert resultado.outcome is Outcome.OK, getattr(resultado, "reason", resultado)

    with fleet.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT packet_loss_pct, mqtt_rtt_ms, battery_pct, battery_min_left, "
            "       seedlink_lag_s, ntp_offset_ms, relays_state, reason "
            "FROM device_health WHERE gateway_id = %s AND ts = %s",
            (GW, payload["captured_at"]),
        )
        fila = cur.fetchone()

    assert fila is not None, "el latido se aceptó pero no dejó fila en device_health"
    # Las cuatro sondas sin dato ⇒ NULL. `ups_runtime_s` aterriza convertido a
    # minutos en `battery_min_left`, así que se comprueba por su columna.
    columna = {"ups_runtime_s": "battery_min_left"}
    for campo in sondas:
        assert fila[columna.get(campo, campo)] is None, (
            f"{campo} llegó «sin dato» y la base guardó {fila[columna.get(campo, campo)]!r}: "
            "el SOC lo pintaría como una medición"
        )
    # Y lo que SÍ venía medido se guarda, para que el test no pueda pasar por
    # la vía barata de no escribir nada. El offset se deriva del propio vector
    # ×1000 —lo que se mide es la CONVERSIÓN de unidad, no un número copiado que
    # habría que retocar cada vez que el vector cambie.
    assert fila["reason"] == "heartbeat"
    assert fila["ntp_offset_ms"] == pytest.approx(payload["ntp_offset_s"] * 1000.0, abs=1e-9)
    assert fila["seedlink_lag_s"] == pytest.approx(payload["seedlink_lag_s"], abs=1e-9)
    # El latido real trae el censo eléctrico de los relés, así que la nube anota
    # «el gabinete pudo mirarse los pines». `stopped` aquí significaría lo
    # contrario —«pregunté y no hay filas»— y es lo que decía el vector cuando
    # llevaba `relays: []`, que ningún gabinete desplegado emite.
    assert fila["relays_state"] == "reported"


# --------------------------------------------- la procedencia del vector, medida

#: La razón que la cola de mensajes muertos guardó junto al latido, literal.
RAZON_DLQ = "health_snapshot: None is not of type 'number' (en packet_loss_pct)"

#: El commit que relajó `packet_loss_pct` (T-5.24, 2026-09-03). Su PADRE es el
#: esquema que la nube seguía sirviendo el 2026-09-10, siete días después.
COMMIT_DE_LA_RELAJACION = "d67d079"

_PISTA_CLON = (
    "\n  Si esto falla en CI y no en local, es un CLON SUPERFICIAL: `actions/checkout` "
    "clona con `fetch-depth: 1` por defecto. El job `api` lo pide con `fetch-depth: 0` "
    "precisamente por esto."
)


def _esquema_que_servia_la_nube() -> dict:
    """El contrato que la nube aplicaba el día del rechazo, LEÍDO DE GIT.

    No se transcribe aquí. Una copia a mano coincide el día que se escribe y deja
    de coincidir el día que alguien retoca esa estrofa — y entonces este fichero
    sigue verde reproduciendo un rechazo que ya no es el que ocurrió. Es la misma
    clase de defecto que «un censo que enumera a mano acaba divergiendo», y el
    repo ya tiene el patrón bueno al lado (`test_docs_consistency` interroga a git
    en vez de recordar).
    """
    salida = subprocess.run(  # noqa: S603
        ["git", "show", f"{COMMIT_DE_LA_RELAJACION}~1:shared/schemas/health_snapshot.schema.json"],  # noqa: S607, E501
        cwd=_RAIZ,
        capture_output=True,
        text=True,
    )
    assert salida.returncode == 0, (
        f"no se pudo leer el esquema de {COMMIT_DE_LA_RELAJACION}~1: "
        f"{salida.stderr.strip()}{_PISTA_CLON}"
    )
    return json.loads(salida.stdout)


def _razon(esquema: dict, payload: dict) -> str | None:
    """La misma composición que `contracts.loader.validate`, sobre otro esquema."""
    error = best_match(Draft202012Validator(esquema).iter_errors(payload))
    if error is None:
        return None
    donde = "/".join(str(p) for p in error.absolute_path) or "$"
    return f"health_snapshot: {error.message} (en {donde})"


def test_el_esquema_de_aquel_dia_sale_de_git_y_es_el_ESTRECHO() -> None:
    """La guarda del propio andamio: si el commit dejara de decir lo que se cree,
    los dos tests de abajo medirían otra cosa sin avisar."""
    estrofa = _esquema_que_servia_la_nube()["properties"]["packet_loss_pct"]
    assert estrofa.get("type") == "number", estrofa
    assert "anyOf" not in estrofa, "el padre de la relajación ya admitía null: revisa el commit"


def _release_de(ruta: str) -> str:
    """El directorio de release de una ruta de `/opt/takab/releases/<release>/…`.

    Se busca por el segmento `releases` y no por profundidad: el activo vive
    cuatro niveles más abajo hoy y el día que alguien mueva `audio/assets/` esto
    seguiría midiendo lo mismo en vez de comparar silenciosamente otra carpeta.
    """
    partes = PurePosixPath(ruta).parts
    assert "releases" in partes, f"ruta de audio fuera del árbol de releases: {ruta}"
    return partes[partes.index("releases") + 1]


def test_la_release_del_latido_cuadra_por_TRES_campos_LEIDOS_independientes() -> None:
    """La guarda contra el vector «refrescado» a medias, que es como se perdió antes.

    El `fw_version`, el `fw_running` y las rutas de `audio` se leyeron por
    separado del mismo mensaje, y las tres nombran la misma release; el
    `captured_at` cae 27 s después del sello horario que esa release lleva en su
    nombre — es literalmente el primer latido tras el arranque. Si alguien
    cambia uno solo de los cuatro (otra fecha «más bonita», otro SHA), esto se
    pone rojo en vez de dejar pasar una mezcla de dos latidos distintos, que fue
    exactamente el defecto que devolvió este trabajo.
    """
    payload, _meta = split_meta(_fixture()[0])

    assert payload["fw_version"] == payload["fw_running"], (
        "el gabinete tenía en disco y en ejecución el MISMO código: si difieren, "
        "este vector ya no es el latido de arranque de esa release"
    )
    directorios = {_release_de(payload["audio"][clave]) for clave in ("siren_path", "test_path")}
    assert len(directorios) == 1, f"las rutas de audio nombran dos releases: {directorios}"
    release = directorios.pop()

    sello, _, sha = release.partition("-")
    assert sha == payload["fw_version"], f"{release} no es la release de {payload['fw_version']}"

    arranque = datetime.strptime(sello, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    captura = datetime.fromisoformat(payload["captured_at"].replace("Z", "+00:00"))
    desde_el_arranque = (captura - arranque).total_seconds()
    assert 0 < desde_el_arranque < 300, (
        f"el latido se capturó {desde_el_arranque:.0f} s después de desplegar {release}: "
        "o no es el de arranque, o la hora y la release vienen de mensajes distintos"
    )


def test_el_gabinete_YA_traia_la_relajacion_que_la_nube_todavia_no_servia() -> None:
    """El desfase de despliegue, medido en git en vez de contado en un docstring.

    Es la tesis entera del incidente: el arreglo de `packet_loss_pct` llevaba una
    semana escrito, el gabinete lo corría y la nube no. Que `f19aa06` descienda de
    `d67d079` es lo que convierte eso en un hecho — sin ello, el rechazo sería
    simplemente un gabinete viejo, y no habría nada que arreglar en el despliegue.
    """
    corriendo = _fixture()[0]["fw_version"]
    assert corriendo != COMMIT_DE_LA_RELAJACION, "el vector dejó de distinguir release y arreglo"
    salida = subprocess.run(  # noqa: S603
        ["git", "merge-base", "--is-ancestor", COMMIT_DE_LA_RELAJACION, corriendo],  # noqa: S607
        cwd=_RAIZ,
        capture_output=True,
        text=True,
    )
    assert salida.returncode == 0, (
        f"{corriendo} NO contiene {COMMIT_DE_LA_RELAJACION}: entonces el gabinete no corría "
        f"el arreglo y el incidente no fue un desfase de despliegue{_PISTA_CLON}"
    )


def test_con_el_esquema_de_aquel_dia_el_vector_reproduce_la_razon_de_la_dlq() -> None:
    """Lo que ata este fichero al incidente del 2026-09-10, y por eso se mide.

    El mensaje ya no se puede releer: se leyó de la cola el 2026-09-12 y acto
    seguido se drenó, con su alarma de vuelta en `OK`. Lo que sí sobrevive es la
    razón del rechazo, y una razón de `jsonschema` es función del esquema y del
    payload. Con el esquema de aquel día —traído de git, no transcrito— este
    vector la reproduce **carácter por carácter**.

    Lo que esto prueba y lo que NO. Prueba que el vector es SUFICIENTE para
    producir esa razón; el test de abajo prueba que el `null` de
    `packet_loss_pct` es lo que la produce —quitarlo la hace desaparecer— y que
    ningún otro campo del vector chirriaba contra aquel esquema. No prueba, ni
    puede, lo que quedó detrás del truncamiento de aquella lectura: el resto de
    la lista de `relays` a partir de su cuarta fila, el `transition_reason` y dos
    de las tres claves `meta_*`. El JSON del vector los enumera uno a uno como
    completados, y esta suite no los desmiente ni los necesita.

    Si un día `jsonschema` reescribe su mensaje, esto se pone rojo: la salida
    correcta es re-verificar la procedencia y actualizar la cadena, nunca aflojar
    la comparación hasta que pase.
    """
    payload, _meta = split_meta(_fixture()[0])
    assert _razon(_esquema_que_servia_la_nube(), payload) == RAZON_DLQ


def test_el_null_de_packet_loss_pct_es_LO_QUE_mataba_al_latido() -> None:
    """La mitad que convierte la coincidencia en causa.

    Sin esto, el test de arriba pasaría igual con un vector en el que el `null`
    fuera uno de varios problemas — o en el que la razón viniera de otro sitio.
    Se mide en las dos direcciones sobre el esquema de aquel día:

      · con un número en `packet_loss_pct`, el MISMO vector validaba sin una sola
        queja ⇒ el `null` era necesario;
      · y ninguna de las otras tres sondas sin dato le hacía nada: ya eran
        `null`-ables antes de `d67d079`, así que la razón no podía nombrarlas.
    """
    esquema = _esquema_que_servia_la_nube()
    payload, _meta = split_meta(_fixture()[0])

    con_numero = payload | {"packet_loss_pct": 0.0}
    assert _razon(esquema, con_numero) is None, (
        "con un número ahí el latido TAMBIÉN caía: entonces la razón de la DLQ no "
        "la produce el null y este vector no es el del incidente"
    )
    # …y es el ÚNICO campo del vector que aquel esquema rechazaba: las otras tres
    # sondas siguen en `null` en `con_numero` y aun así valida.
    for campo in _fixture()[1]:
        if campo != "packet_loss_pct":
            assert con_numero[campo] is None, campo


# ------------------------------- el camino donde el mensaje murió de verdad


def _cuerpo_del_mensaje() -> str:
    """El cuerpo SQS tal cual: payload + los tres `meta_*` de la regla IoT."""
    return json.dumps(_fixture()[0])


def _borra_la_fila() -> None:
    """El latido de arranque tiene fecha FIJA y `device_health` es idempotente por
    `(ts, gateway_id)`: sin esto, una fila commiteada por la corrida anterior haría
    pasar al siguiente test sin escribir nada."""
    payload, _meta = split_meta(_fixture()[0])
    with psycopg.connect(_dsn()) as c:
        c.execute(
            "DELETE FROM device_health WHERE gateway_id = %s AND ts = %s",
            (GW, payload["captured_at"]),
        )
        c.commit()


@pytest.fixture
def sin_rastro_del_latido():
    """Deshace TODO lo que el latido commitea, no solo su fila.

    Medido: sin la segunda mitad, `test_health_version_absurda_se_rechaza_sin_tumbar_
    la_ingesta` se pone rojo en la suite y verde en aislado. El handler de salud
    escribe también la versión que el gabinete DECLARA (`gateways.fw_version` /
    `fw_running`, T-1.74 y T-2.70), y el vector trae `f19aa06`, la release que el
    Pi corría aquella noche: el handler la escribe, se queda commiteada y contamina
    al siguiente test. Se guardan los valores previos y se reponen: dejarlos en
    `NULL` sería asumir un estado inicial en vez de restaurarlo.
    """
    with psycopg.connect(_dsn()) as c:
        antes = c.execute(
            "SELECT fw_version, fw_running FROM gateways WHERE gateway_id = %s", (GW,)
        ).fetchone()
    _borra_la_fila()
    yield
    _borra_la_fila()
    if antes is not None:
        with psycopg.connect(_dsn()) as c:
            c.execute(
                "UPDATE gateways SET fw_version = %s, fw_running = %s WHERE gateway_id = %s",
                (*antes, GW),
            )
            c.commit()


@pytest.fixture
def consumidor(sqs, queues) -> SqsConsumer:  # noqa: F811 — fixtures reutilizadas
    """El worker REAL de `takab-dev-q-telemetry`: handlers reales, registro real,
    enrutado a DLQ real. Llamar al handler a pelo salta justamente la parte que
    falló."""
    return SqsConsumer(
        queues[0],
        queues[1],
        HANDLERS,
        Registry(_ingest_conn),
        _ingest_conn,
        Settings(),
        per_message_commit=True,
        sqs_client=sqs,
        wait_time_s=0,
    )


@pytest.fixture
def nube_del_2026_09_10(monkeypatch):
    """Pone en el validador de la ingesta el esquema que la nube servía aquel día.

    No se toca el fichero de `shared/schemas/`: se sustituye el validador que
    `contracts.loader.validate` consulta, que es por donde pasa el mensaje. Así el
    resto del camino —regla IoT, `split_meta`, resolución de identidad, enrutado a
    DLQ— es exactamente el de producción."""
    validadores = dict(loader._validators())
    validadores["health_snapshot"] = Draft202012Validator(_esquema_que_servia_la_nube())
    monkeypatch.setattr(loader, "_validators", lambda: validadores)


def test_con_la_nube_de_aquel_dia_el_latido_ACABA_en_la_cola_de_mensajes_muertos(
    flota_commiteada,  # noqa: F811 — fixture
    sqs,  # noqa: F811 — fixture
    queues,  # noqa: F811 — fixture
    consumidor: SqsConsumer,
    nube_del_2026_09_10,
    sin_rastro_del_latido,
) -> None:
    """El defecto, reproducido donde ocurrió: en el consumidor, no en el handler.

    El mensaje entra por la cola con su envoltorio `meta_*`, lo rechaza el
    validador de contrato y el consumidor lo manda a la DLQ con su motivo en
    `MessageAttributes.reason` — que es la cadena que quedó escrita el 2026-09-10 y
    la única prueba que sobrevive del incidente. Y no deja fila: el latido se
    perdió entero.
    """
    sqs.send_message(QueueUrl=queues[0], MessageBody=_cuerpo_del_mensaje())

    stats = consumidor.process_once()

    assert stats["n_reject"] == 1, stats
    muertos = sqs.receive_message(
        QueueUrl=queues[1], MaxNumberOfMessages=10, MessageAttributeNames=["All"]
    ).get("Messages", [])
    assert len(muertos) == 1, "el latido no llegó a la DLQ: el camino medido no es el que falló"
    atributos = muertos[0]["MessageAttributes"]
    assert atributos["reason"]["StringValue"] == RAZON_DLQ
    assert atributos["original_topic"]["StringValue"] == "takab/health"

    payload, _meta = split_meta(_fixture()[0])
    with psycopg.connect(_dsn()) as check:
        fila = check.execute(
            "SELECT 1 FROM device_health WHERE gateway_id = %s AND ts = %s",
            (GW, payload["captured_at"]),
        ).fetchone()
    assert fila is None, "el latido rechazado dejó fila: entonces no se perdió y no es el caso"


def test_con_el_esquema_de_HOY_el_MISMO_mensaje_entra_y_deja_la_fila_con_NULL(
    flota_commiteada,  # noqa: F811 — fixture
    sqs,  # noqa: F811 — fixture
    queues,  # noqa: F811 — fixture
    consumidor: SqsConsumer,
    sin_rastro_del_latido,
) -> None:
    """El después, por el MISMO camino y con el MISMO cuerpo: nada de DLQ, y la
    fila con NULL donde el gabinete dijo «sin dato».

    Es la mitad que hace falsable a la otra: si alguien «arreglara» el contrato
    aceptándolo todo y guardando ceros, aquélla seguiría verde y ésta no.
    """
    sqs.send_message(QueueUrl=queues[0], MessageBody=_cuerpo_del_mensaje())

    stats = consumidor.process_once()

    assert stats["n_ok"] == 1 and stats["n_reject"] == 0, stats
    assert _n_messages(sqs, queues[1]) == 0, "el latido de arranque volvió a la DLQ"

    payload, sondas = split_meta(_fixture()[0])[0], _fixture()[1]
    with psycopg.connect(_dsn()) as check, check.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT packet_loss_pct, mqtt_rtt_ms, battery_pct, battery_min_left, reason "
            "FROM device_health WHERE gateway_id = %s AND ts = %s",
            (GW, payload["captured_at"]),
        )
        fila = cur.fetchone()
    assert fila is not None, "el mensaje se aceptó pero no dejó fila en device_health"
    columna = {"ups_runtime_s": "battery_min_left"}
    for campo in sondas:
        destino = columna.get(campo, campo)
        assert fila[destino] is None, (
            f"{campo} llegó «sin dato» y la base guardó {fila[destino]!r}: "
            "el SOC lo pintaría como una medición"
        )
    assert fila["reason"] == "heartbeat"


def test_y_con_el_esquema_PUBLICADO_hoy_esa_razon_ya_no_existe() -> None:
    """La otra mitad del antes/después, sobre el mismo vector y el mismo camino."""
    mensaje, _sondas = _fixture()
    payload, _meta = split_meta(mensaje)
    validate("health_snapshot", payload)  # no lanza ⇒ el latido entra
