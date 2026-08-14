"""T-2.138 · Un rechazo REENTREGADO deja una fila; dos rechazos distintos, dos.

`T-2.136` midió los 7 caminos de la ingesta contra una reentrega real de SQS: 6
quedan en una fila (PK natural, UPSERT por `event_uuid`, guarda monotónica) y el
séptimo —`ingest_reject`— dejaba **dos**, porque `audit_log` es
`GENERATED ALWAYS AS IDENTITY` + `ts DEFAULT now()` y **no tiene clave natural**.
La tabla es append-only por trigger y **no se poda jamás** (regla de oro 11): el
renglón de más es permanente.

Lo que NO se podía hacer, y es la mitad difícil de la ficha:

    una clave sobre (tenant, actor, verb, object, meta) COLAPSA rechazos
    genuinamente distintos, que es peor que duplicar uno.

Dos mensajes falsificados distintos del mismo gabinete pueden producir la misma
razón (`station desconocida para el gateway: 'XYZ'` sale igual todas las veces),
así que una clave permanente sobre el contenido borraría para siempre el segundo
rechazo, el tercero y el de dentro de un año. Por eso la clave lleva **cubeta de
tiempo**: la huella identifica el HECHO, la cubeta lo acota a la ventana en la
que una reentrega es físicamente posible. Fuera de esa ventana, el mismo rechazo
vuelve a dejar su fila.

Orden del fichero:

1. **La reentrega** — el 2 medido por `T-2.136` pasa a 1.
2. **Lo que NO se colapsa** — el criterio que hizo que `T-2.136` no lo arreglara.
3. **La ventana** — de dónde sale el número y por qué dos cubetas y no el reloj.
4. **El respaldo físico** — el índice único parcial, que actúa cuando la lectura
   no puede ver la fila (dos entregas concurrentes, cada una en su transacción).
5. **Lo que esta huella NO puede distinguir**, declarado en voz alta.
"""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import takab_api.audit as audit_mod
from conftest import _dsn
from takab_api.audit import (
    DEDUPE_VERBS,
    VENTANA_REENTREGA_S,
    audit,
    audit_async,
    dedupe_digest_for,
)

TENANT = "11111111-1111-1111-1111-111111111111"
OTRO_TENANT = "22222222-2222-2222-2222-222222222222"

_TF_COLAS = Path(__file__).resolve().parents[2] / "infra/terraform/modules/messaging/main.tf"
_INGEST_MAIN = Path(__file__).resolve().parents[1] / "src/takab_api/ingest/__main__.py"


def _sonda() -> str:
    """Prefijo de `object` único por test: la suite comparte base y `audit_log`
    no se puede vaciar (append-only por trigger), así que contar por prefijo es
    lo único que no arrastra filas de otra prueba."""
    return f"sonda-{uuid.uuid4().hex}"


def _rechazo(prefijo: str, **kw) -> dict:
    """La fila EXACTA que escribe `_audit_reject` (ingest/handlers.py)."""
    fila = {
        "tenant_id": TENANT,
        "actor": "system:ingest",
        "verb": "ingest_reject",
        "obj": f"{prefijo}@takab/events",
        "meta": {
            "reason": "tenant mismatch: payload='tenant-evil' registro='acme'",
            "principal": "gw-dev-0001",
        },
    }
    fila.update(kw)
    return fila


def _contar(conn: psycopg.Connection, prefijo: str) -> int:
    return conn.execute(
        "SELECT count(*) FROM audit_log WHERE starts_with(object, %s)", (prefijo,)
    ).fetchone()[0]


# ============================================================ 1 · la reentrega


def test_la_reentrega_del_mismo_rechazo_deja_una_sola_fila(conn: psycopg.Connection) -> None:
    """El hallazgo de `T-2.136`, invertido. Dos entregas del MISMO mensaje
    falsificado producen la misma fila byte a byte; la segunda ya no se escribe."""
    prefijo = _sonda()
    fila = _rechazo(prefijo)

    audit(conn, **fila)
    audit(conn, **fila)

    assert _contar(conn, prefijo) == 1


