"""T-2.71 · Qué se puede silenciar, cómo se derivan los nombres y qué acusa.

Este archivo blinda la decisión más peligrosa de la tarea: **qué alarma puede
callarse durante una ventana de mantenimiento**. Silenciar de más no rompe
ningún test de forma ruidosa — produce un sistema que parece vigilado y no lo
está, que es exactamente el modo de fallo que esta fase encontró quince veces.

Tres invariantes, y ninguno se afirma: se mide.

1. **El catálogo se DERIVA del Terraform, no se enumera.** El test lee
   ``infra/terraform/modules/observability/main.tf`` y exige que TODA alarma que
   exista allí esté clasificada aquí. Una alarma nueva sin clasificar pone este
   archivo en rojo: es imposible añadir vigilancia y olvidarse de decidir si se
   puede callar.
2. **Los nombres se DERIVAN de las filas de la DB**, jamás del cuerpo de la
   petición. Por eso ``mute_names_for_gateways`` recibe ``iot_thing``, no una
   lista de nombres de alarma.
3. **PUBLICADO ≠ ENTREGADO.** Un ``PutAlarmMuteRule`` con 200 no es "silenciado":
   el acuse se calcula releyendo la regla y contrastando contra
   ``describe_alarms``.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ops.censo_alarmas import alarmas
from takab_api.ops.muting import (
    ALARM_CATALOG,
    AWS_CITAS,
    AWS_PREVUELO,
    GATEWAY,
    MAX_WINDOW_S,
    MIN_WINDOW_S,
    NEVER,
    PLATFORM,
    MuteAck,
    ProtectedAlarmError,
    apply_mute,
    assert_not_protected,
    at_expression,
    delete_mute,
    iso8601_duration,
    mute_names_for_gateways,
    mute_names_for_platform,
    mute_start,
    protected_alarm_names,
)

_T0 = datetime(2026, 8, 6, 3, 30, tzinfo=UTC)

_MODULE = Path(__file__).resolve().parents[3] / "infra/terraform/modules/observability/main.tf"


def _terraform_alarm_resources() -> set[str]:
    """[T-2.72.d] El censo ya no se lee de UN fichero: se deriva de todo
    `infra/terraform` (`ops/censo_alarmas.py`). Este guardia tenía exactamente el
    mismo punto ciego que el de `treat_missing_data` —una alarma declarada en otro
    módulo nacía sin clasificar y nada lo delataba— y se cierra con la misma
    derivación. Hoy todas siguen en `observability/main.tf`; el censo ya no lo da
    por supuesto."""
    return set(alarmas())


# --- 1. El catálogo se deriva, no se enumera ---------------------------------


def test_toda_alarma_del_terraform_esta_clasificada() -> None:
    """Patrón #2 de la sesión: un test que enumera casos se queda ciego ante el
    siguiente. Aquí la lista la pone el Terraform, así que una alarma nueva sin
    decidir si es silenciable **no puede pasar en verde**."""
    en_terraform = _terraform_alarm_resources()
    assert en_terraform, "no se encontró ninguna alarma en el Terraform: el test estaría vacío"
    clasificadas = {k.resource for k in ALARM_CATALOG}
    sin_clasificar = en_terraform - clasificadas
    assert not sin_clasificar, (
        f"alarma(s) nueva(s) en el Terraform sin clasificar en ALARM_CATALOG: "
        f"{sorted(sin_clasificar)}. Decide si se puede silenciar durante una ventana de "
        f"mantenimiento — el default seguro es NEVER."
    )
    fantasmas = clasificadas - en_terraform
    assert not fantasmas, (
        f"ALARM_CATALOG clasifica alarma(s) que ya no existen en Terraform: {sorted(fantasmas)}"
    )


def test_el_catalogo_conoce_los_nombres_reales_del_terraform() -> None:
    """La frontera es un NOMBRE. Si la plantilla de aquí y el ``alarm_name`` de
    allí divergen, la ventana silencia un nombre que no existe (y el acuse lo
    dirá), pero peor: el guardia de alarmas protegidas dejaría de reconocer las
    intocables. Se contrasta contra el texto real del módulo."""
    texto = _MODULE.read_text(encoding="utf-8")
    for kind in ALARM_CATALOG:
        # `for_each` interpola `each.value` (toset) o `each.key` (map): ambas son
        # el mismo hueco desde aquí.
        variantes = {
            kind.name_template.replace("{thing}", sufijo)
            for sufijo in ("${each.value}", "${each.key}", "")
        }
        assert any(v in texto for v in variantes), (
            f"la plantilla de {kind.resource} ({kind.name_template!r}) no aparece en "
            f"observability/main.tf: el nombre real cambió y esta clasificación quedó huérfana"
        )


def test_las_intocables_lo_son_por_escrito() -> None:
    """Las que NUNCA se callan, con su razón — no por gusto:

    ``dlq_depth`` y ``iot_rule_errors`` son el INSTRUMENTO del canary de T-2.70
    (una actualización que rompe el contrato de payload se manifiesta ahí);
    ``ghost_gateways`` vigila al vigilante y su ``insufficient_data_actions`` es
    la única señal de que el worker que cuenta está muerto;
    ``wal_archive_stalled`` (T-2.72) es lo único que acota el RPO — el número que
    publica ``terraform output rpo_seconds`` no lo garantiza la configuración de
    Postgres, lo garantiza que esa alarma suene.

    Este conjunto se ENUMERA a propósito, al revés que
    ``test_toda_alarma_del_terraform_esta_clasificada``. Ahí enumerar sería
    quedarse ciego ante la siguiente alarma; aquí la lista ES la decisión, y que
    haga falta tocar este test para ampliar el silencio permitido —o para
    retirarlo— es justo la fricción que se busca. Lo que sí se deriva es que cada
    una lleve su razón escrita, para que nadie herede una clasificación sin
    entenderla.
    """
    nunca = {k.resource for k in ALARM_CATALOG if k.scope == NEVER}
    assert nunca == {
        "dlq_depth",
        "iot_rule_errors",
        "ghost_gateways",
        "wal_archive_stalled",
        # [T-2.72.b/c] Las dos de la Fase 2.6. `wal_archive_stalled` vigila la
        # CADENA de WAL; `base_backup_missing`, su ANCLA — sin ancla, la cadena no
        # recupera nada. Y `db_disk_space` vigila el modo de fallo que el PITR
        # trajo consigo: con el archivado atascado el WAL no se recicla y llena el
        # volumen de los datos en menos de dos días.
        "base_backup_missing",
        # [T-2.141] Y su AVISO, que mira la MISMA métrica con el umbral sin el
        # margen. Entra por separado porque callarla no es callar «la misma
        # alarma otra vez»: es quedarse solo con la que ya no avisa a tiempo.
        "base_backup_late",
        "db_disk_space",
        # [T-2.81.a] La retención de PII que se para. No entra aquí por inercia:
        # su umbral ya son DOS DÍAS sin una corrida correcta, así que ninguna
        # ventana de mantenimiento razonable la hace sonar — no hay ruido que
        # evitar callándola, solo el aviso que se perdería. Y lo que avisa no es
        # un síntoma operativo: es que se está incumpliendo la política de
        # privacidad que se le prometió a un cliente, un fallo que no tumba nada
        # y que por eso solo se descubre cuando alguien pregunta.
        "pii_retention_stalled",
        # [T-2.153] La deriva de esquema, y entra aquí por la razón más directa
        # de todas: **una ventana de mantenimiento es justo cuando alguien está
        # desplegando**, o sea el momento en que la deriva se CREA. Callarla ahí
        # es apagar el detector durante el único rato en que el defecto aparece.
        # Tampoco hay ruido que evitar: los dos periodos de evaluación ya se
        # comen el transitorio del propio despliegue, así que un `make
        # cloud-deploy` normal no la enciende.
        "schema_drift",
        # [T-5.24] El reloj a la deriva. Comparte publicador con `ghost_gateways`
        # —la MISMA `put_metric_data`—, así que una ventana de plataforma que pare
        # el worker de notificación manda DOS correos de INSUFFICIENT_DATA por una
        # sola causa, y eso es un argumento real para callarla. No basta: durante
        # esa ventana la alarma también puede sonar por su VALOR, y el reloj de un
        # gabinete que se sale de rango mientras se mantiene la nube es un hallazgo
        # AJENO al mantenimiento, que la ventana taparía. Se paga el correo
        # duplicado a cambio de no cegar la única vigilancia de la hora — y sin
        # hora confiable no vale ninguna evidencia que se selle en ese rato.
        "clock_drift",
    }
    for kind in ALARM_CATALOG:
        if kind.scope == NEVER:
            assert len(kind.why) > 40, f"{kind.resource} intocable sin razón escrita"


def test_solo_dos_alarmas_son_silenciables_por_gabinete() -> None:
    por_gabinete = {k.resource for k in ALARM_CATALOG if k.scope == GATEWAY}
    assert por_gabinete == {"gateway_offline", "sensor_mute"}


def test_solo_las_de_la_instancia_son_silenciables_por_plataforma() -> None:
    plataforma = {k.resource for k in ALARM_CATALOG if k.scope == PLATFORM}
    assert plataforma == {"ec2_status", "ec2_cpu"}


# --- 1b. Las citas de AWS son comprobables, o no se escriben --------------------
#
# La decisión central de este módulo se justificó con una frase entrecomillada
# como literal de la documentación de AWS que **no está en la documentación de
# AWS**: "When a mute window ends, if the targeted alarm(s) remains in an
# alarming state, CloudWatch automatically RE-TRIGGERS the alarm actions that
# were muted during the window". Una afirmación falsa escrita como verdad citable
# es peor que no escribir nada, porque el siguiente que lea el archivo no vuelve
# a comprobarla — y si la razón no se sostiene, la decisión hay que retomarla.
#
# Estos dos tests son el ancla. El primero no se salta NUNCA: vigila que la frase
# no vuelva. El segundo comprueba lo contrario —que lo que SÍ se cita es literal—
# y para eso necesita el modelo de servicio del CLI, así que se salta si no está
# instalado; el primero cubre el caso mientras tanto.

_RAIZ = Path(__file__).resolve().parents[3]

#: Archivos que citan comportamiento de AWS sobre las mute rules.
_CON_CITAS = (
    "api/src/takab_api/ops/muting.py",
    "api/src/takab_api/routers/maintenance.py",
    "infra/terraform/modules/observability/tests/treat_missing_data.tftest.hcl",
    "takab-docs/TASKS.md",
)

#: Fragmentos de la cita inventada, en la forma en que se presentó como literal.
_INVENTADO = ("re-triggers", "mute window ends", "alarming state")

#: Los DOS archivos donde una cita de AWS se escribe como tal. La convención es
#: estrecha a propósito: dentro de ellos, ``*"…"*`` significa CITA LITERAL DE AWS
#: y no se usa para nada más, así que el escáner de abajo no puede confundirse con
#: prosa en castellano.
_CON_CITAS_LITERALES = (
    "api/src/takab_api/ops/muting.py",
    "api/src/takab_api/routers/maintenance.py",
)

_CITA_RE = re.compile(r'\*"(.+?)"\*', re.S)


def _modelo_de_servicio() -> dict | None:
    """El modelo del CLI instalado, o ``None`` si no hay CLI en esta máquina."""
    candidatos = sorted(
        Path("/usr/local/aws-cli/v2").glob(
            "*/dist/awscli/botocore/data/cloudwatch/*/service-2.json"
        )
    )
    if not candidatos:
        return None
    return json.loads(candidatos[-1].read_text(encoding="utf-8"))


def _sin_marcas(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", texto)).strip()


@pytest.mark.parametrize("ruta", _CON_CITAS)
def test_la_cita_inventada_no_vuelve(ruta: str) -> None:
    """No se salta nunca. Si alguien reintroduce la frase, esto cae en rojo."""
    texto = (_RAIZ / ruta).read_text(encoding="utf-8").lower()
    presentes = [f for f in _INVENTADO if f in texto]
    assert not presentes, (
        f"{ruta} volvió a citar como documentación de AWS una frase que no existe en la "
        f"documentación de AWS ({presentes}). Lo verificable está en el modelo de servicio "
        f"del CLI; lo que no se pueda verificar se declara pendiente de gate, no se cita."
    )


def test_ninguna_cita_de_aws_del_codigo_vive_fuera_de_AWS_CITAS() -> None:
    """El eslabón que faltaba, y que no se salta NUNCA.

    La versión anterior de este archivo confrontaba el modelo de servicio contra
    su **propia copia** de la frase, no contra la que el código enseña al que lo
    lee: invertir la cita dentro de ``delete_mute`` (*"…will NOT trigger"*) o
    parafrasear a falso la del permiso IAM dejaba los 82 tests en verde. Eso es
    teatro: la fase entera nació de una cita inventada, y una cita verdadera sin
    anclar es la siguiente cita inventada esperando su turno.

    Aquí la prosa se LEE del archivo y tiene que coincidir palabra por palabra
    con una entrada de ``AWS_CITAS``, que es lo único que el test de abajo
    confronta contra AWS. Los dos sentidos importan: una cita en prosa sin
    declarar no se comprueba jamás, y una entrada declarada que nadie cita es un
    ancla amarrada a nada.
    """
    declaradas = {_sin_marcas(c.texto) for c in AWS_CITAS}
    en_prosa: set[str] = set()
    for ruta in _CON_CITAS_LITERALES:
        texto = (_RAIZ / ruta).read_text(encoding="utf-8")
        en_prosa |= {_sin_marcas(m) for m in _CITA_RE.findall(texto)}

    assert en_prosa, (
        'no se encontró una sola cita `*"…"*` en el código de la ventana: el escáner '
        "quedó vacío y este test no mediría nada"
    )
    sin_anclar = sorted(en_prosa - declaradas)
    assert not sin_anclar, (
        f"el código cita a AWS con palabras que NO están declaradas en `AWS_CITAS`, así que "
        f"nadie las confronta jamás contra el modelo de servicio: {sin_anclar}. Declárala o "
        f"deja de escribirla como cita."
    )
    sin_citar = sorted(declaradas - en_prosa)
    assert not sin_citar, (
        f"`AWS_CITAS` declara frases que el código ya no cita: {sin_citar}. Un ancla que no "
        f"sujeta nada da la falsa impresión de que la prosa está comprobada."
    )


def test_cada_cita_declarada_es_LITERAL_en_el_modelo_del_CLI() -> None:
    """El otro extremo del mismo cable: cuatro decisiones de diseño se apoyan en
    estas frases (el mecanismo, el cierre anticipado, el IAM por objetivo y qué
    pasa mientras la regla está activa). Si AWS las cambia o alguien las
    parafrasea "para que se lean mejor", este test lo dice."""
    modelo = _modelo_de_servicio()
    if modelo is None:
        pytest.skip(
            "sin AWS CLI v2 instalado no hay modelo de servicio que leer; "
            "`test_la_cita_inventada_no_vuelve` y el escáner de prosa cubren el caso"
        )
    assert len(AWS_CITAS) >= 4, "quedan menos citas de las que el módulo usa para decidir"
    for cita in AWS_CITAS:
        assert len(_sin_marcas(cita.texto)) >= 40, (
            f"cita demasiado corta para medir nada: {cita.texto!r}"
        )
        nodo: object = modelo
        for paso in cita.donde:
            assert isinstance(nodo, dict) and paso in nodo, (
                f"la ruta {cita.donde} ya no existe en el modelo de servicio del CLI: "
                f"AWS movió el contrato y esta cita quedó huérfana"
            )
            nodo = nodo[paso]
        assert _sin_marcas(cita.texto) in _sin_marcas(str(nodo)), (
            f"la cita de {'.'.join(cita.donde)} ya no es literal en el modelo de servicio "
            f"del CLI. Corrige la cita o vuelve a tomar la decisión que se apoyaba en ella."
        )


def test_la_expresion_y_la_duracion_son_OBLIGATORIAS_en_el_contrato() -> None:
    """La razón DECISIVA para preferir la mute rule sobre ``actions_enabled``: no
    puede existir sin vencimiento. Se comprueba en el contrato, no de memoria."""
    modelo = _modelo_de_servicio()
    if modelo is None:
        pytest.skip("sin AWS CLI v2 instalado no hay modelo de servicio que leer")
    assert set(modelo["shapes"]["Schedule"]["required"]) == {"Expression", "Duration"}


# --- 2. Los nombres se DERIVAN, nunca se aceptan ------------------------------


def test_los_nombres_por_gabinete_salen_del_iot_thing() -> None:
    names = mute_names_for_gateways(env="takab-dev", things=["gw-dev-0001"])
    assert set(names) == {
        "takab-dev-gateway-offline-gw-dev-0001",
        "takab-dev-sensor-mudo-gw-dev-0001",
    }


def test_un_gabinete_sin_iot_thing_no_aporta_ningun_nombre() -> None:
    """Un gabinete dado de alta que aún no tiene ``iot_thing`` no tiene alarmas.
    Silenciar "nada" tiene que ser un no-op explícito, no una excepción ni un
    nombre inventado — la consola lo rotulará como SIN ALARMA EXISTENTE."""
    assert mute_names_for_gateways(env="takab-dev", things=[None, "", "  "]) == ()


def test_los_nombres_de_plataforma_no_dependen_de_ningun_gabinete() -> None:
    names = mute_names_for_platform(env="takab-dev")
    assert set(names) == {"takab-dev-ec2-status-check", "takab-dev-ec2-cpu-sostenida"}


def test_ninguna_derivacion_produce_jamas_una_alarma_protegida() -> None:
    """La frontera multi-tenant es el ORIGEN de los nombres. Se mide sobre TODAS
    las derivaciones posibles, incluyendo un ``iot_thing`` hostil que intente
    fabricar el nombre de una intocable."""
    protegidas = set(protected_alarm_names(env="takab-dev"))
    assert protegidas  # si estuviera vacío el test no mediría nada
    hostil = [
        "gw-dev-0001",
        "gw-dev-0001 takab-dev-dlq-telemetry",
        "../takab-dev-gateway-retirado-sigue-reportando",
    ]
    derivados = set(mute_names_for_gateways(env="takab-dev", things=hostil))
    derivados |= set(mute_names_for_platform(env="takab-dev"))
    assert derivados.isdisjoint(protegidas)


def test_el_guardia_rechaza_una_alarma_intocable() -> None:
    """Cinturón y tirantes: aunque hoy los nombres se derivan, el día que alguien
    abra un camino que los acepte, este guardia lo para."""
    with pytest.raises(ProtectedAlarmError):
        assert_not_protected(
            ["takab-dev-gateway-offline-gw-dev-0001", "takab-dev-dlq-telemetry"],
            env="takab-dev",
        )
    # Y no molesta a lo legítimo.
    assert_not_protected(["takab-dev-gateway-offline-gw-dev-0001"], env="takab-dev")


def test_el_guardia_reconoce_la_intocable_de_cualquier_dlq() -> None:
    """``dlq_depth`` es ``for_each`` sobre un mapa: su nombre lleva un sufijo que
    Terraform decide. El guardia tiene que reconocer el PREFIJO, no una lista de
    colas — otra vez, derivar en vez de enumerar."""
    with pytest.raises(ProtectedAlarmError):
        assert_not_protected(["takab-dev-dlq-una-cola-que-nadie-previo"], env="takab-dev")


# --- 3. La duración vence sola --------------------------------------------------


def test_la_duracion_se_traduce_a_iso8601_de_minutos() -> None:
    assert iso8601_duration(900) == "PT15M"
    assert iso8601_duration(14400) == "PT240M"


def test_la_duracion_maxima_esta_muy_por_debajo_del_tope_de_aws() -> None:
    """AWS acepta hasta P15D. Una ventana de mantenimiento que necesita quince
    días no es una ventana: es un sistema apagado. El tope de la casa son horas."""
    assert MAX_WINDOW_S <= 4 * 3600
    assert MIN_WINDOW_S >= 60  # mínimo de AWS: PT1M


@pytest.mark.parametrize("bad", [0, 59, 4 * 3600 + 1, -300])
def test_una_duracion_fuera_de_rango_no_se_traduce(bad: int) -> None:
    with pytest.raises(ValueError):
        iso8601_duration(bad)


def test_el_arranque_se_redondea_al_minuto_siguiente() -> None:
    """``at()`` tiene granularidad de MINUTO. Se redondea hacia ARRIBA a
    propósito: un ``at()`` en un minuto ya empezado podría no activarse nunca, y
    la ventana quedaría abierta en la fila sin estarlo en AWS. Ese lado de la
    divergencia es el SEGURO (las alarmas suenan), pero el retraso acotado a
    ≤60 s es preferible a un silencio que no se sabe si existe."""
    assert mute_start(datetime(2026, 8, 6, 3, 30, 12, tzinfo=UTC)) == datetime(
        2026, 8, 6, 3, 31, tzinfo=UTC
    )
    # Un instante exacto en el minuto también avanza: nunca se emite un `at()` que
    # ya pasó.
    assert mute_start(_T0) == datetime(2026, 8, 6, 3, 31, tzinfo=UTC)


def test_la_expresion_es_siempre_de_UNA_VEZ_jamas_un_cron() -> None:
    """La corrección más importante del reconocimiento: ``Expression`` es
    OBLIGATORIA en ``PutAlarmMuteRule``, no opcional. Y admite dos formatos —
    ``cron(...)`` recurrente y ``at(...)`` de una sola vez.

    Una mute rule recurrente **no expira jamás** salvo que se le ponga
    ``expire_date``: es la alarma apagada para siempre disfrazada de comodidad.
    Aquí la expresión no se acepta de nadie: se DERIVA del reloj, y solo puede
    salir un ``at()``."""
    expr = at_expression(datetime(2026, 8, 6, 3, 31, tzinfo=UTC))
    assert expr == "at(2026-08-06T03:31)"
    assert not expr.startswith("cron(")


# --- 4. PUBLICADO ≠ ENTREGADO: el acuse se relee ---------------------------------


class _FakeCW:
    """CloudWatch de mentira. ``existing`` = alarmas que de verdad existen."""

    def __init__(self, *, existing: set[str], stored_targets: list[str] | None = None) -> None:
        self.existing = existing
        self._stored = stored_targets
        self.puts: list[dict] = []
        self.deleted: list[str] = []

    def put_alarm_mute_rule(self, **kw: object) -> dict:
        self.puts.append(dict(kw))
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def get_alarm_mute_rule(self, **_kw: object) -> dict:
        put = self.puts[-1]
        targets = self._stored if self._stored is not None else put["MuteTargets"]["AlarmNames"]
        return {
            "Name": put["Name"],
            "Status": "SCHEDULED",
            "MuteTargets": {"AlarmNames": list(targets)},
        }

    def delete_alarm_mute_rule(self, **kw: object) -> dict:
        self.deleted.append(str(kw["AlarmMuteRuleName"]))
        return {}

    def describe_alarms(self, **kw: object) -> dict:
        pedidas = list(kw.get("AlarmNames", []))  # type: ignore[arg-type]
        return {"MetricAlarms": [{"AlarmName": n} for n in pedidas if n in self.existing]}


def test_el_acuse_cuenta_lo_que_de_verdad_quedo_silenciado() -> None:
    """Dos gabinetes pedidos, uno solo con alarmas creadas (el otro no está en
    ``paged_gateways``). El 200 diría "todo bien"; el acuse dice la verdad."""
    cw = _FakeCW(
        existing={
            "takab-dev-gateway-offline-gw-dev-0001",
            "takab-dev-sensor-mudo-gw-dev-0001",
        }
    )
    pedidas = mute_names_for_gateways(env="takab-dev", things=["gw-dev-0001", "gw-dev-0009"])
    ack = apply_mute(
        cw,
        rule_name="takab-dev-mw-abc",
        alarm_names=pedidas,
        duration_s=900,
        starts_at=_T0,
        env="takab-dev",
    )
    assert isinstance(ack, MuteAck)
    assert ack.requested == 4
    assert ack.silenced == 2
    assert ack.missing == 2
    assert sorted(ack.missing_names) == [
        "takab-dev-gateway-offline-gw-dev-0009",
        "takab-dev-sensor-mudo-gw-dev-0009",
    ]


def test_el_acuse_no_cree_al_200_si_la_regla_guardo_otra_cosa() -> None:
    """El caso que el patrón #1 de la sesión predice: la llamada devuelve 200 y
    la regla almacenada NO cubre lo que se pidió. La alarma existe, pero no está
    silenciada. Contar el 200 como éxito sería la mentira exacta."""
    cw = _FakeCW(
        existing={
            "takab-dev-gateway-offline-gw-dev-0001",
            "takab-dev-sensor-mudo-gw-dev-0001",
        },
        stored_targets=["takab-dev-gateway-offline-gw-dev-0001"],
    )
    ack = apply_mute(
        cw,
        rule_name="takab-dev-mw-abc",
        alarm_names=mute_names_for_gateways(env="takab-dev", things=["gw-dev-0001"]),
        duration_s=900,
        starts_at=_T0,
        env="takab-dev",
    )
    assert ack.requested == 2
    assert ack.silenced == 1
    assert ack.missing_names == ("takab-dev-sensor-mudo-gw-dev-0001",)


def test_apply_mute_rechaza_una_alarma_protegida_antes_de_llamar_a_aws() -> None:
    cw = _FakeCW(existing={"takab-dev-dlq-telemetry"})
    with pytest.raises(ProtectedAlarmError):
        apply_mute(
            cw,
            rule_name="takab-dev-mw-abc",
            alarm_names=("takab-dev-dlq-telemetry",),
            duration_s=900,
            starts_at=_T0,
            env="takab-dev",
        )
    assert cw.puts == [], "se llamó a AWS con una alarma intocable"


def test_apply_mute_emite_una_ventana_de_UNA_VEZ_con_duracion() -> None:
    """Las dos mitades del vencimiento, en la misma aserción a propósito:
    ``Duration`` acota cuánto dura y ``at()`` acota que ocurre UNA VEZ. Separadas,
    alguien cambia un día la expresión a ``cron(...)`` para "no tener que abrirla
    cada domingo" y la ventana deja de vencer para siempre."""
    cw = _FakeCW(existing={"takab-dev-gateway-offline-gw-dev-0001"})
    apply_mute(
        cw,
        rule_name="takab-dev-mw-abc",
        alarm_names=("takab-dev-gateway-offline-gw-dev-0001",),
        duration_s=1800,
        starts_at=datetime(2026, 8, 6, 3, 31, tzinfo=UTC),
        env="takab-dev",
    )
    (put,) = cw.puts
    assert put["Rule"]["Schedule"]["Duration"] == "PT30M"
    assert put["Rule"]["Schedule"]["Expression"] == "at(2026-08-06T03:31)"
    assert "cron(" not in put["Rule"]["Schedule"]["Expression"], (
        "una mute rule con CRON y sin expire_date no vence NUNCA"
    )


