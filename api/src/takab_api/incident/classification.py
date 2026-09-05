"""Clasificación de incidentes — la tasa de falsos positivos (T-5.12).

**El problema que cierra.** Cerrar un incidente no pedía ni admitía una razón, así
que la tasa de falsos positivos —la métrica que decide si un cliente renueva— no
era calculable ni a mano sobre la base. La ironía la documentaba el propio
código: el documento de entrega **se deslinda expresamente de los falsos
positivos de SASMEX**, y el sistema no medía ninguno.

**Catálogo cerrado y corto**, decidido en la ficha y anclado por el CHECK de la
tabla. Cuatro y no más: cada valor adicional es una casilla que alguien tiene que
entender a las 3 de la mañana, y un catálogo largo se convierte en «lo dejo en el
primero».

**`indeterminado` se ELIGE.** No hay valor por defecto y no lo puede haber: un
default silencioso convertiría «nadie lo revisó» en «se revisó y no se supo», que
son cosas distintas y **solo la primera pide trabajo**. Los no clasificados no
tienen fila, y el agregado los cuenta APARTE en vez de excluirlos del denominador
— un porcentaje calculado sobre lo clasificado, con lo no clasificado escondido,
es peor que no tener el número.

**Corregir INSERTA.** Igual que la cadena de dictámenes: una clasificación nueva
declara a cuál sustituye y las dos quedan. Quien clasificó mal no puede hacer
desaparecer su clasificación.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Catálogo cerrado. El orden es el de la interfaz, de más común a menos.
CLASIFICACIONES: tuple[str, ...] = ("real", "falso_positivo", "prueba", "indeterminado")

#: Qué significa cada una, en la lengua de quien la elige a las 3 de la mañana.
SIGNIFICADO: dict[str, str] = {
    "real": "Hubo un evento: el sistema hizo lo que tenía que hacer.",
    "falso_positivo": "No hubo evento. Es la casilla que decide si el cliente renueva.",
    "prueba": "Prueba, mantenimiento o puesta en marcha. No cuenta como falso positivo.",
    "indeterminado": "Se revisó y NO se pudo determinar. Distinto de no haberlo revisado.",
}

#: Las que cuentan en el denominador de la tasa. `prueba` NO: un incidente
#: provocado a propósito no dice nada sobre si el sistema molesta.
EN_LA_TASA: frozenset[str] = frozenset({"real", "falso_positivo", "indeterminado"})


class ClasificacionInvalida(ValueError):
    """Un valor fuera del catálogo. No se normaliza: se rechaza."""


def validar(valor: str) -> str:
    if valor not in CLASIFICACIONES:
        raise ClasificacionInvalida(
            f"clasificación desconocida: {valor!r}. Válidas: {', '.join(CLASIFICACIONES)}"
        )
    return valor


@dataclass(frozen=True)
class Tasa:
    """El desglose de una ventana. Los ``sin_clasificar`` van SIEMPRE a la vista.

    ``tasa_falsos_positivos`` es ``None`` —no cero— cuando no hay nada
    clasificado en la ventana: un cero afirmaría que no hubo falsos positivos, y
    lo que ocurre es que nadie miró. La diferencia es exactamente la que este
    módulo existe para no volver a perder.
    """

    desde: str
    hasta: str
    total: int
    sin_clasificar: int
    por_clasificacion: dict[str, int]

    @property
    def clasificados(self) -> int:
        return sum(self.por_clasificacion.values())

    @property
    def en_la_tasa(self) -> int:
        return sum(n for c, n in self.por_clasificacion.items() if c in EN_LA_TASA)

    @property
    def tasa_falsos_positivos(self) -> float | None:
        base = self.en_la_tasa
        if base == 0:
            return None
        return self.por_clasificacion.get("falso_positivo", 0) / base
