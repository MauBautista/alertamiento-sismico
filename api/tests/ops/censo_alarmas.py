"""Censo de alarmas de CloudWatch derivado del Terraform (T-2.72.d).

No es un test: es la derivación que usan los tests que no quieren enumerar
alarmas a mano. Vive aparte por eso — dos guardias la comparten
(`test_treat_missing_data.py` y `test_muting.py`) y una lista escrita a mano en
cada una divergiría, que es el defecto que esta ficha cierra.

**El ámbito es TODO `infra/terraform`, no un fichero.** La guardia anterior leía
solo `modules/observability/main.tf`: una alarma declarada en otro módulo nacía
sin clasificar y nada lo delataba. Hoy no hay ninguna fuera de ahí —el censo lo
mide, no lo supone— y el día que la haya, entra sola.

Todas las funciones toman la raíz como parámetro: sin esa costura no se puede
comprobar que el detector detecta, y un censo que no se ha probado contra una
muestra es un verde que significa "no sé".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

RAIZ_TERRAFORM = Path(__file__).resolve().parents[3] / "infra/terraform"

_RECURSO = re.compile(r'resource\s+"aws_cloudwatch_metric_alarm"\s+"([a-z0-9_]+)"\s*\{')
_LITERAL = re.compile(r'treat_missing_data\s*=\s*"([A-Za-z]+)"')
_CUALQUIER_VALOR = re.compile(r"treat_missing_data\s*=\s*(.+)")

#: `aws_cloudwatch_metric_alarm.<recurso>[…].treat_missing_data == "<valor>"`
_ASERCION = re.compile(
    r'aws_cloudwatch_metric_alarm\.([a-z0-9_]+)(?:\[[^\]]*\])?\.treat_missing_data\s*==\s*"(\w+)"'
)

#: Los cuatro valores que acepta CloudWatch. `missing` es el DEFECTO cuando no se
#: escribe ninguno, y es el que más engaña: suena a "retiene" y lleva a
#: INSUFFICIENT_DATA (probado en vivo el 29-jul-2026, ver la cabecera de
#: `modules/observability/tests/treat_missing_data.tftest.hcl`).
VALORES = frozenset({"breaching", "notBreaching", "ignore", "missing"})


@dataclass(frozen=True)
class Alarma:
    """Una alarma tal y como la declara el Terraform."""

    recurso: str
    fichero: str
    cuerpo: str

    @property
    def treat_missing_data(self) -> str | None:
        """El valor LITERAL, o ``None`` si no lo hay o no se puede resolver."""
        m = _LITERAL.search(self.cuerpo)
        return m.group(1) if m else None

    @property
    def declara_treat_missing_data(self) -> bool:
        """Si la clave aparece, aunque su valor sea una expresión o una variable.

        Distinguirlo del caso anterior es lo que permite NOMBRAR el punto ciego:
        "no lo declara" y "lo declara con algo que no sé leer" son fallos
        distintos y piden arreglos distintos.
        """
        return _CUALQUIER_VALOR.search(self.cuerpo) is not None

    @property
    def tiene_accion_de_insufficient_data(self) -> bool:
        return "insufficient_data_actions" in self.cuerpo


def _bloque(texto: str, inicio: int) -> str:
    """Cuerpo del bloque HCL que abre en ``inicio`` (la llave), contando llaves y
    saltándose las cadenas — un `"${each.value}"` trae llaves balanceadas, pero
    una `}` suelta dentro de una descripción rompería el conteo ingenuo."""
    profundidad = 0
    dentro_de_cadena = False
    i = inicio
    while i < len(texto):
        c = texto[i]
        if dentro_de_cadena:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                dentro_de_cadena = False
        elif c == '"':
            dentro_de_cadena = True
        elif c == "{":
            profundidad += 1
        elif c == "}":
            profundidad -= 1
            if profundidad == 0:
                return texto[inicio : i + 1]
        i += 1
    return texto[inicio:]


def ficheros_tf(raiz: Path = RAIZ_TERRAFORM) -> list[Path]:
    return sorted(raiz.rglob("*.tf"))


def ficheros_tftest(raiz: Path = RAIZ_TERRAFORM) -> list[Path]:
    return sorted(raiz.rglob("*.tftest.hcl"))


def alarmas(raiz: Path = RAIZ_TERRAFORM) -> dict[str, Alarma]:
    """Toda alarma declarada bajo ``raiz``, venga del módulo que venga."""
    censo: dict[str, Alarma] = {}
    for ruta in ficheros_tf(raiz):
        texto = ruta.read_text(encoding="utf-8")
        for m in _RECURSO.finditer(texto):
            cuerpo = _bloque(texto, texto.index("{", m.end() - 1))
            censo[m.group(1)] = Alarma(
                recurso=m.group(1),
                fichero=str(ruta.relative_to(raiz)),
                cuerpo=cuerpo,
            )
    return censo


def alarmas_sin_asercion(
    censo: dict[str, Alarma] | set[str],
    fijadas: dict[str, set[str]] | set[str],
    declaradas: dict[str, object] | set[str],
) -> list[str]:
    """Las que nadie fija: ni una aserción de Terraform, ni un hueco declarado.

    Es una función y no tres líneas dentro del test para que el veredicto se pueda
    probar contra un censo SINTÉTICO. Un guardia que solo se ha visto en verde
    contra la realidad de hoy no ha demostrado que sepa ponerse rojo.
    """
    return sorted(set(censo) - set(fijadas) - set(declaradas))


def aserciones_de_treat_missing_data(raiz: Path = RAIZ_TERRAFORM) -> dict[str, set[str]]:
    """``{recurso: {valores fijados}}`` según los `*.tftest.hcl`, todos ellos."""
    fijado: dict[str, set[str]] = {}
    for ruta in ficheros_tftest(raiz):
        for recurso, valor in _ASERCION.findall(ruta.read_text(encoding="utf-8")):
            fijado.setdefault(recurso, set()).add(valor)
    return fijado