def test_sin_una_sola_alarma_derivada_no_se_llama_a_aws() -> None:
    """Ventana sobre un gabinete sin ``iot_thing``: no hay nada que silenciar.
    Emitir una mute rule con cero objetivos sería un objeto huérfano en AWS."""
    cw = _FakeCW(existing=set())
    ack = apply_mute(
        cw,
        rule_name="takab-dev-mw-abc",
        alarm_names=(),
        duration_s=900,
        starts_at=_T0,
        env="takab-dev",
    )
    assert cw.puts == []
    assert (ack.requested, ack.silenced, ack.missing) == (0, 0, 0)


def test_cerrar_antes_de_tiempo_borra_la_regla_y_reabre_las_alarmas() -> None:
    """``DeleteAlarmMuteRule`` es idempotente y **desilencia en el acto**: si
    alguna alarma quedó en ALARM, sus acciones disparan. Por eso el cierre
    anticipado va por aquí y no por un ``actions_enabled``: la dirección segura
    es que el correo pendiente SALGA.

    Las dos frases están citadas literalmente en el modelo de servicio que trae
    el CLI instalado (ver ``muting.CLI_SERVICE_MODEL``); no son una promesa.
    """
    cw = _FakeCW(existing=set())
    delete_mute(cw, rule_name="takab-dev-mw-abc")
    assert cw.deleted == ["takab-dev-mw-abc"]


