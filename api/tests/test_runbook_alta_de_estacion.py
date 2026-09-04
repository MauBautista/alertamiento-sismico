"""T-5.06 · El runbook de alta se ancla al CÓDIGO, no a otra prosa.

`RUNBOOK-ALTA-DE-ESTACION.md` llevaba desde el 2026-07-30 sin tocarse mientras el
contrato de alta cambió tres veces, y acumuló **siete divergencias**. La peor
mandaba escribir UUIDs en `TAKAB_EDGE_TENANT_ID/SITE_ID/GATEWAY_ID` cuando la
ingesta compara **códigos y seriales legibles** — y encima mandaba sobrescribir el
valor que `provision_gateway.sh` ya había dejado bien. Seguir el runbook al pie de
la letra producía una estación aprovisionada, con certificado, conectada por
mTLS… y **muda en la nube**, con sus mensajes en la cola de descarte y ninguna
pantalla explicando por qué.

Un runbook que se comprueba leyéndolo vuelve a divergir en cuanto alguien cambia
un esquema. Este archivo compara lo que el runbook MANDA HACER contra lo que el
código ACEPTA, y nombra las tres fuentes cuando dejan de coincidir.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from takab_api.schemas.fleet import EquipmentProfile, GatewayCreate
from takab_api.schemas.sensors import SensorCreate
from takab_api.schemas.sites import SiteCreate

_RAIZ = Path(__file__).resolve().parents[2]
_RUNBOOK = _RAIZ / "takab-docs/RUNBOOK-ALTA-DE-ESTACION.md"
_PROVISION = _RAIZ / "infra/scripts/provision_gateway.sh"
_INGESTA = _RAIZ / "api/src/takab_api/ingest/handlers.py"


@pytest.fixture(scope="module")
def runbook() -> str:
    return _RUNBOOK.read_text(encoding="utf-8")


# --- 1. La identidad: tres fuentes que tienen que decir lo mismo --------------


def _dotenv_activas(texto: str) -> dict[str, str]:
    """Variables `TAKAB_EDGE_*` que el runbook manda escribir DE VERDAD.

    Las comentadas no cuentan: son las que el runbook enseña como «ya puestas» o
    «opcionales», y tratarlas como órdenes haría fallar al test por documentación
    correcta.
    """
    return {
        m.group(1): m.group(2).strip()
        for m in re.finditer(r"^(TAKAB_EDGE_[A-Z0-9_]+)=(.*)$", texto, re.M)
    }


def test_el_runbook_NO_manda_escribir_UUIDs_de_identidad(runbook: str) -> None:
    """La divergencia que rompía la ingesta, en su forma exacta.

    `handlers.py` compara `payload.tenant_id` contra `tenants.code` y
    `payload.gateway_id` contra `gateways.serial`. Un UUID ahí no es un formato
    distinto del mismo dato: es OTRO dato, y el mensaje acaba en la DLQ.
    """
    activas = _dotenv_activas(runbook)
    sospechosas = {
        k: v
        for k, v in activas.items()
        if k in ("TAKAB_EDGE_TENANT_ID", "TAKAB_EDGE_SITE_ID", "TAKAB_EDGE_GATEWAY_ID")
        and ("uuid" in v.lower() or re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", v, re.I))
    }
    assert not sospechosas, (
        "el runbook manda escribir UUIDs en la identidad del gabinete: "
        f"{sospechosas}. La ingesta compara CÓDIGOS legibles "
        "(`api/src/takab_api/ingest/handlers.py`, regla de identidad), así que el "
        "gabinete quedaría mudo con sus mensajes en la cola de descarte."
    )


def test_el_runbook_no_manda_pisar_lo_que_el_APROVISIONADOR_ya_dejo(runbook: str) -> None:
    """`provision_gateway.sh` escribe `TAKAB_EDGE_GATEWAY_ID` con el thing name.

    El runbook mandaba sobrescribirlo en el paso siguiente. Aquí se exige lo
    contrario: lo que el aprovisionador gestiona no puede aparecer como una línea
    activa del bloque que el operador teclea.
    """
    # Solo el bloque que se escribe SIEMPRE: el `printf` con redirección
    # TRUNCANTE (`>`, no `>>`) a `edge.env.managed`. Los `>>` posteriores dependen
    # de banderas opcionales (`--site-lat`), y ésas SÍ puede ponerlas el operador
    # a mano — el propio runbook ofrece los dos caminos.
    #
    # El `[\s\S]*?` no es adorno: en el guion la redirección va en la LÍNEA
    # SIGUIENTE al `printf`. Con `[^\n]*` este barrido casaba con OTRO printf y
    # devolvía `{TAKAB_EDGE_GPIO_OWNER}` — un conjunto no vacío, así que el
    # `assert gestionadas` pasaba en verde sobre un censo que ya no vigilaba la
    # variable que importa. Por eso ahora se exige por NOMBRE.
    guion = _PROVISION.read_text("utf-8")
    bloque = re.search(r"printf '([^']*)'[\s\S]*?[^>]>\"\$TMP/edge\.env\.managed\"", guion)
    assert bloque, "no se encontró el bloque gestionado de provision_gateway.sh"
    gestionadas = set(re.findall(r"(TAKAB_EDGE_[A-Z0-9_]+)=", bloque.group(1)))
    assert "TAKAB_EDGE_GATEWAY_ID" in gestionadas, (
        "el barrido no ve que `provision_gateway.sh` escribe TAKAB_EDGE_GATEWAY_ID; "
        f"leyó {sorted(gestionadas)}. Sin eso este test no vigila nada."
    )

    pisadas = sorted(gestionadas & set(_dotenv_activas(runbook)))
    assert not pisadas, (
        f"el runbook manda escribir a mano variables que `provision_gateway.sh` ya "
        f"deja puestas: {pisadas}. Sobrescribirlas es exactamente lo que rompía el "
        "alta — coméntalas en el bloque y di que ya están."
    )


def test_la_ingesta_SIGUE_comparando_codigos_y_el_runbook_lo_dice(runbook: str) -> None:
    """La tercera fuente. Si mañana la ingesta pasara a comparar UUIDs, este test
    se pone rojo y obliga a mover el runbook con ella — que es justo lo que no
    pasó en las tres veces que el contrato cambió."""
    ingesta = _INGESTA.read_text("utf-8")
    for esperado in (
        "payload.tenant_id",
        "tenants.code",
        "payload.gateway_id",
        "gateways.serial",
    ):
        assert esperado in ingesta, (
            f"la regla de identidad de la ingesta ya no menciona `{esperado}`: si el "
            "contrato cambió, el runbook (§5) tiene que cambiar con él"
        )
    assert "CÓDIGOS" in runbook and "gateways.serial" in runbook, (
        "el runbook dejó de explicar que la identidad son códigos y contra qué se "
        "comparan: es la divergencia que costó una estación muda"
    )


# --- 2. Los cuerpos del alta: por igualdad contra el esquema ------------------

#: Los tres `POST` del §6 y el esquema que valida cada uno. Se comparan POR
#: IGUALDAD: un campo de más da 422 (`extra="forbid"`) y uno de menos deja un
#: default silencioso — `equipment` omitido pinta cinco actuadores en un gabinete
#: que tiene dos.
_CUERPOS = {
    "POST /sites": SiteCreate,
    "POST /fleet/gateways": GatewayCreate,
    "POST /sensors": SensorCreate,
}


def _campos_documentados(runbook: str, endpoint: str) -> set[str]:
    """Los campos de la frase `Campos:` de ese endpoint. **Solo esa frase.**

    Leer la viñeta entera no sirve: sus sub-guiones nombran campos PROHIBIDOS a
    propósito —«`fw_version` da 422»— y un parser que los contara como órdenes se
    pondría rojo por documentación correcta. La frase `Campos:` es la instrucción;
    lo de debajo es la explicación.
    """
    i = runbook.index(f"**`{endpoint}`**")
    resto = runbook[i:]
    frase = re.search(r"Campos:(.*?)\.\n", resto, re.S)
    assert frase, f"`{endpoint}`: no se encontró su frase `Campos:` en el runbook"
    return set(re.findall(r"`([a-z0-9_]+)`", frase.group(1)))


@pytest.mark.parametrize("endpoint", sorted(_CUERPOS))
def test_los_campos_del_runbook_son_los_del_ESQUEMA(runbook: str, endpoint: str) -> None:
    esquema = _CUERPOS[endpoint]
    del_esquema = set(esquema.model_fields)
    documentados = _campos_documentados(runbook, endpoint) & (
        del_esquema | {"fw_version", "tenant_id", "status"}
    )

    sobran = documentados - del_esquema
    faltan = del_esquema - documentados
    assert not sobran, (
        f"`{endpoint}`: el runbook manda enviar {sorted(sobran)}, que el esquema "
        f'`{esquema.__name__}` NO acepta (`extra="forbid"`) ⇒ **422**'
    )
    assert not faltan, (
        f"`{endpoint}`: el runbook no menciona {sorted(faltan)}. Un campo omitido "
        f"toma su default en silencio — que es como `equipment` acabó pintando cinco "
        "actuadores en gabinetes que tienen dos"
    )


def test_los_tres_esquemas_prohiben_claves_desconocidas() -> None:
    """La premisa del test de arriba: si un esquema dejara de ser `forbid`, un
    campo de más ya no daría 422 y el runbook podría desviarse sin consecuencia."""
    for endpoint, esquema in _CUERPOS.items():
        assert esquema.model_config.get("extra") == "forbid", (
            f"{esquema.__name__} ({endpoint}) dejó de rechazar claves desconocidas"
        )


def test_el_runbook_declara_el_EQUIPAMIENTO_con_sus_cinco_canales(runbook: str) -> None:
    """`equipment` no basta con nombrarlo: el default es TODO TRUE, así que el
    runbook tiene que enseñar a declararlo o la consola miente sobre el hardware."""
    for canal in EquipmentProfile.model_fields:
        assert f"`{canal}`" in runbook or f'"{canal}"' in runbook, (
            f"el runbook no nombra el canal `{canal}` del equipamiento: quien siga "
            "el alta no sabrá que omitirlo lo declara INSTALADO"
        )


# --- 3. Los pasos que faltaban ------------------------------------------------


def test_el_runbook_manda_INSTALAR_el_software_del_edge(runbook: str) -> None:
    """`provision_gateway.sh` deja identidad y certificados; **no copia el código**."""
    assert "deploy/edge/deploy.sh" in runbook, (
        "el runbook no manda instalar el software del edge: un gabinete "
        "aprovisionado sin esto no tiene nada que arrancar"
    )


def test_el_runbook_manda_PUBLICAR_la_version(runbook: str) -> None:
    assert "/fleet/releases" in runbook, (
        "el runbook no manda publicar el release: sin él la flota entera sale "
        "SIN REFERENCIA y la deriva de versión no significa nada"
    )


def test_el_runbook_manda_crear_el_RULE_SET_con_su_clave_edge(runbook: str) -> None:
    assert "/rule-sets" in runbook, (
        "el runbook no menciona el rule_set: sin uno aplicable, la estación nueva "
        "NUNCA entra al sincronizado firmado"
    )
    assert re.search(r"clave\s+`edge`", runbook), (
        "el runbook no dice que el `config` necesita la clave `edge`: sin ella el "
        "rule_set existe y no se sincroniza, que es peor que no tenerlo"
    )


def test_el_runbook_ya_NO_dice_que_falten_el_alta_de_clientes_ni_la_visibilidad(
    runbook: str,
) -> None:
    """Dos secciones anunciaban como futuro lo que lleva en producción desde el
    2026-07-15 (`T-1.72` y `T-1.73`), y mandaban dar de alta clientes por SQL —
    que además se salta la fila de auditoría del alta."""
    for endpoint in ("POST /tenants", "/visibility-grants"):
        assert endpoint in runbook, f"el runbook sigue sin documentar `{endpoint}`"
    for futuro in ("T-1.72 traerá", "T-1.73 traerá", "no hay** endpoint"):
        assert futuro not in runbook, (
            f"el runbook sigue anunciando como futuro algo ya entregado: {futuro!r}"
        )


def test_el_censo_declara_SU_TAMAÑO(runbook: str) -> None:
    """Guarda de no-vacuidad: sin esto, un parser que dejara de encontrar el bloque
    `dotenv` —o las viñetas— pasaría en verde comparando conjuntos vacíos."""
    assert len(_CUERPOS) == 3
    activas = _dotenv_activas(runbook)
    assert len(activas) >= 10, (
        f"solo se leyeron {len(activas)} variables del bloque dotenv del runbook: "
        "el parser dejó de encontrarlo y los tests de identidad no comprueban nada"
    )
    for endpoint, esquema in _CUERPOS.items():
        campos = _campos_documentados(runbook, endpoint)
        assert len(campos) >= len(esquema.model_fields), (
            f"`{endpoint}`: se leyeron {len(campos)} campos del runbook para un "
            f"esquema de {len(esquema.model_fields)} — el parser no está viendo la viñeta"
        )
