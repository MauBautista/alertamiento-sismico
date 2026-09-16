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

Cuando los cuatro lleguen, **es UNA edición**: se rellenan las constantes de
abajo, se regenera la hoja en blanco y el mismo commit lleva las dos cosas.
⚠️ Y tiene que llevarlas: `make drift` compara el artefacto comiteado, así que
editar esto sin regenerar pone el árbol en rojo — a propósito.
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
    #: Quién firma por TAKAB (nombre y cargo).
    firmante: str | None = None

    @property
    def completa(self) -> bool:
        return all(
            v is not None
            for v in (self.razon_social, self.domicilio, self.clasificacion, self.firmante)
        )

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


#: La identidad de TAKAB. **Los cuatro valores siguen en `None` a propósito.**
#: Rellenarlos es la edición que cierra `PENDIENTES §4.8`.
TAKAB = Identidad()