def test_cerrar_una_ventana_que_nunca_emitio_regla_no_llama_a_aws() -> None:
    cw = _FakeCW(existing=set())
    delete_mute(cw, rule_name=None)
    assert cw.deleted == []


class _CWContador(_FakeCW):
    """Cuenta CADA método que se le llama, no solo el que interesa."""

    def __init__(self) -> None:
        super().__init__(existing=set())
        self.llamadas: list[str] = []

    def put_alarm_mute_rule(self, **kw: object) -> dict:
        self.llamadas.append("put")
        return super().put_alarm_mute_rule(**kw)

    def get_alarm_mute_rule(self, **kw: object) -> dict:
        self.llamadas.append("get")
        return {"Name": "x", "Status": "ACTIVE", "MuteTargets": {"AlarmNames": []}}

    def delete_alarm_mute_rule(self, **kw: object) -> dict:
        self.llamadas.append("delete")
        return super().delete_alarm_mute_rule(**kw)

    def describe_alarms(self, **kw: object) -> dict:
        self.llamadas.append("describe")
        return super().describe_alarms(**kw)


def test_el_cierre_CONFIA_en_el_200_del_borrado_y_eso_es_una_decision_ESCRITA() -> None:
    """**Punto ciego declarado, no perseguido.** Léelo antes de "arreglarlo".

    La apertura no se cree el 200 del ``PutAlarmMuteRule``: lo relee. El cierre sí
    se cree el 200 del ``DeleteAlarmMuteRule``, y esta asimetría es deliberada por
    una razón que está en la FORMA de las dos operaciones, no en la comodidad:

    - el PUT acepta una LISTA de N nombres y su resultado es **parcial por
      naturaleza** —un nombre que no existe no muta nada—, así que "200" y "cuántas
      quedaron mudas" son dos hechos distintos y el segundo hay que medirlo;
    - el DELETE actúa sobre **UN objeto**, la regla, y no tiene resultado parcial:
      o la regla se fue (y con ella el silencio de todo lo que cubría) o no. No hay
      un ``N/M`` que releer.

    Lo que esto SIGUE sin cubrir, dicho en voz alta: un 200 al borrar que no
    hubiera surtido efecto cerraría la ventana —la quita de pantalla— con el
    edificio mudo hasta que expire la ``Duration``. Es el mismo daño que el
    bloqueante del cierre tragado, por otra puerta. No se persigue aquí porque
    exigiría una segunda llamada a AWS en el camino de cierre, cuyo propio fallo
    deja la ventana atascada; medir cuál de los dos riesgos es real es
    **`HUMANO-AWS`**, igual que el vencimiento de la ventana.

    Y para que el día que se cierre no haya que inventar nada, se ancla aquí la
    forma que tendría esa comprobación: ``GetAlarmMuteRule`` declara
    ``ResourceNotFoundException`` en su contrato, o sea que "la regla ya no está"
    es un hecho consultable y no una suposición. Este test cae en rojo si alguien
    añade la relectura sin venir a reescribir esta decisión.
    """
    cw = _CWContador()
    delete_mute(cw, rule_name="takab-dev-mw-abc")
    assert cw.llamadas == ["delete"], (
        "el cierre dejó de ser una sola llamada. Si es porque ahora SE COMPRUEBA el "
        "borrado, perfecto: reescribe esta decisión y el `Fichado` de T-2.71 en vez de "
        "borrar el test. Si es por otra cosa, el camino de cierre ganó una dependencia "
        "de AWS cuyo fallo deja la ventana sin poder cerrarse."
    )

    modelo = _modelo_de_servicio()
    if modelo is None:
        pytest.skip("sin AWS CLI v2 instalado no hay contrato que leer")
    errores = {e["shape"] for e in modelo["operations"]["GetAlarmMuteRule"].get("errors", [])}
    assert "ResourceNotFoundException" in errores, (
        "el contrato ya no dice cómo se sabría que una regla borrada NO está: la vía "
        "para cerrar este punto ciego cambió, y la ficha lo da por hecho"
    )


