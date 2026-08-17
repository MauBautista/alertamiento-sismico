"""[T-2.150 · D-07] El teléfono del consentimiento deja de estar en claro.

EL PROBLEMA QUE RESUELVE
────────────────────────
Un sujeto identificado por teléfono tenía su número **en claro** en
``privacy_consents.subject_ref``, y esa tabla es **append-only por trigger**.
ARCO no lo alcanzaba: anonimizarlo exigía abrir un hueco en el guard, y el valor
entero de esa tabla es que no los tiene.

`D-07` eligió no elegir entre los dos bienes: el número deja de estar en claro y
**la fila del consentimiento no se toca jamás**.

CÓMO, EN TRES PIEZAS
─────────────────────
1. **``subject_ref`` pasa a ser un ÍNDICE DE BÚSQUEDA**, no el número: un
   HMAC-SHA256 sobre ``tenant || msisdn`` con una **pimienta que vive FUERA de la
   base**. Sigue permitiendo la única pregunta que el motor necesita hacer
   —«¿consintió este número?»— sin que la respuesta esté escrita en la fila.

2. **El número vive SELLADO en una tabla aparte** (``privacy_subject_secrets``),
   cifrado con AES-GCM bajo una clave maestra que tampoco vive en la base.

3. **Ejercer ARCO borra ESA fila.** El consentimiento queda byte a byte intacto:
   se conserva la prueba de **que** hubo consentimiento y **cuándo**, y
   desaparece la capacidad de leer **a quién**.

POR QUÉ NO HAY «CLAVE POR SUJETO», QUE ES LO QUE D-07 DECÍA LITERALMENTE
────────────────────────────────────────────────────────────────────────
La decisión describía «cifrado con clave por sujeto; ARCO destruye la clave».
El sellado ya es **por sujeto** —una fila por (tenant, índice)—, así que borrar
esa fila destruye exactamente lo mismo que destruiría su clave, sin un ciclo de
vida de claves que mantener. Las tres propiedades que `D-07` compraba se cumplen
enteras; lo que se ahorra es maquinaria que no añadía garantía.

LO QUE ESTO **NO** ES, Y HAY QUE DECIRLO
─────────────────────────────────────────
El índice **no es anónimo mientras exista la pimienta**. El espacio de teléfonos
es de ~10^10: con la pimienta en la mano, un HMAC se invierte por fuerza bruta en
nada. Lo que protege es el escenario real —**una copia de la base, sin los
secretos del despliegue**—, no a un atacante que ya tiene todo.

Y eso es **exactamente** la pregunta que `D-07` mandó al abogado: *¿un número
cifrado sigue siendo dato personal mientras exista la clave?* Este módulo no la
contesta; la implementa de forma que la respuesta pueda cambiarse sin rehacerlo.

FAIL-CLOSED, COMO EL RESTO DE LA CASA
──────────────────────────────────────
Sin pimienta o sin clave maestra configuradas, el camino del ``msisdn``
**se niega a funcionar**. No cae a texto en claro «por compatibilidad»: eso sería
escribir el defecto que esta ficha cierra, en silencio y para siempre, en una
tabla que no se puede reescribir. Es el mismo criterio que «sin clave HMAC
resoluble ⇒ 503» de los comandos.
"""

from __future__ import annotations

import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

#: Etiqueta de dominio del HMAC. Evita que la misma pimienta usada en otro sitio
#: produzca el mismo digest para el mismo teléfono: dos usos, dos espacios.
_DOMINIO = b"takab/privacy/subject-ref/v1"

#: Nonce de AES-GCM. 96 bits es el tamaño para el que GCM está especificado.
_NONCE_BYTES = 12


class PrivacyCryptoUnavailable(RuntimeError):
    """Faltan los secretos del despliegue. **Nunca se degrada a texto en claro.**

    Se distingue de un error de datos a propósito: quien la reciba tiene que
    devolver 503 —«el servicio no puede atender esto ahora»— y no un 400, que
    culparía al llamador de una configuración que no es suya.
    """


def _pepper(settings) -> bytes:  # noqa: ANN001 — Settings, import perezoso
    valor = (getattr(settings, "privacy_subject_pepper", "") or "").strip()
    if not valor:
        raise PrivacyCryptoUnavailable(
            "falta TAKAB_API_PRIVACY_SUBJECT_PEPPER: sin ella el índice de búsqueda "
            "del consentimiento por teléfono no se puede derivar, y escribir el "
            "número en claro es justo lo que T-2.150 cierra"
        )
    return valor.encode("utf-8")


def _master_key(settings) -> bytes:  # noqa: ANN001 — Settings, import perezoso
    valor = (getattr(settings, "privacy_subject_master_key", "") or "").strip()
    if not valor:
        raise PrivacyCryptoUnavailable(
            "falta TAKAB_API_PRIVACY_SUBJECT_MASTER_KEY: sin ella el teléfono no se "
            "puede sellar, y guardarlo en claro en una tabla append-only lo deja "
            "ahí para siempre"
        )
    clave = hashlib.sha256(valor.encode("utf-8")).digest()
    return clave  # 32 bytes ⇒ AES-256-GCM


def lookup_ref(settings, *, tenant_id: str, msisdn: str) -> str:  # noqa: ANN001
    """Índice de búsqueda del sujeto-teléfono. 64 hex, estable por tenant.

    **Lleva el ``tenant_id`` dentro a propósito** (regla de oro 5): el mismo
    número en dos clientes produce dos índices distintos, así que cruzar las dos
    tablas no revela que se trata de la misma persona. Sin eso, el índice sería
    un identificador global de la persona a través de clientes, que es más de lo
    que ningún cliente consintió.
    """
    mensaje = _DOMINIO + b"\x00" + tenant_id.encode("utf-8") + b"\x00" + msisdn.encode("utf-8")
    return hmac.new(_pepper(settings), mensaje, hashlib.sha256).hexdigest()


def seal(settings, *, msisdn: str) -> bytes:  # noqa: ANN001
    """Sella el número. Nonce aleatorio por sellado, prefijado al criptograma.

    Nonce nuevo cada vez aunque el número se repita: con GCM, reutilizar un par
    (clave, nonce) es catastrófico —no filtra «un poco», rompe la
    confidencialidad y la autenticación de los dos mensajes—. Por eso NO se
    deriva del teléfono ni del índice, que serían deterministas.
    """
    nonce = os.urandom(_NONCE_BYTES)
    return nonce + AESGCM(_master_key(settings)).encrypt(nonce, msisdn.encode("utf-8"), None)


def unseal(settings, *, sealed: bytes) -> str:  # noqa: ANN001
    """Abre el sello. Lanza si el criptograma fue alterado (GCM autentica)."""
    datos = bytes(sealed)
    nonce, cuerpo = datos[:_NONCE_BYTES], datos[_NONCE_BYTES:]
    return AESGCM(_master_key(settings)).decrypt(nonce, cuerpo, None).decode("utf-8")


def disponible(settings) -> bool:  # noqa: ANN001
    """¿Están los dos secretos? Para decidir ANTES de empezar una escritura.

    Existe para que el router pueda contestar 503 limpio en vez de reventar a
    mitad de una transacción que ya escribió media cosa.
    """
    try:
        _pepper(settings)
        _master_key(settings)
    except PrivacyCryptoUnavailable:
        return False
    return True
