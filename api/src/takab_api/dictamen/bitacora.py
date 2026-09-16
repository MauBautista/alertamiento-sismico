"""[T-7.22] Los rótulos de `incident_actions` para el papel, y de dónde salen.

La cronología del informe se dibujaba con el `kind` CRUDO de la base: el papel que
el cliente se lleva decía `gas_closed` donde la pantalla dice «VÁLVULAS DE GAS
CERRADAS». Es el defecto que `T-2.127` y `T-2.144` ya pagaron dos veces en la
consola, cobrado una tercera en un documento firmado.

## Por qué el registro está AQUÍ y no se lee de `bms.ts`

El registro vivo es `shared/sdk-ts/src/bms.ts`, y la tentación era leerlo desde
Python como ya hace `tests/api/test_incident_action_kinds.py`. **Muere en la
nube:** `api/Dockerfile` copia `api/*`, `shared/schemas` y `shared/glossary`, y no
copia `shared/sdk-ts`. Sería verde en CI y un `FileNotFoundError` —o, peor, el
`kind` en crudo— en el documento que se entrega. Es exactamente el modo de fallo
que el propio precedente advierte, con letra: allí el registro se lee «**en tiempo
de test**», y por eso no añade dependencia de build de `api/` sobre `web/`.

Así que esta tabla es un ESPEJO, no una segunda fuente:
`tests/dictamen/test_bitacora.py` la deriva de `bms.ts` con el mismo parseo y
exige **igualdad de conjuntos**. Divergir pone CI en rojo en el mismo commit.

## Un `kind` sin rótulo se DECLARA, no se imprime en crudo

`incident_actions` es append-only y exenta de poda, así que la tabla real puede
traer verbos que este registro no conozca —una fila vieja, un productor nuevo—.
El precedente rechaza con razón un registro Python que pretenda ser COMPLETO: su
completitud descansaría en una convención. Aquí no se pretende. Lo que no se sabe
rotular se imprime con su identificador **y con el aviso de que no tiene rótulo**,
que es la diferencia entre un dato crudo y un dato crudo declarado como tal.
"""

from __future__ import annotations

#: `kind` de `incident_actions` → lo que ese verbo dice en castellano.
#:
#: Espejo EXACTO de `INCIDENT_ACTION_KINDS[kind].logLabel` y de
#: `ACTUATOR_CHANNELS[canal].label` + el estado que ese `kind` afirma, en
#: `shared/sdk-ts/src/bms.ts`. No se edita a mano sin mirar allí: la prueba lo
#: impide en el mismo commit.
#:
#: Los `legacyKinds` (`gas_valve_close`, `elevator_recall`, `door_release`) van
#: incluidos por la misma razón que en la consola: `incident_actions` es
#: append-only y exenta de poda, así que una fila antigua no puede volver al
#: identificador en crudo.
ROTULOS: dict[str, str] = {
    "ack": "ACUSE DE OPERADOR",
    "close": "INCIDENTE CERRADO",
    "damage_people_at_risk": "PERSONAS EN RIESGO REPORTADAS EN SITIO",
    "dictamen": "DICTAMEN EMITIDO",
    "dictamen_request": "DICTAMEN SOLICITADO",
    "dictamen_signed": "DICTAMEN FIRMADO · HABITABLE, REINGRESO AUTORIZADO",
    "door_release": "RETENEDORES DE PUERTA LIBERADOS",
    "door_released": "RETENEDORES DE PUERTA LIBERADOS",
    "door_retained": "RETENEDORES DE PUERTA RETENIDOS",
    "elevator_recall": "ELEVADORES RETORNADOS",
    "elevator_recalled": "ELEVADORES RETORNADOS",
    "elevator_released": "ELEVADORES LIBERADOS",
    "epicenter_relocate": "EPICENTRO REUBICADO",
    "fail_open": "INCIDENTE ABIERTO SIN ENLACE CON EL GABINETE · NADA CONFIRMADO EN SITIO",
    "gas_closed": "VÁLVULAS DE GAS CERRADAS",
    "gas_open": "VÁLVULAS DE GAS ABIERTAS",
    "gas_valve_close": "VÁLVULAS DE GAS CERRADAS",
    "headcount_closed": "PASE DE LISTA CERRADO",
    "headcount_notify": "AVISO A NO REPORTADOS · HAY PERSONAS SIN REPORTARSE",
    "in_review": "INCIDENTE EN REVISIÓN",
    "notify_blocked_demo": "NOTIFICACIÓN SUPRIMIDA · MODO DEMOSTRACIÓN ACTIVO",
    "notify_delivered": "NOTIFICACIÓN ENTREGADA EN EL DISPOSITIVO",
    "notify_failed": "NOTIFICACIÓN NO ENTREGADA",
    "notify_no_recipients": "NOTIFICACIÓN SIN DESTINATARIOS · NADIE REGISTRADO EN EL INMUEBLE",
    "notify_sent": "NOTIFICACIÓN ENVIADA",
    "notify_simulated": "NOTIFICACIÓN SIMULADA · NADIE LA RECIBIÓ",
    "siren_off": "SIRENA SILENCIADA",
    "siren_on": "SIRENA ACTIVADA",
    "strobe_off": "ESTROBO APAGADO",
    "strobe_on": "ESTROBO ACTIVADO",
    "tactical_ack": "ACUSE DE LA BRIGADA",
    "tactical_ack_timeout": "LA BRIGADA NO ACUSÓ EN EL PLAZO",
}

#: Lo que se imprime junto a un verbo que este registro no sabe rotular. El
#: identificador va igualmente —es el dato de la tabla y no se oculta—, pero
#: acompañado de la razón, que es lo que distingue un dato en crudo de un dato en
#: crudo DECLARADO.
SIN_ROTULO = "sin rótulo declarado"


def rotulo(kind: str) -> tuple[str, bool]:
    """`(texto_para_el_papel, ¿se_sabe_rotular?)`.

    Nunca lanza y nunca devuelve vacío: una cronología con una fila en blanco
    sería peor que una con un identificador técnico, porque el hueco no dice que
    falte nada.
    """
    conocido = ROTULOS.get(kind)
    if conocido is not None:
        return conocido, True
    return f"{kind} · {SIN_ROTULO}", False
