"""[T-7.50] Lo que el grant PUEDE decidir, y lo que sólo el worker puede.

De `T-7.40`: un gabinete subió 192 KB de evidencia cuyo incidente no existía, el
worker respondió «aún no ingerido» una y otra vez, y el mensaje acabó en una DLQ
cuya alarma está muda (`T-7.41`). El objeto quedó en S3 sin que nada dijera por
qué.

## ⚠️ La ficha pedía que el grant RECHAZARA, y eso habría hecho más daño

Rechazar en el grant no acaba con el bucle: **lo mueve al gabinete, donde nada lo
acota.** Un grant denegado hoy es indistinguible de uno perdido —no se publica
nada—, así que el edge espera 30 s, conserva el pendiente y, desde `T-7.40`, el
barrido lo reintenta cada 30 s **para siempre**. Y cada reintento vuelve a
extraer la ventana del ring: si el rechazo persiste hasta que la ventana se sale
del anillo, la evidencia de un sismo real **se destruye**, contada en el panel
casi como un éxito.

Peor aún: en una reconexión la evidencia adelanta **legítimamente** a su evento
—`_on_online` la dispara al instante mientras el spool del `LocalEvent` espera un
jitter de hasta 120 s, y los dos caen en la misma cola sin orden garantizado—, así
que rechazar por «el incidente no existe» tira evidencia buena.

## Lo que sí se hizo

* **El grant comprueba la FORMA**, que es el único «nunca» que puede conocer sin
  base y sin tiempo: `incidents.event_uuid` es de tipo `uuid`, así que un
  `event_id` que no lo sea jamás podrá casar con ninguno.
* **El worker decide el «nunca»**, que es donde hay reintentos contados: al
  agotarse las reentregas de la cola, la huérfana se **DECLARA** en `audit_log`
  —la tabla que la purga operativa conserva por nombre— en vez de caer a la DLQ
  en silencio. La evidencia **no se borra** (regla de oro 11): se dice que lo es.
"""

from __future__ import annotations

import uuid

import pytest

from takab_api.backfill.grants import canonical_key

TENANT = "d0000000-0000-0000-0000-0000000000aa"
SHA = "a" * 64


def _payload(event_id: str, mode: str = "evidence") -> dict:
    return {
        "mode": mode,
        "event_id": event_id,
        "sha256": SHA,
        "ts_from": "2026-09-15T00:00:00+00:00",
        "ts_to": "2026-09-15T00:03:00+00:00",
    }


class _Ctx:
    tenant_id = TENANT


# ─────────────────────────── lo que el grant PUEDE decidir: la forma


@pytest.mark.parametrize(
    "event_id",
    [
        pytest.param("ab12cd34ef567890ab12cd34ef567890", id="hex-del-edge"),
        pytest.param("ab12cd34-ef56-7890-ab12-cd34ef567890", id="canonica-con-guiones"),
    ],
)
def test_las_DOS_escrituras_reales_de_un_event_id_pasan(event_id: str) -> None:
    """Son las que emite el gabinete y las que Postgres acepta. Nada más."""
    assert canonical_key(_payload(event_id), _Ctx(), "thing") is not None


@pytest.mark.parametrize(
    "event_id",
    [
        pytest.param("../../../etc/passwd", id="travesia-de-directorios"),
        pytest.param("urn:uuid:ab12cd34-ef56-7890-ab12-cd34ef567890", id="urn"),
        pytest.param("{ab12cd34-ef56-7890-ab12-cd34ef567890}", id="entre-llaves"),
        pytest.param("1' OR '1'='1", id="inyeccion"),
        pytest.param("a" * 10_000, id="clave-de-10-KB"),
        pytest.param("ev-abc", id="etiqueta-cualquiera"),
        pytest.param("", id="vacio"),
    ],
)
def test_lo_que_NUNCA_podra_ser_un_incidente_no_llega_a_S3(event_id: str) -> None:
    """Estas siete formas **pasaban el contrato y producían key**, medido.

    No es «todavía no»: `incidents.event_uuid` es de tipo `uuid`, así que ninguna
    podrá casar jamás. Y dos de ellas son algo peor que una huérfana: una key con
    `../` no aterriza donde el bucket notifica —el objeto existiría y el incidente
    no se enteraría— y una de 10 KB es una key que nadie puede buscar.
    """
    assert canonical_key(_payload(event_id), _Ctx(), "thing") is None


