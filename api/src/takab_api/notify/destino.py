"""Qué se puede enseñar de un destinatario de notificación (T-5.15).

`GET /incidents/{id}/notifications` contesta *"¿quién recibió la alerta?"*, y esa
pregunta se contesta con datos de contacto: correos, teléfonos y URLs de webhook.
Este módulo es el filtro entre la fila de `notification_jobs` y la pantalla.

**Allowlist por FORMA, no denylist**, exactamente por el motivo que
`narrative/redact.py` deja escrito: con una denylist, el canal que se añada
mañana trae una forma de `target` que nadie previó y **sale entero por omisión**.
Aquí lo que no encaja en una forma conocida no sale — y lo dice, en vez de
callarlo, para que la pantalla escriba «destinatario no reconocido» en lugar de
un hueco que se lee como «no había destinatario».

**La URL de un webhook ES la credencial.** Un `https://…/services/T0/B0/xoxb…`
autoriza a publicar a cualquiera que lo lea; por eso de un webhook sale el host
y nada más — ni ruta, ni query, ni la autoridad con usuario y contraseña.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

#: Nombre del cajón de lo que no se reconoce. Es un valor propio y no `None`
#: para que la pantalla pueda decirlo en voz alta.
DESCONOCIDO = "desconocido"

#: Cuántos dígitos finales de un teléfono bastan para reconocerlo sin dictarlo.
_COLA_TELEFONO = 4
#: Mínimo para que enmascarar signifique algo. Por debajo, el enmascarado
#: enseñaría casi el número entero, así que se calla del todo: enmascarar mal es
#: peor que no enmascarar.
_MIN_TELEFONO = 8


@dataclass(frozen=True)
class DestinoResumen:
    """Lo que la consola puede decir del destinatario de un job."""

    #: `correo` | `telefono` | `webhook` | `dispositivos` | `desconocido`.
    kind: str
    #: Cuántos destinatarios, o `None` cuando la forma no permite contarlos.
    count: int | None
    #: Texto mínimo para reconocerlo. **Nunca** el dato de contacto completo.
    hint: str
    #: `True` = la forma no encajó en ninguna conocida y no sale nada de ella.
    unrecognised: bool = False


_NADA = DestinoResumen(kind=DESCONOCIDO, count=None, hint="", unrecognised=True)


def _correo(direccion: str) -> str:
    """`ops@cliente.com` → `o***@cliente.com`.

    El dominio entero sale porque identifica a la organización y no a la persona;
    del buzón sale la inicial, que basta para distinguir `ops@` de `seguridad@`
    a quien ya conoce la lista, y no para teclearlo.
    """
    local, _, dominio = direccion.partition("@")
    if not local or not dominio:
        return "•••"
    return f"{local[0]}***@{dominio}"


def _telefono(numero: str) -> str:
    """`+525512345678` → `+••••••••5678`.

    NO se intenta separar el prefijo de país. La primera versión de esto lo
    dedujo del largo total y acertaba con México y mentía con `+1` y con `+351`:
    el ancho del prefijo varía por país y aquí no hay forma de saberlo. Un
    prefijo inventado en una pantalla de evidencia es peor que un dígito menos,
    así que **todo se enmascara menos la cola**, que es lo único que sirve para
    reconocer el número sin poder teclearlo.
    """
    digitos = "".join(c for c in numero if c.isdigit())
    if len(digitos) < _MIN_TELEFONO:
        return "•••"
    mas = "+" if numero.strip().startswith("+") else ""
    return f"{mas}{'•' * (len(digitos) - _COLA_TELEFONO)}{digitos[-_COLA_TELEFONO:]}"


def _host(url: str) -> str:
    """Host de la URL, sin ruta, sin query y sin la autoridad con credenciales."""
    partes = urlsplit(url)
    return partes.hostname or "•••"


def resumen_destino(channel: str, target: object) -> DestinoResumen:
    """Resumen publicable del destinatario de un job, o el cajón de lo no reconocido."""
    if not isinstance(target, dict) or not target:
        return _NADA

    if channel == "email":
        to = target.get("to")
        if isinstance(to, str):
            to = [to]
        if isinstance(to, list) and to and all(isinstance(x, str) and x for x in to):
            return DestinoResumen("correo", len(to), ", ".join(_correo(x) for x in to))
        return _NADA

    if channel in ("sms", "whatsapp"):
        to = target.get("to")
        if isinstance(to, str):
            return DestinoResumen("telefono", 1, _telefono(to))
        return _NADA

    if channel == "webhook":
        url = target.get("url")
        if isinstance(url, str) and url:
            return DestinoResumen("webhook", 1, _host(url))
        return _NADA

    if channel == "push":
        # Un sitio y una clase de push NO son datos de una persona: el job va a
        # los dispositivos registrados del inmueble, y cuántos son se sabe en el
        # despacho, no aquí. Por eso `count` es None y no cero.
        sitio = target.get("site_id")
        clase = target.get("push_class")
        if isinstance(sitio, str) and isinstance(clase, str):
            return DestinoResumen("dispositivos", None, f"{clase} · sitio {sitio[:8]}")
        return _NADA

    return _NADA
