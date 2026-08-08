"""T-2.79 · El aviso como ARTEFACTO VERSIONADO, y el sello que lo identifica.

El motor es `SOFTWARE`; el texto legal es `LEGAL`. Esta tarea construye el motor
con un **texto provisional versionado** y deja el mecanismo para sustituirlo el
día que llegue el definitivo. Y lo que sigue es la parte que hay que entender
antes de tocar nada:

──────────────────────────────────────────────────────────────────────────────
POR QUÉ EL CONSENTIMIENTO SE ATA AL CONTENIDO Y NO AL NÚMERO DE VERSIÓN
──────────────────────────────────────────────────────────────────────────────
El criterio "cambiar el aviso no reescribe consentimientos anteriores" suena a
una tabla ``privacy_notices(version, body)`` con una FK desde ``consents``.
**Eso no lo cumple.** Si alguien EDITA el texto de la versión 3 —una errata, una
reescritura, un ``UPDATE`` mal hecho— todos los consentimientos que apuntaban a
la versión 3 pasan a apuntar en silencio a un texto distinto del que se aceptó.
La FK sigue íntegra, la etiqueta sigue diciendo "3", el test de integridad
referencial sigue verde y **el registro miente**.

Por eso la identidad de un aviso es el **digest SHA-256 de lo que la persona
lee**, y el consentimiento guarda **una copia sellada de ese digest**. Editar el
texto mueve el digest en el acto, y el consentimiento de ayer queda declarado
obsoleto sin que nadie tenga que acordarse de invalidarlo.

Es el mismo candado que ``notify/whatsapp_templates/*.json`` (T-2.77): allí el
sello prueba que el texto del repo sigue siendo el que Meta aprobó; aquí prueba
que el texto de hoy sigue siendo el que la persona aceptó. Y la misma honestidad:
esto atrapa la deriva accidental —la que ocurre—, no a quien reescriba el digest
a propósito. Ningún mecanismo dentro del repo puede atrapar eso.

──────────────────────────────────────────────────────────────────────────────
QUÉ ENTRA EN EL DIGEST, Y QUÉ NO
──────────────────────────────────────────────────────────────────────────────
Entra **exactamente lo que se muestra**: ``locale``, ``title`` y ``body``. NO
entra la etiqueta de versión, y es deliberado en las dos direcciones:

* republicar el MISMO texto con otra etiqueta no invalida nada (no hubo cambio
  de aviso), y el índice único ``(tenant, purpose, locale, digest)`` lo rechaza
  como duplicado: **una versión nueva sin texto nuevo no es una versión**;
* corregir una coma SÍ invalida, aunque la etiqueta no se toque.

Tampoco hay un "resumen" o unas viñetas aparte del cuerpo. Un resumen que se
enseña pero no se sella es justo el agujero que esto cierra: la persona lee A y
consiente el digest de B. La app pinta párrafos partiendo el propio ``body``.

La forma canónica lleva **la longitud de cada campo delante**::

    takab.privacy-notice.v1\\n<len>:<locale>\\n<len>:<title>\\n<len>:<body>

Sin los prefijos, ``title="A\\nB", body="C"`` y ``title="A", body="B\\nC"`` dan
la misma cadena y el mismo digest — dos avisos distintos indistinguibles. La
longitud se cuenta en **puntos de código** (``len()`` en Python,
``char_length()`` en SQL) para que las dos implementaciones coincidan con
acentos y con emoji fuera del BMP.

La mitad SQL de esta función vive en ``db/schema.sql``
(``privacy_notice_digest``) y es la que calcula la columna GENERATED de
``privacy_notices``: quien inserta **no puede elegir el sello**. Que las dos
implementaciones coinciden lo prueba ``tests/test_privacy_engine.py`` sobre
siete entradas, no sobre una.

──────────────────────────────────────────────────────────────────────────────
DE DÓNDE SALE EL AVISO: REPO (plataforma) o TABLA (tenant)
──────────────────────────────────────────────────────────────────────────────
* **Plataforma** — este directorio (``texts/*.json``), versionado en git. Es el
  aviso por defecto y es lo que se sirve a un tenant que no ha publicado el suyo.
  No hay fila en la base: la identidad es el digest, así que no hace falta. Y
  así el texto legal no acaba duplicado dentro de una migración.
* **Tenant** — una fila de ``privacy_notices``. Un hospital o una dependencia es
  el *responsable* de los datos de su propia gente y publica SU aviso; el más
  específico gana (ver ``store.current_notice``).

El artefacto declara además si el texto está **sellado por LEGAL**
(``legal_review.status == 'APPROVED'`` y ``approved_digest`` cuadrando con el
digest del bloque ``notice``). Mientras no lo esté, el aviso viaja marcado
``provisional`` hasta la pantalla del usuario. Sustituir el texto es **publicar
otra versión**, nunca editar la que ya se sirvió.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("takab_api.privacy")

#: Prefijo de dominio de la forma canónica. Va dentro del hash para que el
#: digest de un aviso no pueda coincidir por accidente con el de otro artefacto
#: sellado del proyecto (p. ej. una plantilla de WhatsApp).
CANON_PREFIX = "takab.privacy-notice.v1"

APPROVED = "APPROVED"
PROVISIONAL = "PROVISIONAL"

#: Propósitos del motor. ``privacy_notice`` es el aviso; ``whatsapp_alerts`` es
#: el opt-in que Meta exige antes de escribir a un número (T-2.77). Espejo del
#: CHECK de ``privacy_notices.purpose``/``privacy_consents.purpose``.
PURPOSES: tuple[str, ...] = ("privacy_notice", "whatsapp_alerts")

TEXTS_DIR = Path(__file__).resolve().parent / "texts"


def notice_digest(locale: str, title: str, body: str) -> str:
    """SHA-256 de lo que la persona lee, en forma canónica con longitudes.

    Espejo exacto de ``privacy_notice_digest(text,text,text)`` en SQL. Si cambias
    una, cambia la otra: ``test_digest_de_python_coincide_con_el_de_sql`` compara
    las dos sobre entradas con acentos, emoji y saltos de línea.
    """
    canon = "\n".join(
        (
            CANON_PREFIX,
            f"{len(locale)}:{locale}",
            f"{len(title)}:{title}",
            f"{len(body)}:{body}",
        )
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class NoticeSpec:
    """Un aviso del repo, ya validado, con su sello de revisión legal."""

    purpose: str
    locale: str
    version: str
    title: str
    body: str
    digest: str
    status: str
    approved_digest: str
    source: str
    defect: str = ""

    @property
    def provisional_reason(self) -> str:
        """Por qué este texto NO está sellado por LEGAL (vacío = sí lo está).

        Se devuelve la razón y no un booleano porque este texto acaba en la
        pantalla del usuario y en el `meta` de la auditoría: decir "provisional"
        sin decir por qué es media respuesta.
        """
        if self.defect:
            return self.defect
        if self.status != APPROVED:
            return (
                f"revisión legal en estado {self.status}: el texto es un marcador "
                "de posición hasta que LEGAL entregue el definitivo"
            )
        if not self.approved_digest:
            return "sin approved_digest: nadie ha sellado qué texto revisó LEGAL"
        if self.approved_digest != self.digest:
            return (
                "el digest del texto no coincide con el revisado: el cuerpo cambió "
                "en el repo y hay que volver a pasarlo por LEGAL"
            )
        return ""

    @property
    def provisional(self) -> bool:
        return bool(self.provisional_reason)

    @property
    def usable(self) -> bool:
        """Un texto con DEFECTO no se sirve; uno provisional sí.

        La diferencia importa: servir un aviso provisional marcado como tal es
        honesto y es lo que esta fase autoriza. Servir un artefacto roto (sin
        cuerpo, con un locale inválido) sería servir un aviso que no existe.
        """
        return not self.defect

    @property
    def paragraphs(self) -> tuple[str, ...]:
        """El cuerpo partido en párrafos, para pintarlo sin inventar un resumen."""
        return tuple(p.strip() for p in self.body.split("\n\n") if p.strip())

    @classmethod
    def from_document(cls, doc: dict, source: str) -> NoticeSpec:
        """Construye la spec y **no revienta**: un artefacto inválido nace con
        ``defect`` puesto. Levantar aquí dejaría la API sin arrancar y, con ella,
        sin aviso que servir — que es peor que servir el de plataforma anterior.
        """
        notice = doc.get("notice") or {}
        review = doc.get("legal_review") or {}
        locale = str(notice.get("locale") or "")
        title = str(notice.get("title") or "")
        body = str(notice.get("body") or "")
        spec = cls(
            purpose=str(doc.get("purpose") or ""),
            locale=locale,
            version=str(notice.get("version") or ""),
            title=title,
            body=body,
            digest=notice_digest(locale, title, body),
            status=str(review.get("status") or "").upper() or PROVISIONAL,
            approved_digest=str(review.get("approved_digest") or ""),
            source=source,
        )
        defect = _defect_of(spec)
        return spec if not defect else cls(**{**spec.__dict__, "defect": defect})


def _defect_of(spec: NoticeSpec) -> str:
    """Lo que hace inservible a un artefacto ANTES de mirar su revisión legal."""
    if spec.purpose not in PURPOSES:
        return f"purpose {spec.purpose!r} desconocido (esperado uno de {PURPOSES})"
    if len(spec.locale) != 5 or spec.locale[2] != "-":
        return f"locale {spec.locale!r} inválido (esperado ll-CC, p. ej. es-MX)"
    if not spec.version.strip():
        return "sin etiqueta de versión: un aviso sin versión no se puede citar"
    if len(spec.title.strip()) < 8:
        return "sin título utilizable"
    if len(spec.body.strip()) < 40:
        return "cuerpo demasiado corto para ser un aviso (¿marcador sin rellenar?)"
    return ""


@dataclass(frozen=True)
class NoticeCatalog:
    """Los avisos de PLATAFORMA del repo, indexados por (propósito, locale)."""

    notices: tuple[NoticeSpec, ...] = ()

    @classmethod
    def load(cls, directory: Path | str = TEXTS_DIR) -> NoticeCatalog:
        """Lee ``*.json`` del directorio. **Nunca levanta**: un artefacto
        ilegible se salta con un ERROR ruidoso y los sanos siguen sirviendo."""
        found: list[NoticeSpec] = []
        for path in sorted(Path(directory).glob("*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                found.append(NoticeSpec.from_document(doc, source=path.name))
            except (OSError, ValueError, TypeError) as exc:
                logger.error(
                    "aviso de privacidad ilegible %s (%s) — se omite; los tenants sin "
                    "aviso propio se quedarán sin texto que mostrar",
                    path.name,
                    type(exc).__name__,
                )
        for spec in found:
            if spec.defect:
                logger.error(
                    "aviso de privacidad %s INSERVIBLE: %s", spec.source, spec.defect
                )
        return cls(notices=tuple(found))

    def get(self, purpose: str, locale: str) -> NoticeSpec | None:
        """El aviso de plataforma para ese propósito y locale, o ``None``.

        Sin caso alterno por idioma a propósito: servir un aviso en otro idioma
        del que la persona pidió es servir un texto que puede no entender, y un
        consentimiento sobre un texto que no se entiende no es un consentimiento.
        """
        return next(
            (n for n in self.notices if n.usable and n.purpose == purpose and n.locale == locale),
            None,
        )


@lru_cache(maxsize=1)
def get_catalog() -> NoticeCatalog:
    """El catálogo del repo, leído una vez por proceso.

    Los artefactos son ficheros de git: cambian con un despliegue, no en
    caliente. Los tests que necesiten releer llaman a
    ``get_catalog.cache_clear()`` — el mismo seam que usan los demás módulos con
    ``lru_cache`` de este proyecto.
    """
    return NoticeCatalog.load()
