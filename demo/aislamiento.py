"""El aislamiento de la demo, IMPUESTO en vez de supuesto (T-5.08).

Antes de esta ficha la demo no despertaba a nadie por una razón frágil: **el guion
no lanzaba el worker de notificación**. Eso no es un aislamiento, es una
coincidencia de arranque — el día que alguien corriera la demo con un
`make soc-local` a medio apagar (que sí levanta el worker), la cascada saldría por
los canales configurados hacia teléfonos reales.

Aquí el aislamiento pasa a ser un ESTADO del sistema, no una omisión del guion:

1. **Se enciende el modo demostración** (`T-5.02 · D-27`) del cliente de la demo.
   Es el interruptor de producto que suprime **las salidas de la nube** —entregas
   por cualquier canal y comandos de actuador firmados— y **no puede tocar el
   gabinete**: el reflejo SASMEX→sirena no se entera de que la nube esté jugando
   (regla de oro 1). O sea que la demo sigue demostrando de verdad la protección
   local, que es lo único que un cliente necesita ver funcionando.
2. **Se comprueba que quedó vivo** leyendo la ventana con la MISMA función que
   consulta el worker (`ventana_viva_sync`). Encenderlo y no verificarlo sería
   volver a suponer.
3. **Al terminar se cuenta lo entregado.** Si algo salió por un canal real
   mientras el modo estaba puesto, la demo lo dice: es la prueba de que la
   supresión funcionó, y no la promesa de que debería.

Lo que este módulo NO hace, a propósito: apagar el modo al final. Lo apaga un
evento real del cliente (`apagar_por_evento_real`), y dejarlo puesto tras la demo
es el estado seguro — la ventana vence sola.

[T-5.29] **La excepción, y por qué existe.** `levantar()` apaga el modo para una
escena concreta y `imponer()` lo vuelve a poner. La necesita la escena del
simulacro: `D-27` declara que el modo suprime **notificaciones y comandos
firmados**, y un simulacro ES un comando firmado, así que con el modo puesto no
baja nada. La escena aprovecha eso —enseña primero la supresión, con su fila de
auditoría— y solo entonces levanta la ventana para poder recorrer el simulacro
entero. Lo que NO se hace es tocar la regla: `issue_signed_command` sigue
suprimiendo igual, y el recuento final de entregas reales cubre también esa
ventana, así que la prueba del aislamiento sale REFORZADA y no debilitada.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import psycopg

from takab_api.db.engine import get_engine
from takab_api.demo_mode import apagar, encender, ventana_viva_sync

#: Duración de la ventana. Una demo larga cabe de sobra y el tope lo impone
#: `ventana_maxima`; pedir más sería pedir que el sistema esté mudo más rato del
#: que dura la exposición.
VENTANA_S = 3600

#: `demo_mode.enabled_by` es una columna **uuid** (sin FK), y el router pasa ahí
#: el `sub` del token. Como el guion no tiene sesión, se usa un uuid FIJO y
#: reconocible: quien lea la bitácora ve quién encendió el modo y que no fue una
#: persona. Escribir `"demo:run.py"` reventaba con `invalid input syntax for type
#: uuid` — el mismo valor viaja al `actor` de la auditoría, que sí es texto.
_ACTOR = "de300000-0000-0000-0000-0000000de300"
_NOTA = "guion de demostracion (demo/run.py)"


def _tenant_uuid(conn: psycopg.Connection, code: str) -> str:
    fila = conn.execute("SELECT tenant_id FROM tenants WHERE code = %s", (code,)).fetchone()
    if fila is None:
        raise RuntimeError(f"demo: el cliente {code!r} no existe en la DB. ¿Falta `make demo-db`?")
    return str(fila[0])


def imponer(conn: psycopg.Connection, *, tenant_code: str) -> str:
    """Enciende el modo demostración y COMPRUEBA que quedó vivo. Devuelve el uuid.

    Falla ruidosamente: una demo que arranca sin el interruptor puesto es
    exactamente lo que esta ficha existe para impedir.
    """
    tenant_id = _tenant_uuid(conn, tenant_code)

    async def _encender() -> None:
        engine = get_engine()
        async with engine.begin() as ac:
            await encender(ac, tenant_id=tenant_id, actor=_ACTOR, segundos=VENTANA_S, note=_NOTA)

    asyncio.run(_encender())

    ventana = ventana_viva_sync(conn, tenant_id=tenant_id, now=datetime.now(tz=UTC))
    if ventana is None:
        raise RuntimeError(
            "demo: se encendió el MODO DEMOSTRACIÓN y la ventana no quedó viva. "
            "Sin él, la cascada de notificación saldría por los canales "
            "configurados: la demo NO arranca así."
        )
    return tenant_id


def levantar(conn: psycopg.Connection, *, tenant_code: str) -> str:
    """[T-5.29] Apaga la ventana y COMPRUEBA que se apagó. Devuelve el uuid.

    Es la mitad simétrica de :func:`imponer` y se usa para una sola escena. Falla
    ruidosamente por la misma razón que su gemela: correr la escena del simulacro
    creyendo que el modo está apagado, cuando sigue puesto, produce cero comandos
    y un diagnóstico que apunta al transporte.
    """
    tenant_id = _tenant_uuid(conn, tenant_code)

    async def _apagar() -> None:
        engine = get_engine()
        async with engine.begin() as ac:
            await apagar(ac, tenant_id=tenant_id, actor=_ACTOR, motivo="escena de simulacro")

    asyncio.run(_apagar())

    if ventana_viva_sync(conn, tenant_id=tenant_id, now=datetime.now(tz=UTC)) is not None:
        raise RuntimeError(
            "demo: se apagó el MODO DEMOSTRACIÓN y la ventana sigue viva. La escena "
            "del simulacro no puede correr: todo comando firmado se suprimiría."
        )
    return tenant_id


def entregas_reales(conn: psycopg.Connection) -> list[tuple]:
    """Notificaciones que SALIERON de verdad. Vacío es la prueba del aislamiento.

    `sent` es el único estado que significa entrega; `simulated` es lo que produce
    un canal sin credenciales —y por eso no vale como aislamiento: desaparece justo
    en el entorno donde se haría la demostración—.
    """
    return conn.execute(
        "SELECT channel, count(*) FROM notification_jobs WHERE status = 'sent' GROUP BY channel"
    ).fetchall()