# --- 5. El ÉXITO PARCIAL: AWS falla A MEDIAS ------------------------------------
#
# La familia de fallo que el reconocimiento encontró abierta: la llamada que
# silencia SÍ llegó, y la que lo comprueba NO. El código antiguo reportaba
# "fracaso total" —`0/N` y `rule_name=None`— dejando las alarmas MUDAS, la
# consola diciendo que la vigilancia sigue viva, y el botón REABRIR sin nada que
# borrar durante hasta 4 h.
#
# La regla de la casa para este caso ya estaba escrita en otro sitio: ante la
# duda, asumir el estado más PELIGROSO. Aquí el estado peligroso es "silenciado",
# así que se asume silencio Y se conserva lo único que permite deshacerlo: el
# nombre de la regla.


class _AwsRechazo(Exception):
    """Forma de un ``botocore.exceptions.ClientError``: AWS CONTESTÓ rechazando.

    Se imita la forma (``exc.response``) en vez de importar botocore para que el
    discriminador de ``muting`` no dependa de boto3, que no es dependencia de la
    API en local ni en tests.
    """

    def __init__(self, status: int = 403, code: str = "AccessDeniedException") -> None:
        super().__init__(code)
        self.response = {
            "Error": {"Code": code, "Message": "not authorized"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        }


class _RotoCW(_FakeCW):
    """CloudWatch que falla EN UN PUNTO CONCRETO de la secuencia."""

    def __init__(
        self, *, existing: set[str], falla_en: str, error: Exception | None = None
    ) -> None:
        super().__init__(existing=existing)
        self.falla_en = falla_en
        self.error = error or ConnectionError("la red se cortó a mitad de la llamada")

    def put_alarm_mute_rule(self, **kw: object) -> dict:
        salida = super().put_alarm_mute_rule(**kw)
        if self.falla_en == "put":
            raise self.error
        return salida

    def get_alarm_mute_rule(self, **kw: object) -> dict:
        if self.falla_en == "get":
            raise self.error
        return super().get_alarm_mute_rule(**kw)

    def describe_alarms(self, **kw: object) -> dict:
        if self.falla_en == "describe":
            raise self.error
        return super().describe_alarms(**kw)


_UNA = "takab-dev-gateway-offline-gw-dev-0001"


def _mute(cw: object) -> MuteAck:
    return apply_mute(
        cw,  # type: ignore[arg-type]
        rule_name="takab-dev-mw-abc",
        alarm_names=(_UNA,),
        duration_s=900,
        starts_at=_T0,
        env="takab-dev",
    )


@pytest.mark.parametrize("falla_en", ["get", "describe"])
def test_si_el_PUT_triunfa_y_la_comprobacion_falla_NO_se_pierde_la_regla(falla_en: str) -> None:
    """El PUT llegó: las alarmas están MUDAS. Devolver ``rule_name=None`` aquí
    tira a la basura lo ÚNICO que permite desilenciarlas antes de que expire la
    ``Duration`` — hasta 4 h de edificio sin vigilancia y con un botón REABRIR
    que no hace nada."""
    cw = _RotoCW(existing={_UNA}, falla_en=falla_en)
    ack = _mute(cw)
    assert cw.puts, "el silencio llegó a pedirse"
    assert ack.rule_name == "takab-dev-mw-abc", (
        "se perdió el nombre de la regla: el silencio ya aplicado quedó sin forma de deshacerse"
    )
    assert ack.verified is False, "un acuse que no se pudo leer no puede pasar por medido"
    assert (ack.silenced, ack.missing) == (1, 0), (
        "no se sabe qué quedó mudo: se asume el estado más PELIGROSO (silenciado), "
        "no el más cómodo (vigilando)"
    )


def test_un_fallo_AMBIGUO_del_PUT_se_cuenta_como_silencio() -> None:
    """Un corte de red no dice si la petición llegó a AWS. Contarlo como
    "no silenciado" es la mentira peligrosa: si sí llegó, el edificio está mudo y
    la consola afirma lo contrario."""
    cw = _RotoCW(existing={_UNA}, falla_en="put", error=ConnectionError("se cayó la red"))
    ack = _mute(cw)
    assert ack.rule_name == "takab-dev-mw-abc"
    assert ack.verified is False
    assert (ack.silenced, ack.missing) == (1, 0)


@pytest.mark.parametrize("status", [400, 403, 404, 429])
def test_un_rechazo_DEFINITIVO_de_aws_no_finge_un_silencio_que_no_existe(status: int) -> None:
    """El error simétrico, que también hay que evitar: si AWS CONTESTÓ con un 4xx
    la regla no se creó y las alarmas SUENAN. Asumir silencio aquí pondría la
    consola en "vigilancia apagada" con la vigilancia encendida, y nadie iría a
    mirar por qué no llegan correos que sí van a llegar."""
    cw = _RotoCW(existing={_UNA}, falla_en="put", error=_AwsRechazo(status))
    with pytest.raises(_AwsRechazo):
        _mute(cw)


def test_un_5xx_de_aws_es_AMBIGUO_y_se_asume_silenciado() -> None:
    """Un 500 del servicio no dice si la regla se aplicó antes de reventar."""
    cw = _RotoCW(existing={_UNA}, falla_en="put", error=_AwsRechazo(500, "InternalFailure"))
    ack = _mute(cw)
    assert ack.verified is False and ack.rule_name == "takab-dev-mw-abc"


def test_el_camino_sin_incidencias_sigue_siendo_MEDIDO() -> None:
    """No-vacuidad del flag: si ``verified`` fuera siempre ``False`` los tests de
    arriba pasarían sin medir nada."""
    cw = _FakeCW(existing={_UNA})
    ack = _mute(cw)
    assert ack.verified is True
    assert (ack.silenced, ack.missing) == (1, 0)


# --- 6. La TERCERA familia: la petición que ni salió ------------------------------
#
# El discriminador partía el mundo en dos preguntando «¿contestó AWS?»: si no
# contestó, ambiguo, y ante la duda se asume silencio. Pero hay una tercera
# familia en la que NO hay duda: la petición nunca se envió —no había credenciales,
# no se resolvió el endpoint, la conexión no llegó a abrirse, el parámetro no pasó
# la validación del cliente—. Ahí se SABE que no se silenció nada, y contarlo como
# silencio es la inferencia inválida de esta fase con el signo cambiado: antes se
# daba por entregado lo publicado; aquí se daría por silenciado lo que ni salió.
#
# Consecuencia concreta: la consola pintaría "vigilancia apagada" con las alarmas
# sonando, y nadie iría a mirar por qué no llegan correos que sí van a llegar.


def _como_botocore(nombre: str) -> Exception:
    """Una excepción con el NOMBRE de la de botocore, y nada más.

    El discriminador va por FORMA —igual que ``exc.response``— para no convertirse
    en un ``ImportError`` el día que un despliegue recortado se quede sin boto3.
    Que se pueda imitar con esto es justamente lo que hay que poder simular; que
    los nombres sean REALES lo mide ``test_los_nombres_de_prevuelo_existen_...``.
    """
    return type(nombre, (Exception,), {})("la petición no llegó a salir")


@pytest.mark.parametrize("nombre", sorted(AWS_PREVUELO))
def test_un_fallo_que_NUNCA_salio_a_la_red_no_se_cuenta_como_silencio(nombre: str) -> None:
    """Se sabe con certeza que no hay nada mudo: el llamante puede declarar 0/N."""
    cw = _RotoCW(existing={_UNA}, falla_en="put", error=_como_botocore(nombre))
    with pytest.raises(Exception) as capturada:  # noqa: B017 - se comprueba el tipo abajo
        _mute(cw)
    assert type(capturada.value).__name__ == nombre, (
        "se tragó el fallo de prevuelo y devolvió un acuse: eso declara un silencio que "
        "NO existe, con las alarmas sonando"
    )


@pytest.mark.parametrize(
    "nombre", ["ConnectionClosedError", "ReadTimeoutError", "SSLError", "ConnectionError"]
)
def test_lo_que_pudo_pasar_DESPUES_de_enviar_sigue_siendo_ambiguo(nombre: str) -> None:
    """No-vacuidad del discriminador, y la mitad que NO se toca.

    Estos cuatro tienen en común que la petición pudo estar ya en el cable: la
    conexión se cerró esperando respuesta, se agotó el tiempo de LECTURA, el TLS
    reventó a mitad, la red se cayó sin más. Si aquí se declarase "no silenciado"
    se perdería el nombre de la regla con el edificio mudo — el bloqueante que
    esta fase ya cerró. Ante la duda se sigue asumiendo el estado PELIGROSO.
    """
    cw = _RotoCW(existing={_UNA}, falla_en="put", error=_como_botocore(nombre))
    ack = _mute(cw)
    assert ack.rule_name == "takab-dev-mw-abc"
    assert ack.verified is False
    assert (ack.silenced, ack.missing) == (1, 0)


def test_los_nombres_de_prevuelo_existen_de_verdad_en_botocore() -> None:
    """El ancla del discriminador: los nombres no se inventan, se comprueban.

    ``boto3`` es dependencia DECLARADA de esta API (``api/pyproject.toml``), así
    que esto no se salta: si botocore renombra una excepción, o si alguien añade
    a la lista un nombre que no existe —y que por tanto no filtraría nada—, cae
    en rojo. Es la misma disciplina que las citas: no se afirma lo que no se puede
    comprobar de primera mano.
    """
    from botocore import exceptions as be

    faltan = sorted(n for n in AWS_PREVUELO if not isinstance(getattr(be, n, None), type))
    assert not faltan, (
        f"`AWS_PREVUELO` nombra excepciones que botocore no tiene: {faltan}. Un nombre "
        f"inventado nunca coincide, así que ese fallo seguiría contándose como silencio."
    )


def test_la_lista_de_prevuelo_no_se_come_las_familias_ambiguas() -> None:
    """Cinturón sobre el cinturón: los nombres cuyo fallo pudo ocurrir con la
    petición ya enviada NO pueden estar en la lista. Si alguien añade
    ``ReadTimeoutError`` "porque también es de red", esto lo para."""
    prohibidos = {"ConnectionClosedError", "ReadTimeoutError", "SSLError", "ConnectionError"}
    assert AWS_PREVUELO.isdisjoint(prohibidos)
