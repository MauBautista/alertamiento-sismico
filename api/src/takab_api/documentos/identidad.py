"""[T-7.21 · PENDIENTES §4.8] Quién emite el papel, y qué se hace mientras no se sepa.

Un documento firmado que sale a un cliente tiene que decir **quién lo emite**: la
razón social exacta, el domicilio que va al pie, cómo está clasificado (público o
confidencial) y quién firma por TAKAB.

**Nada de eso está en el repositorio, y no debe inventarse.** No es un descuido:
`PENDIENTES-MAURICIO §4.8` lo ficha como dato que aporta Mauricio, y un texto de
relleno que PAREZCA real —«TAKAB S.A. de C.V.», un domicilio verosímil— sería la
peor opción posible de las tres que había:

* **Rellenar con algo plausible.** Es afirmar una razón social falsa en un papel
  que va firmado y que un perito puede llevar a una reclamación. La mentira más
  cara que puede contar este producto, y además invisible: nadie revisa un pie.
* **No imprimir el bloque.** El documento sale sin emisor y parece completo. Es
  la misma clase de hueco mudo que el resto del sistema lleva tres bloques
  persiguiendo: un hueco se lee como «no aplica», que es lo contrario de «falta».
* **Imprimirlo DECLARANDO la ausencia.** Es lo que se hace aquí, y es la
  doctrina del repositorio aplicada a la papelería: lo que no se sabe se declara
  (`SIN DATO EXTERNO`, `S/D`, `NO MEDIDO`, `SIN LUGAR EN EL CATÁLOGO`). El papel
  dice qué le falta y a quién se lo pide.

**Los cuatro llegaron el 2026-09-19** y están abajo. El mecanismo de arriba NO
se retira: sigue siendo lo que pasa si mañana se añade un campo nuevo o se
revoca uno de éstos. Lo que cambió es que hoy no hay ninguno en `None`.

⚠️ Y una edición aquí **obliga a regenerar la hoja en el mismo commit**:
`make drift` compara el artefacto comiteado (`shared/brand/membrete/`), así que
tocar esto sin regenerar pone el árbol en rojo — a propósito.

    ( cd api && uv run python ../shared/brand/generar.py )
"""

from __future__ import annotations

from dataclasses import dataclass

#: Referencia que el papel cita cuando le falta un dato. Es el sitio donde está
#: fichado quién lo debe, no una excusa genérica.
PENDIENTE = "PENDIENTE · PENDIENTES-MAURICIO §4.8"


@dataclass(frozen=True)
class Identidad:
    """Quién emite el documento. `None` = no se sabe, y el papel lo dice."""

    #: Razón social EXACTA, como está registrada. No el nombre comercial.
    razon_social: str | None = None
    #: Domicilio fiscal que debe aparecer al pie.
    domicilio: str | None = None
    #: Clasificación del documento: público, confidencial…
    clasificacion: str | None = None
    #: Quién firma por TAKAB. Un nombre y su cargo, **o** la declaración de que
    #: no hay firmante nominal — ver `FIRMA_INSTITUCIONAL` y `D-36`. Lo que NO
    #: puede ser es `""`: eso imprimiría `PENDIENTE` (ver `completa`).
    firmante: str | None = None

    @property
    def completa(self) -> bool:
        """Completa = **ninguna línea del papel dice PENDIENTE**, ni más ni menos.

        ⚠️ Se deriva de `lineas()` a propósito. Antes era
        `all(v is not None ...)`, que es OTRO criterio: con `firmante=""` el
        objeto se declaraba completo **y a la vez** el papel imprimía
        `PENDIENTE` en ese renglón y `aviso()` seguía avisando de que faltaba
        algo. Esa contradicción es justo lo que este módulo existe para impedir,
        y estaba armada esperando a la primera cadena vacía.
        """
        return all(v != PENDIENTE for _, v in self.lineas())

    def lineas(self) -> list[tuple[str, str]]:
        """`(rótulo, valor)` del bloque de emisor, con las ausencias declaradas.

        Devuelve SIEMPRE las cuatro: un bloque que encoge cuando falta un dato
        esconde que falta. El rótulo se queda y el valor dice quién lo debe.
        """
        return [
            ("RAZÓN SOCIAL", self.razon_social or PENDIENTE),
            ("DOMICILIO", self.domicilio or PENDIENTE),
            ("CLASIFICACIÓN", self.clasificacion or PENDIENTE),
            ("FIRMA POR TAKAB", self.firmante or PENDIENTE),
        ]

    def aviso(self) -> str | None:
        """La frase que el papel imprime mientras le falten datos, o `None`.

        No se calla y no se disfraza: quien reciba este documento tiene que poder
        distinguir un papel completo de uno al que le falta el emisor.
        """
        faltan = [r for r, v in self.lineas() if v == PENDIENTE]
        if not faltan:
            return None
        return (
            "DOCUMENTO SIN IDENTIDAD LEGAL COMPLETA: falta "
            + ", ".join(r.lower() for r in faltan)
            + ". El contenido técnico de este documento no depende de ese dato; "
            "su validez como papel membretado, sí."
        )


#: [D-36] Lo que va en el renglón de la firma cuando **no hay firmante nominal**.
#:
#: ⚠️ NO es `None`, y la diferencia importa: `None` significa «no se sabe» y el
#: papel imprimiría `PENDIENTE · PENDIENTES-MAURICIO §4.8`, que a partir del
#: 2026-09-19 sería FALSO — no falta el dato, está decidido que no lo hay. Un
#: hueco declarado como pendiente es tan engañoso como un hueco mudo cuando lo
#: que se sabe es la ausencia misma.
#:
#: Quien emite es la persona moral. El renglón lo dice en vez de dejar en blanco
#: un sitio donde el lector espera un nombre.
FIRMA_INSTITUCIONAL = "La persona moral emisora · este documento no lleva firmante nominal"

#: La identidad de TAKAB. Aportada por Mauricio el **2026-09-19**, cierra
#: `PENDIENTES §4.8`.
#:
#: ⚠️ La razón social va **literal, como está registrada**: sin acentos y con la
#: forma societaria detrás de la coma. No se «corrige» la ortografía de un
#: nombre legal — lo que va en un papel firmado es lo que dice el acta.
TAKAB = Identidad(
    razon_social=(
        "TAKAB, SISTEMAS TECNOLOGICOS INTELIGENTES & SERVICIOS INTEGRALES, S. de R.L. de C.V."
    ),
    domicilio="PRIV. 48 NORTE #1239 AGRICOLA RESURGIMIENTO, HEROICA PUEBLA DE ZARAGOZA, PUEBLA",
    clasificacion="USO INTERNO",
    firmante=FIRMA_INSTITUCIONAL,
)