def test_la_huella_solo_se_calcula_para_los_verbos_del_censo(conn: psycopg.Connection) -> None:
    """El resto de la bitácora no cambia de comportamiento. Un `export` repetido
    son dos hechos (dos descargas), no una reentrega: si esto dedujera, la ficha
    habría convertido un renglón de más en pruebas de compliance perdidas."""
    assert "export" not in DEDUPE_VERBS, "cambiar el censo cambia lo que se puede perder"
    prefijo = _sonda()

    for _ in range(2):
        audit(
            conn,
            tenant_id=TENANT,
            actor="user:ana",
            verb="export",
            obj=f"{prefijo}:evidencia",
            meta={"key": "s3://x"},
        )

    assert _contar(conn, prefijo) == 2
    assert dedupe_digest_for(verb="export", tenant_id=TENANT, actor="a", obj="b", meta={}) is None


# ================================================ 2 · lo que NO se puede colapsar


def test_los_rechazos_genuinamente_distintos_no_se_colapsan(conn: psycopg.Connection) -> None:
    """**El criterio por el que `T-2.136` NO lo arregló.** Cada eje del rechazo
    —la razón, el publicador, el cliente, el objeto— produce huella distinta, así
    que cuatro rechazos distintos dejan cuatro renglones aunque lleguen en el
    mismo segundo."""
    prefijo = _sonda()
    base = _rechazo(prefijo)

    audit(conn, **base)
    audit(conn, **{**base, "meta": {**base["meta"], "reason": "site mismatch: 'site-x'"}})
    audit(conn, **{**base, "meta": {**base["meta"], "principal": "gw-dev-0002"}})
    audit(conn, **{**base, "tenant_id": OTRO_TENANT})
    audit(conn, **{**base, "obj": f"{prefijo}@takab/telemetry"})

    assert _contar(conn, prefijo) == 5


