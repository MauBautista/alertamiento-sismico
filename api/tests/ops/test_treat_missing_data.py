"""T-2.72.d · La guardia de `treat_missing_data` se DERIVA, no se enumera.

`modules/observability/tests/treat_missing_data.tftest.hcl` es donde vive la
decisión más sutil del módulo —qué significa el SILENCIO de cada métrica— y
**enumera** las alarmas: escribe una aserción por nombre. El problema es el de
siempre en este repo: una lista escrita a mano acaba divergiendo. Una alarma
nueva no obtiene su aserción sola, nace sin que nada lo diga, y elegir mal
`treat_missing_data` no rompe el `plan` ni el `validate` — produce una alarma que
MIENTE. Ya pasó cuatro veces con `gateway_offline` (julio-2026) y volvió a pasar
con `ghost_gateways`, que llegó el 2026-08-05 sin una sola línea allí.

Y HCL no puede cerrarlo por sí mismo: `terraform test` asierta sobre recursos que
hay que NOMBRAR, así que no existe la forma de escribir "para toda alarma…" en el
propio `.tftest.hcl`. Por eso la guardia derivada vive aquí, del mismo lado que
`test_muting.py`, que ya deriva su catálogo del `.tf`.

Las tres cosas que este fichero impone:

1. Toda alarma **declara** su `treat_missing_data`. Sin la clave, CloudWatch usa
   `missing`, que lleva a INSUFFICIENT_DATA: heredar ese default por olvido es
   exactamente lo que dejó la alarma MUDA el 29-jul-2026.
2. Toda alarma tiene su valor **fijado por una aserción**. Las que no la tienen
   en Terraform se NOMBRAN aquí una a una, con el valor vigente medido — el censo
   no calla lo que no sabe resolver (lección de `incidentActionKinds`).
3. El **ámbito es todo `infra/terraform`**, no un fichero. Ese era el segundo
   criterio de la ficha y el límite declarado de la guardia anterior.
"""

from __future__ import annotations

from pathlib import Path

from ops.censo_alarmas import (
    RAIZ_TERRAFORM,
    VALORES,
    alarmas,
    alarmas_sin_asercion,
    aserciones_de_treat_missing_data,
    ficheros_tf,
)

#: Alarmas cuyo `treat_missing_data` NO lo fija ninguna aserción de Terraform.
#: Se declaran aquí con el valor VIGENTE (medido del `.tf`, no elegido) para que
#: cambiarlo ponga esto en rojo: mientras `infra/` no se toque, esta es su única
#: aserción. **Ninguna trae una razón escrita en ningún sitio del repo**, y eso es
#: parte del hallazgo: no se inventa una a posteriori — se nombra el hueco.
SIN_ASERCION_EN_TERRAFORM: dict[str, tuple[str, str]] = {
    "dlq_depth": (
        "breaching",
        "INTOCABLE en ALARM_CATALOG (instrumento del canary de T-2.70) y aun así su silencio "
        "no lo fija ninguna aserción. Sin razón escrita en el repo.",
    ),
    "iot_rule_errors": (
        "breaching",
        "INTOCABLE en ALARM_CATALOG. Métrica de filtro de log (Takab/Ops/IoTRuleErrors): su "
        "ausencia y su cero se parecen mucho, y la decisión no está razonada en ningún sitio.",
    ),
    "ec2_cpu": (
        "breaching",
        "Silenciable, y la única de las tres que además duplicaría el aviso de `ec2_status` "
        "(también `breaching`) cuando la instancia se apaga. Sin razón escrita en el repo.",
    ),
}


def _censo() -> dict:
    censo = alarmas()
    assert censo, (
        f"no se encontró NINGUNA alarma bajo {RAIZ_TERRAFORM}: el censo estaría vacío y todo "
        "lo de abajo pasaría por vacuidad"
    )
    return censo


# ------------------------------------------------------- 0 · el censo mide algo


