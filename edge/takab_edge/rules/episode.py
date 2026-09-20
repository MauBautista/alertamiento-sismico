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
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from takab_edge.contracts import AlertSource, Tier, TierDecision, TierTransition
from takab_edge.durable import escribir_durable
from takab_edge.reloj import mono as _mono


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
        self,
        quiet_s: float,
        *,
        site_id: str,
        state_path: Path | str | None = None,
        max_s: float = 3600.0,
        on_episode_end: Callable[[], None] | None = None,
        now: Callable[[], datetime] | None = None,
        mono: Callable[[], float] | None = None,
    ) -> None:
        self.quiet_s = float(quiet_s)
        #: [T-7.49] Cota DURA de duración de un episodio. No es un segundo reloj
        #: de identidad —el motor ya no tiene ninguno—: es el suelo bajo el
        #: silencio. Con el enclavado SASMEX puesto el reloj de `quiet_s` **ni
        #: arranca** (no baja hasta que el operador re-arma), así que sin cota un
        #: episodio atascado archivaría el sismo del mes que viene dentro del
        #: incidente de hoy. Cortar por cota **no es** cerrar por silencio, y por
        #: eso la transición lo DICE: un fallback no puede ser `ok`.
        self.max_s = float(max_s)
        self.site_id = site_id
        self._state_path = Path(state_path) if state_path else None
        self._now = now or _utcnow
        #: [T-7.60] El SEGUNDO reloj, y son dos porque miden cosas distintas:
        #: `_now` fecha lo que viaja a la nube (una fecha se imprime y se compara
        #: con fechas ajenas), `_mono` cuenta lo que transcurre aquí. Inyectable
        #: por la misma razón que el otro: una prueba que quiera adelantar el
        #: silencio no debería tener que parchear `time` entero.
        self._mono = mono or _mono
        #: [T-7.49] El seguidor es la única autoridad sobre el final del episodio,
        #: así que es él quien jubila la identidad en el motor. El cable va en
        #: esta dirección —advisory → crítico— y no al revés: que el motor
        #: preguntase aquí metería I/O de disco y una excepción posible en el hilo
        #: que decide la actuación.
        self._on_episode_end = on_episode_end
        self._tier: Tier = Tier.NORMAL
        self._event_id: str | None = None
        self._opened_at: datetime | None = None
        # ⚠️ [T-7.60] MONOTÓNICO, y de todos los relojes del gabinete éste es
        # el que más importa: cuenta el silencio que declara TERMINADO un
        # episodio. Con reloj de pared, el salto de NTP del arranque —13 h 25
        # min el 2026-09-19, y el Pi no tiene RTC— lo satisface DE GOLPE: el
        # gabinete da la sacudida por acabada y saca al ocupante de «EVACÚE».
        # Es la inversión exacta de lo que cerró `T-7.30`, que existe porque el
        # arreglo ingenuo hacía justo esto antes de la onda S.
        self._quiet_since: float | None = None
        #: [T-7.60] El instante monotónico en que se abrió el episodio, al lado
        #: del `_opened_at` de pared. Son dos porque sirven para cosas distintas:
        #: aquél FECHA el episodio para la nube, éste lo CRONOMETRA aquí. `None`
        #: cuando el episodio se restauró del disco: entonces no hay origen
        #: monotónico compartido con el proceso que lo abrió.
        self._abierto_mono: float | None = None
        # Mismo read-modify-write y mismos dos hilos que en el motor, y aquí
        # además se escribe a disco: sin lock se pueden emitir dos cierres o
        # dejar `episodio.json` a medias.
        self._lock = threading.RLock()
        self._restaurar()

    @property
    def event_id(self) -> str | None:
        """La identidad del episodio en curso, para que el motor la herede al arrancar."""
        with self._lock:
            return self._event_id

    # --- lo que ve el supervisor ------------------------------------------

    def observe(
        self, decision: TierDecision, *, latched: bool | None, now: datetime
    ) -> TierTransition | None:
        """Devuelve la transición A PUBLICAR, o ``None`` si no hay nada que decir.

        `latched` es el enclavado del gabinete: ``None`` significa que no se pudo
        leer, y entonces no se cierra nada.
        """
        with self._lock:
            return self._observe(decision, latched=latched, now=now)

    def _observe(
        self, decision: TierDecision, *, latched: bool | None, now: datetime
    ) -> TierTransition | None:
        # [T-7.49] La cota, ANTES de nada: un episodio atascado tiene que jubilar
        # su identidad aunque la decisión que entra sea una escalada.
        por_cota = self._cerrar_por_cota(decision, now)
        if por_cota is not None:
            return por_cota
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
            # [T-7.49] Y cuándo abrió, que es lo que la cota necesita y lo que
            # permite descartar un `episodio.json` rancio tras un reinicio.
            self._opened_at = now
            self._abierto_mono = self._mono()  # [T-7.60] el cronómetro, al lado de la fecha
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
            self._quiet_since = self._mono()
            return None
        # reloj: monotonico — el silencio transcurre en ESTA máquina
        if self._mono() - self._quiet_since < self.quiet_s:
            return None
        return self._cerrar(decision, now, event_id=self._event_id, reasons=None)

    def _cerrar(
        self,
        decision: TierDecision,
        now: datetime,
        *,
        event_id: str | None,
        reasons: list[str] | None,
    ) -> TierTransition:
        """El ÚNICO sitio que termina un episodio, por silencio o por cota.

        [T-7.49] Y el único que jubila la identidad en el motor: desde esta ficha
        el motor no caduca por su cuenta, así que si esto no se llamara el id
        viviría para siempre.
        """
        previo = self._tier
        self._tier = Tier.NORMAL
        self._event_id = None
        self._opened_at = None
        self._abierto_mono = None
        self._quiet_since = None
        self._guardar()
        self._jubilar_identidad()
        cierre = self._transicion(decision, previo, Tier.NORMAL, now)
        actualizado: dict = {"event_id": event_id}
        if reasons is not None:
            actualizado["reasons"] = reasons
        return cierre.model_copy(update=actualizado)

    def _cerrar_por_cota(self, decision: TierDecision, now: datetime) -> TierTransition | None:
        """Corta un episodio que lleva demasiado abierto — y lo DICE.

        No es un cierre sano y no puede parecerlo: el suelo no se calmó, se acabó
        el plazo. Un operador que lea la bitácora tiene que poder distinguirlos.
        """
        if self._event_id is None or self._opened_at is None:
            return None
        # [T-7.60] Monotónica cuando el episodio se abrió en esta vida del
        # proceso; sólo cae en la pared cuando viene del disco y no hay origen
        # monotónico que compartir con el proceso anterior. El salto de reloj
        # cerraba por cota un episodio de un minuto.
        if self._abierto_mono is not None:
            # reloj: monotonico — el episodio se abrió aquí y sigue abierto aquí
            edad = self._mono() - self._abierto_mono
        else:
            # reloj: heredado — viene del disco; la pared es lo único que hay
            edad = (now - self._opened_at).total_seconds()
        if edad <= self.max_s:
            return None
        log.warning(
            "episodio %s cerrado POR COTA (%.0f s abierto, tope %.0f s), no por silencio",
            self._event_id,
            edad,
            self.max_s,
        )
        return self._cerrar(
            decision,
            now,
            event_id=self._event_id,
            reasons=[
                f"cerrado por COTA de duración ({edad:.0f} s abierto, tope {self.max_s:.0f} s): "
                "el suelo no se calmó — revisar el enclavado del gabinete"
            ],
        )

    def _jubilar_identidad(self) -> None:
        if self._on_episode_end is None:
            return
        try:
            self._on_episode_end()
        except Exception:  # noqa: BLE001 — advisory: jamás al camino de actuación
            log.exception("no se pudo jubilar la identidad del episodio en el motor")

    def _transicion(
        self, decision: TierDecision, previo: Tier, nuevo: Tier, now: datetime
    ) -> TierTransition:
        return TierTransition(
            # ⚠️ [T-7.49] Aquí había un respaldo TRIPLE que acababa en
            # `new_event_id()`. Un fallback no puede INVENTAR la identidad de un
            # hecho de compliance: si ninguna de las dos existiera, un id nuevo
            # ataría esta transición a un incidente que no existe, y eso es peor
            # que no emitirla. Las dos ramas que quedan son alcanzables y ciertas:
            # el episodio en curso, o la decisión que lo abre.
            event_id=self._event_id or decision.event_id,
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
            if self._event_id is None:
                self._state_path.unlink(missing_ok=True)
                return
            # ⚠️ [T-7.59] `escribir_durable` y no `write_text` + `replace`. El rename
            # es atómico —nadie lee un fichero a medias— pero eso NO es lo que este
            # fichero necesita: necesita sobrevivir a que le quiten la corriente al
            # Pi, y sin `fsync` el rename puede confirmarse antes que los datos.
            # Medido el 2026-09-19 en el gabinete real: volvió con CERO BYTES
            # (`JSONDecodeError: Expecting value: line 1 column 1 (char 0)`).
            escribir_durable(
                self._state_path,
                json.dumps(
                    {
                        "tier": self._tier.value,
                        "event_id": self._event_id,
                        # [T-7.49] Sin fecha, un `episodio.json` de hace tres días
                        # se heredaba como si fuera de hace un minuto y el próximo
                        # sismo se archivaba dentro de aquel incidente.
                        "opened_at": self._opened_at.isoformat() if self._opened_at else None,
                    }
                ),
            )
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
            crudo = d.get("opened_at")
            self._opened_at = datetime.fromisoformat(crudo) if crudo else None
            # [T-7.60] Y NO se inventa un origen monotónico: el del proceso que
            # abrió este episodio murió con él. `None` hace que la cota caiga a
            # la pared, declarado arriba, en vez de fingir un cronómetro.
            self._abierto_mono = None
            # [T-7.49] Un episodio sin fecha es de una versión anterior a esta
            # ficha: no se sabe cuándo abrió, y lo que no se sabe se DECLARA en
            # vez de suponerse fresco.
            if self._opened_at is None:
                log.warning(
                    "el episodio %s viene sin fecha de apertura (estado de una versión "
                    "anterior): se descarta en vez de heredarlo a ciegas",
                    self._event_id,
                )
                self._tier, self._event_id = Tier.NORMAL, None
            # reloj: heredado — el episodio viene del disco y su origen monotónico
            # murió con el proceso anterior. Aquí la pared es lo único que hay, y
            # por eso este camino DESCARTA en vez de heredar: ver el bloque de
            # abajo. Un episodio mal fechado que se hereda archiva el próximo
            # sismo dentro del incidente de hoy.
            # reloj: heredado — el episodio viene del disco; por eso se DESCARTA
            elif (self._now() - self._opened_at).total_seconds() > self.max_s:
                log.warning(
                    "el episodio %s abrió hace %.0f s (tope %.0f): se descarta. Heredarlo "
                    "archivaría el próximo sismo dentro de aquel incidente",
                    # reloj: heredado — la misma edad, para decirlo en el registro
                    self._event_id,
                    (self._now() - self._opened_at).total_seconds(),
                    self.max_s,
                )
                self._tier, self._event_id, self._opened_at = Tier.NORMAL, None, None
                self._abierto_mono = None
        except (OSError, ValueError, KeyError):
            # Corte a mitad de escritura, o fichero de otra versión. Se empieza de
            # cero: peor es no arrancar.
            log.exception("estado de episodio ilegible; se empieza sin episodio")
            self._tier, self._event_id, self._opened_at = Tier.NORMAL, None, None
