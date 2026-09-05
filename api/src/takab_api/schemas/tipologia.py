"""Catálogo de tipología de inmueble, tal como sale por la API (T-5.16 · D-28)."""

from __future__ import annotations

from pydantic import BaseModel


class BuildingTypeOut(BaseModel):
    """Un tipo del catálogo, con su banda de REFERENCIA o la razón de no tenerla."""

    value: str
    label: str
    #: `None` = el blueprint no publica banda para esta tipología. NO se le presta
    #: la de otro tipo: eso es el defecto que abre `T-5.16`.
    banda: dict[str, float] | None
    #: Por qué no hay banda. La ausencia se explica; callarla se lee como olvido.
    sin_banda_por_que: str | None = None


class BuildingTypeCatalog(BaseModel):
    """El catálogo entero, y la declaración de que solo SUGIERE.

    `resuelve_umbrales` viaja en el cuerpo y no en un comentario porque la
    consola tiene que poder escribirlo en pantalla: un catálogo que llegara
    pelado invitaría a que la siguiente pantalla lo aplicara sola.
    """

    resuelve_umbrales: bool
    por_que_no_resuelve: list[str]
    sin_referencia_de_pgv: str
    items: list[BuildingTypeOut]