def test_el_censo_recorre_el_terraform_entero_y_sabe_leer_una_alarma(tmp_path: Path) -> None:
    """**Control positivo: sin esto, los tres tests de abajo podrían querer decir
    "el detector no detecta".** Se le da un módulo sintético FUERA de
    `observability` y tiene que verlo, con su valor y su fichero."""
    modulo = tmp_path / "modules" / "inventado"
    modulo.mkdir(parents=True)
    (modulo / "alarmas.tf").write_text(
        'resource "aws_cloudwatch_metric_alarm" "sonda" {\n'
        '  alarm_name         = "takab-dev-sonda"\n'
        '  alarm_description  = "una llave suelta } dentro de una cadena no rompe el conteo"\n'
        '  treat_missing_data = "ignore"\n'
        "}\n",
        encoding="utf-8",
    )
    censo = alarmas(tmp_path)
    assert set(censo) == {"sonda"}
    assert censo["sonda"].treat_missing_data == "ignore"
    assert censo["sonda"].fichero == "modules/inventado/alarmas.tf"

    reales = ficheros_tf()
    assert len(reales) >= 20, (
        f"solo se recorrieron {len(reales)} ficheros .tf: el ámbito volvió a encogerse"
    )


def test_el_ambito_ya_no_es_un_solo_fichero() -> None:
    """El segundo criterio de la ficha, medido en vez de prometido. Hoy todas las
    alarmas viven en `observability/main.tf` —y por eso era deuda y no defecto—
    pero el censo NO lo da por supuesto: recorre `infra/terraform` entero, así que
    la primera alarma que nazca en otro módulo entra sola y sin aviso previo."""
    censo = _censo()
    ficheros = {a.fichero for a in censo.values()}
    assert ficheros, "ninguna alarma tiene fichero: el censo perdió su origen"
    # No se exige que estén repartidas: se exige que el censo las encuentre estén
    # donde estén. Que hoy sea una sola ruta es una MEDICIÓN, no una suposición.
    assert len(censo) >= 11, f"el censo encogió a {len(censo)} alarmas: {sorted(censo)}"


# --------------------------------------- 1 · toda alarma declara su silencio


def test_toda_alarma_declara_su_treat_missing_data() -> None:
    """Sin la clave, CloudWatch aplica `missing` — el valor que suena a "retiene"
    y no retiene. Heredarlo por olvido es cómo una alarma nace muda."""
    censo = _censo()
    sin_declarar = sorted(r for r, a in censo.items() if not a.declara_treat_missing_data)
    assert not sin_declarar, (
        f"alarma(s) sin `treat_missing_data`: {sin_declarar}. El default de CloudWatch es "
        "`missing` (INSUFFICIENT_DATA) y solo avisa si la alarma tiene "
        "`insufficient_data_actions`: decídelo por escrito, no lo heredes."
    )

    ilegibles = sorted(
        r for r, a in censo.items() if a.declara_treat_missing_data and a.treat_missing_data is None
    )
    assert not ilegibles, (
        f"el censo no sabe resolver el `treat_missing_data` de {ilegibles} (¿variable, `try()`, "
        "expresión?). No se calla: o se escribe literal, o esta guardia deja de vigilarlas."
    )

    raros = {
        r: a.treat_missing_data for r, a in censo.items() if a.treat_missing_data not in VALORES
    }
    assert not raros, f"valores que CloudWatch no acepta: {raros}"


def test_el_valor_missing_no_puede_ir_sin_accion_de_insufficient_data() -> None:
    """La regla de emparejamiento que costó 17 h de gabinete caído el 29-jul-2026:
    `missing` NO retiene el estado, lleva a INSUFFICIENT_DATA. Sin
    `insufficient_data_actions` la alarma no MIENTE — se CALLA, que para enterarse
    da igual. Estaba escrita en la cabecera del `.tftest.hcl` y en un comentario;
    aquí se impone para toda alarma, incluidas las que aún no existen."""
    mudas = sorted(
        r
        for r, a in _censo().items()
        if a.treat_missing_data == "missing" and not a.tiene_accion_de_insufficient_data
    )
    assert not mudas, (
        f"alarma(s) en `missing` SIN `insufficient_data_actions`: {mudas}. Con `missing` el "
        "silencio lleva a INSUFFICIENT_DATA y ese estado no avisa a nadie por su cuenta."
    )


# ------------------------------- 2 · toda alarma tiene su valor fijado por algo