def test_un_rechazo_repetido_fuera_de_la_ventana_vuelve_a_dejar_fila(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El mismo gabinete, el mismo mensaje malo, MESES después: es un hecho nuevo
    y tiene que verse. Una clave sin cubeta lo habría borrado para siempre.

    Se estrecha la ventana en vez de esperar 450 s: la cubeta es un parámetro,
    no una constante escrita en el SQL, justo para que esto sea comprobable."""
    monkeypatch.setattr(audit_mod, "VENTANA_REENTREGA_S", 0.2)
    prefijo = _sonda()
    fila = _rechazo(prefijo)

    audit(conn, **fila)
    time.sleep(0.5)  # > 2 cubetas ⇒ fuera de la ventana por construcción
    audit(conn, **fila)

    assert _contar(conn, prefijo) == 2


# ==================================================== 3 · de dónde sale la ventana


def _colas_de_la_ingesta() -> set[str]:
    """Las colas que consume el worker de ingesta, leídas de su propio CLI."""
    texto = _INGEST_MAIN.read_text(encoding="utf-8")
    m = re.search(r'"--queue",\s*choices=\(([^)]*)\)', texto)
    assert m, (
        f"no se pudo leer qué colas consume la ingesta en {_INGEST_MAIN}: el número de la "
        "ventana se estaría derivando de nada"
    )
    return set(re.findall(r'"([a-z_]+)"', m.group(1)))


def _visibilidades() -> dict[str, int]:
    texto = _TF_COLAS.read_text(encoding="utf-8")
    valores = {
        nombre: int(seg)
        for nombre, seg in re.findall(r"(\w+)\s*=\s*\{\s*visibility_timeout\s*=\s*(\d+)", texto)
    }
    assert valores, f"no se pudo leer la visibilidad real de {_TF_COLAS}"
    return valores


def _max_receive_count() -> int:
    texto = _TF_COLAS.read_text(encoding="utf-8")
    valores = {int(m) for m in re.findall(r"maxReceiveCount\s*=\s*(\d+)", texto)}
    assert len(valores) == 1, (
        f"maxReceiveCount no es único en {_TF_COLAS}: {sorted(valores)} — la ventana no puede "
        "derivarse de un número que depende de la cola"
    )
    return valores.pop()


def test_la_ventana_se_deriva_del_terraform_real_no_de_un_numero_elegido() -> None:
    """El horizonte de reentrega no es una preferencia: es
    `maxReceiveCount × VisibilityTimeout` de las colas que consume la ingesta,
    leído del Terraform de verdad (mismo patrón que `T-2.136`). Si alguien sube
    la visibilidad de `q-telemetry`, este test cae y obliga a mover la ventana."""
    colas = _colas_de_la_ingesta()
    visibilidades = _visibilidades()
    faltan = colas - set(visibilidades)
    assert not faltan, f"colas de la ingesta sin visibilidad en el Terraform: {sorted(faltan)}"

    peor = max(visibilidades[c] for c in colas)
    assert VENTANA_REENTREGA_S == peor * _max_receive_count(), (
        f"la ventana ({VENTANA_REENTREGA_S} s) dejó de ser el horizonte de reentrega real "
        f"({peor} s × {_max_receive_count()} recepciones)"
    )


def _cubeta(t: float, ancho: float) -> int:
    """La misma aritmética que el SQL: `floor(epoch / ancho)`."""
    return int(t // ancho)


def test_dos_entregas_dentro_de_la_ventana_caen_en_cubetas_contiguas() -> None:
    """**Por qué se mira la cubeta anterior y no el reloj.** Una sola cubeta deja
    un agujero de borde: dos entregas separadas 30 s pueden caer a los dos lados
    de la frontera y las dos escribirían. Mirando `cubeta` y `cubeta - 1` el
    agujero desaparece por construcción: cualquier par separado menos que el
    ancho está en la misma cubeta o en la contigua.

    El precio, medido aquí y declarado: la ventana efectiva está entre una y dos
    veces el ancho — nunca menos que el horizonte de reentrega (que es lo que hay
    que garantizar) y nunca más del doble."""
    ancho = float(VENTANA_REENTREGA_S)
    for arranque in (0.0, ancho - 0.001, ancho * 7 + 13.7):
        for delta in (0.0, 1.0, ancho / 2, ancho - 0.002):
            c0 = _cubeta(arranque, ancho)
            c1 = _cubeta(arranque + delta, ancho)
            assert c1 - c0 in (0, 1), (
                f"una reentrega a los {delta} s cayó {c1 - c0} cubetas más allá: el agujero de "
                "borde vuelve a existir"
            )

    lejos = _cubeta(2 * ancho + 1.0, ancho)
    assert lejos - _cubeta(0.0, ancho) >= 2, "más allá del doble del ancho ya no se colapsa"


async def test_el_frente_async_deduplica_igual_que_el_sync() -> None:
    """Los DOS frentes de `audit.py` escriben la misma fila o el veto del escritor
    único sería decorativo: un verbo dedupeado que entrara por los routers
    volvería a duplicar y nadie se enteraría. Hoy `ingest_reject` solo entra por
    el frente sync; esto fija que el otro se comporta igual, antes de que haga
    falta."""
    prefijo = _sonda()
    fila = _rechazo(prefijo)
    assert dedupe_digest_for(**fila) is not None, "el arnés dejó de usar un verbo dedupeado"

    # `_dsn()` devuelve la forma psycopg cruda; SQLAlchemy necesita el driver
    # explícito o cae en psycopg2, que este proyecto no instala.
    engine = create_async_engine(_dsn().replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        async with engine.connect() as c:
            txn = await c.begin()
            try:
                await audit_async(c, **fila)
                await audit_async(c, **fila)
                n = (
                    await c.execute(
                        text("SELECT count(*) FROM audit_log WHERE starts_with(object, :p)"),
                        {"p": prefijo},
                    )
                ).scalar_one()
            finally:
                await txn.rollback()
    finally:
        await engine.dispose()

    assert n == 1


# ============================================ 4 · el respaldo físico (la carrera)


def test_el_indice_unico_parcial_es_el_respaldo_cuando_la_lectura_no_ve_la_fila(
    conn: psycopg.Connection,
) -> None:
    """La comprobación previa lee `audit_log`; dos entregas CONCURRENTES —el modo
    de fallo que abrió `T-2.136`: una consulta que se pasa del `VisibilityTimeout`
    y SQS reentrega mientras la primera sigue viva— corren en transacciones
    distintas y ninguna ve la fila de la otra hasta el commit.

    Lo que cierra ese hueco no es la lectura: es el índice. Se comprueba a pelo,
    insertando dos veces la misma huella en la misma cubeta."""
    huella = uuid.uuid4().hex
    sql = (
        "INSERT INTO audit_log (tenant_id, actor, verb, object, meta, "
        "dedupe_digest, dedupe_bucket) VALUES (%s,'system:ingest','ingest_reject',%s,'{}',%s,%s)"
    )
    conn.execute(sql, (TENANT, _sonda(), huella, 1))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(sql, (TENANT, _sonda(), huella, 1))


def test_el_indice_no_es_un_colapso_permanente(conn: psycopg.Connection) -> None:
    """La misma huella en OTRA cubeta entra sin discutir: el índice acota la
    ventana, no borra el hecho. Sin esta mitad, el arreglo sería exactamente el
    que `T-2.136` rechazó por escrito."""
    huella = uuid.uuid4().hex
    prefijo = _sonda()
    sql = (
        "INSERT INTO audit_log (tenant_id, actor, verb, object, meta, "
        "dedupe_digest, dedupe_bucket) VALUES (%s,'system:ingest','ingest_reject',%s,'{}',%s,%s)"
    )
    conn.execute(sql, (TENANT, f"{prefijo}:a", huella, 1))
    conn.execute(sql, (TENANT, f"{prefijo}:b", huella, 99))

    assert _contar(conn, prefijo) == 2


def test_la_huella_y_la_cubeta_van_juntas_o_no_van(conn: psycopg.Connection) -> None:
    """Media clave es peor que ninguna: una fila con huella y sin cubeta no la
    vigila el índice parcial y se cuela. Lo impide la base, no el llamador."""
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO audit_log (tenant_id, actor, verb, object, dedupe_digest) "
            "VALUES (%s,'system:ingest','ingest_reject',%s,%s)",
            (TENANT, _sonda(), uuid.uuid4().hex),
        )


# ================================ 5 · lo que esta huella NO puede distinguir


def test_declarado_dos_rechazos_identicos_en_la_ventana_son_indistinguibles(
    conn: psycopg.Connection,
) -> None:
    """**El punto ciego, medido y nombrado en vez de escondido.**

    La fila de `audit_log` NO lleva id del mensaje: `_audit_reject` escribe razón
    y `principal`, y la razón la compone el cross-check de identidad. Así que dos
    mensajes DISTINTOS que produzcan evidencia byte-idéntica dentro de la ventana
    —el mismo gabinete reenviando el mismo payload malo— se cuentan como uno.

    No es un descuido: desde `audit.py` no hay forma de distinguirlos, porque lo
    que los distingue (el cuerpo del mensaje, su `meta_ts_iot`) se queda en
    `ingest/handlers.py` y nunca llega aquí. Si algún día hace falta CONTAR
    rechazos repetidos, el arreglo es que el id del mensaje viaje hasta la fila —
    no aflojar la clave. Mientras tanto, el hecho («este gabinete manda payloads
    con tenant falsificado») sí queda, con su primera fecha, y no se poda jamás."""
    prefijo = _sonda()
    fila = _rechazo(prefijo)

    audit(conn, **fila)  # mensaje A
    audit(conn, **fila)  # mensaje B, distinto, evidencia idéntica

    assert _contar(conn, prefijo) == 1, (
        "si esto vale 2, la huella dejó de colapsar lo que no puede distinguir — y entonces "
        "la reentrega tampoco se está colapsando"
    )
