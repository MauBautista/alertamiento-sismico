"""[T-7.30] El EPISODIO de alerta: subir es inmediato, bajar exige silencio.

POR QUÉ EXISTE, medido con el WR-1 real el 2026-09-12: tras el pulso, el teléfono
se quedó en la pantalla de crisis contando y hubo que concluir la sacudida a mano
por SQL. El gabinete no publica nada cuando el nivel vuelve a `normal`
(`supervisor.py`: ``if decision.tier is Tier.NORMAL: return``) y en la nube nadie
escribe ``rule_evaluations``, que es de donde la app deriva ``shaking_concluded``.
Un sismo real no podía producir esa fase jamás.

PERO EL ARREGLO INGENUO ES PEOR QUE EL DEFECTO. ``evaluate_sasmex`` deja el motor
en ``evacuate_or_hold``; ``evaluate_features`` corre cada segundo y ``decide()``
no sabe nada del SASMEX, así que con el suelo quieto devuelve ``NORMAL``.
Publicar esa transición cruda le diría a la nube que la sacudida terminó **un
segundo después de la alerta, antes de que llegue la onda S**, y sacaría al
ocupante de la pantalla que le dice que evacúe.

De ahí la asimetría, que es todo el módulo:

    escalar  → se publica AL INSTANTE (es la mitad que protege)
    volver a normal → solo tras `quiet_s` de silencio CONTINUO

y tres cautelas que no son adorno:

* **Con el enclavado puesto el reloj no corre.** Mientras el gabinete siga
  enclavado, la crisis sigue viva por definición.
* **Sin poder leer el enclavado (``latched is None``) tampoco corre.** Falla
  CERRADO, al revés que el fail-open deliberado del modo prueba del WR-1, y por
  su propia razón: allí callar pierde un sismo real; aquí cerrar de más apaga una
  crisis que no ha terminado.
* **El episodio se persiste.** La forma más probable de que un sismo real termine
  es cortando la luz; un episodio que solo vive en RAM deja el cierre sin emisor y
  el teléfono en crisis para siempre — el mismo defecto con otra cara.

NO vive dentro de ``RuleEngine`` a propósito: ese módulo es el camino
umbral→actuador (regla de oro 1). Esto es advisory y su fallo jamás puede
propagar a la actuación; quien lo llama lo envuelve en ``try/except``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from takab_edge.contracts import AlertSource, Tier, TierDecision, TierTransition, new_event_id

log = logging.getLogger(__name__)

#: Orden de gravedad. `manual_only` NO entra: es degradación de sensores, no
#: sacudida, y tratarla como escalada abriría episodios sin sismo.
_ORDEN = (Tier.NORMAL, Tier.WATCH, Tier.RESTRICTED, Tier.EVACUATE_OR_HOLD)


def _rango(tier: Tier) -> int:
    return _ORDEN.index(tier) if tier in _ORDEN else -1


class EpisodeTracker:
    """Sigue el episodio de alerta y decide qué transiciones cruzan a la nube.

    Sin I/O de red y con reloj inyectado: se prueba entero sin gabinete. El único
    I/O es el fichero de estado, y su fallo nunca impide detectar.
    """

    def __init__(
        self, quiet_s: float, *, site_id: str, state_path: Path | str | None = None
    ) -> None:
        self.quiet_s = float(quiet_s)
        self.site_id = site_id
        self._state_path = Path(state_path) if state_path else None
        self._tier: Tier = Tier.NORMAL
        self._event_id: str | None = None
        self._quiet_since: datetime | None = None
        self._restaurar()

    # --- lo que ve el supervisor ------------------------------------------

    def observe(
        self, decision: TierDecision, *, latched: bool | None, now: datetime
    ) -> TierTransition | None:
        """Devuelve la transición A PUBLICAR, o ``None`` si no hay nada que decir.

        `latched` es el enclavado del gabinete: ``None`` significa que no se pudo
        leer, y entonces no se cierra nada.
        """
        tier = decision.tier
        if _rango(tier) > _rango(self._tier):
            return self._abrir_o_escalar(decision, now)
        if tier is not Tier.NORMAL or self._event_id is None:
            # Bajada dentro del episodio, o normal sin episodio abierto: el
            # episodio sigue (o no hay ninguno) y no hay nada que publicar.
            if tier is not Tier.NORMAL:
                self._quiet_since = None
            return None
        return self._quizas_cerrar(decision, latched=latched, now=now)

    # --- interior -----------------------------------------------------------

    def _abrir_o_escalar(self, decision: TierDecision, now: datetime) -> TierTransition:
        previo = self._tier
        if self._event_id is None:
            # Episodio nuevo: su id es el de ESTA decisión, el mismo que viaja en
            # el `LocalEvent` y acaba siendo `incidents.event_uuid`.
            self._event_id = decision.event_id
        self._tier = decision.tier
        self._quiet_since = None
        self._guardar()
        return self._transicion(decision, previo, decision.tier, now)

    def _quizas_cerrar(
        self, decision: TierDecision, *, latched: bool | None, now: datetime
    ) -> TierTransition | None:
        if latched is not False:
            # Enclavado puesto, o ilegible: el reloj del silencio ni empieza.
            self._quiet_since = None
            return None
        if self._quiet_since is None:
            self._quiet_since = now
            return None
        if (now - self._quiet_since).total_seconds() < self.quiet_s:
            return None
        previo, event_id = self._tier, self._event_id
        self._tier = Tier.NORMAL
        self._event_id = None
        self._quiet_since = None
        self._guardar()
        cierre = self._transicion(decision, previo, Tier.NORMAL, now)
        return cierre.model_copy(update={"event_id": event_id})

    def _transicion(
        self, decision: TierDecision, previo: Tier, nuevo: Tier, now: datetime
    ) -> TierTransition:
        return TierTransition(
            event_id=self._event_id or decision.event_id or new_event_id(),
            site_id=self.site_id,
            prev_tier=previo,
            new_tier=nuevo,
            source=decision.source,
            at=now,
            # La severidad solo es una MEDICIÓN si vino del umbral: el 1.0 con el
            # que se emite SASMEX es un booleano disfrazado de número.
            pga_g=decision.severity if decision.source is AlertSource.THRESHOLD else None,
            reasons=list(decision.reasons),
        )

    # --- estado que sobrevive al corte de luz --------------------------------

    def _guardar(self) -> None:
        if self._state_path is None:
            return
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            if self._event_id is None:
                self._state_path.unlink(missing_ok=True)
                return
            tmp = self._state_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps({"tier": self._tier.value, "event_id": self._event_id}),
                encoding="utf-8",
            )
            tmp.replace(self._state_path)  # rename atómico: nunca a medio escribir
        except OSError:
            # Un disco lleno no puede impedir detectar. Se pierde la continuidad
            # del episodio entre reinicios, que es exactamente el riesgo que este
            # fichero existe para reducir — pero no se rompe el gabinete.
            log.exception("no se pudo persistir el episodio (sigue en memoria)")

    def _restaurar(self) -> None:
        if self._state_path is None or not self._state_path.exists():
            return
        try:
            d = json.loads(self._state_path.read_text(encoding="utf-8"))
            self._tier = Tier(d["tier"])
            self._event_id = str(d["event_id"])
        except (OSError, ValueError, KeyError):
            # Corte a mitad de escritura, o fichero de otra versión. Se empieza de
            # cero: peor es no arrancar.
            log.exception("estado de episodio ilegible; se empieza sin episodio")
            self._tier, self._event_id = Tier.NORMAL, None