def test_el_CCTV_exige_la_misma_forma() -> None:
    """Comparte prefijo y bucket con el miniSEED: no puede ser más laxo."""
    bueno = canonical_key(_payload("ab12cd34ef567890ab12cd34ef567890", "cctv_clip"), _Ctx(), "t")
    assert bueno is not None
    assert canonical_key(_payload("../fuera", "cctv_clip"), _Ctx(), "t") is None


# ──────────────────── lo que sólo el worker puede decidir: el «nunca»


def test_el_worker_DECLARA_la_huerfana_al_agotarse_las_reentregas() -> None:
    """El invariante en su forma comprobable, sin nube.

    `_process_evidence` con `ultimo_intento=True` y sin incidente tiene que
    DECLARAR —no callar— y devolver REJECT, para que el mensaje deje de dar
    vueltas. Con `ultimo_intento=False` sigue siendo RETRY.
    """
    import inspect

    from takab_api.backfill import objects

    fuente = inspect.getsource(objects._process_evidence)
    assert "ultimo_intento" in fuente, "el manejador no distingue el último intento"
    assert "evidence_orphan_declared" in fuente, (
        "la huérfana no se DECLARA: hasta T-7.50 el mensaje caía a la DLQ en "
        "silencio y la alarma que la vigila está muda (T-7.41)"
    )
    assert "conn.rollback()" in fuente
    # ⚠️ Y la carrera legítima sigue viva: ANTES del último intento es RETRY. Si
    # esto se volviera REJECT a secas, una reconexión con el spool por delante
    # tiraría evidencia sísmica buena — la evidencia puede adelantar a su evento.
    assert "if not ultimo_intento:" in fuente, (
        "el RETRY dejó de estar condicionado: la evidencia que llega antes que su "
        "evento se rechazaría en el primer intento"
    )


def test_el_tope_de_reentregas_se_LEE_de_la_cola() -> None:
    """Y no se teclea: el número lo fija el terraform.

    Un número copiado a mano es dos sitios opinando sobre lo mismo — el día que
    suba el del terraform, el código declararía huérfanas una vuelta antes.
    """
    import inspect

    from takab_api.backfill import consumer

    fuente = inspect.getsource(consumer.BackfillConsumer._tope_de_recepciones)
    assert "RedrivePolicy" in fuente and "maxReceiveCount" in fuente
    assert "ApproximateReceiveCount" in inspect.getsource(consumer.BackfillConsumer.process_once), (
        "sin pedir el contador, la cota de la cola es ciega para el código"
    )


def test_la_evidencia_declarada_NO_se_borra() -> None:
    """Regla de oro 11, comprobada sobre el texto del arreglo.

    Declararla es decir que es huérfana, no quitarla: el objeto sigue en S3 y su
    key queda escrita en `audit_log`, que es lo que la purga operativa conserva
    POR NOMBRE — al revés que `evidence_objects`.
    """
    import inspect

    from takab_api.backfill import objects

    fuente = inspect.getsource(objects._process_evidence)
    assert "delete_object" not in fuente and "DELETE FROM" not in fuente.upper()
    assert "obj=key" in fuente, "la declaración no lleva la key: el objeto quedaría sin rastro"


def test_uuid_valido_de_verdad_no_se_rechaza() -> None:
    """La contraprueba de la guarda de forma: no vale rechazarlo todo."""
    for _ in range(50):
        assert canonical_key(_payload(uuid.uuid4().hex), _Ctx(), "t") is not None
        assert canonical_key(_payload(str(uuid.uuid4())), _Ctx(), "t") is not None