def test_toda_alarma_tiene_su_treat_missing_data_fijado_por_una_asercion() -> None:
    """**El criterio de la ficha.** La lista sale del `.tf`; las aserciones salen
    de los `.tftest.hcl`. Una alarma nueva sin aserción cae aquí y no hay forma de
    que nazca en silencio: o se le escribe su bloque en Terraform, o se declara en
    `SIN_ASERCION_EN_TERRAFORM` con su valor y su razón."""
    censo = _censo()
    fijadas = aserciones_de_treat_missing_data()
    assert fijadas, (
        "no se encontró ni una aserción de `treat_missing_data` en los .tftest.hcl: el test "
        "estaría comparando contra el vacío y aprobaría cualquier cosa"
    )

    huerfanas = alarmas_sin_asercion(censo, fijadas, SIN_ASERCION_EN_TERRAFORM)
    assert not huerfanas, (
        f"alarma(s) sin aserción de `treat_missing_data`: {huerfanas}. Elegir mal ese valor no "
        "rompe el plan ni el validate: produce una alarma que miente. Escríbele su bloque en "
        "`modules/observability/tests/treat_missing_data.tftest.hcl` (ahí vive la regla de "
        "decisión) o decláralo aquí con su razón."
    )

    fantasmas = sorted(set(SIN_ASERCION_EN_TERRAFORM) - set(censo))
    assert not fantasmas, (
        f"`SIN_ASERCION_EN_TERRAFORM` nombra alarma(s) que ya no existen: {fantasmas}"
    )

    ya_asertadas = sorted(set(SIN_ASERCION_EN_TERRAFORM) & set(fijadas))
    assert not ya_asertadas, (
        f"{ya_asertadas} ya tienen aserción en Terraform: sácalas de la lista de huecos — un "
        "punto ciego que se arregló y sigue declarado hace que se lea la lista con desconfianza"
    )


def test_el_veredicto_sabe_ponerse_rojo_con_una_alarma_nueva() -> None:
    """**El otro control positivo, y el que de verdad importa aquí.** El test de
    arriba está verde porque hoy toda alarma está cubierta; eso no demuestra que
    sepa cazar la siguiente. Se le da un censo sintético con una alarma recién
    nacida —ni aserción, ni hueco declarado— y tiene que señalarla."""
    censo = {"gateway_offline": None, "alarma_recien_nacida": None}
    fijadas = {"gateway_offline": {"breaching"}}
    assert alarmas_sin_asercion(censo, fijadas, {}) == ["alarma_recien_nacida"]
    # y una alarma declarada como hueco NO se señala: si no, la lista de puntos
    # ciegos sería inútil y nadie podría dejar el test en verde con honestidad.
    assert alarmas_sin_asercion(censo, fijadas, {"alarma_recien_nacida": ("x", "y")}) == []


def test_lo_que_declara_el_tf_y_lo_que_asierta_el_test_son_el_mismo_valor() -> None:
    """La aserción y el recurso son dos copias del mismo número, y dos copias
    divergen. Aquí se contrastan sin credenciales y sin `terraform test`: si
    alguien cambia `main.tf` y no la aserción (o al revés), esto cae en la suite
    del API, que sí corre en cada PR."""
    censo = _censo()
    fijadas = aserciones_de_treat_missing_data()
    divergen = {
        recurso: (censo[recurso].treat_missing_data, sorted(valores))
        for recurso, valores in fijadas.items()
        if recurso in censo and {censo[recurso].treat_missing_data} != valores
    }
    assert not divergen, (
        f"el Terraform y su aserción dicen cosas distintas {divergen} — o el recurso cambió sin "
        "revisar la decisión, o hay dos aserciones peleadas entre sí"
    )

    # La otra dirección: una aserción sobre una alarma que ya no existe. `terraform
    # test` moriría al planificar, pero solo si alguien lo corre; aquí cae en la
    # suite del API. Y sin esto, el bucle de arriba la SALTARÍA en silencio.
    huerfanas = sorted(set(fijadas) - set(censo))
    assert not huerfanas, (
        f"aserción de `treat_missing_data` sobre alarma(s) inexistentes: {huerfanas} — el recurso "
        "se renombró o se borró y su decisión quedó vigilando un fantasma"
    )


def test_los_huecos_declarados_fijan_el_valor_vigente() -> None:
    """Mientras `infra/` no se toque, ESTA es la única aserción que tienen las
    tres alarmas sin bloque en Terraform. No se conforma con nombrarlas: fija su
    valor medido, así que cambiarlo obliga a pasar por aquí."""
    censo = _censo()
    for recurso, (valor, razon) in SIN_ASERCION_EN_TERRAFORM.items():
        assert censo[recurso].treat_missing_data == valor, (
            f"{recurso} cambió su `treat_missing_data` a "
            f"{censo[recurso].treat_missing_data!r}: era {valor!r} y nadie más lo vigila"
        )
        assert len(razon) > 40, f"{recurso} está declarado sin razón legible"
