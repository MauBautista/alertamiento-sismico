"""[T-7.49] Un sismo es UN episodio, y el episodio tiene UNA identidad.

El gabinete llevaba **dos relojes para lo mismo** y divergían:

* `RuleEngine` caducaba su `event_id` a los 30 s (`dedup_window_s`).
* `EpisodeTracker` exige 90 s de silencio para dar el episodio por terminado.

## ⚠️ El peor caso NO es una calma rara: es el sismo que este producto existe para avisar

La ficha lo planteó como «una calma intermedia de entre 30 y 90 s». Lo es, pero lo
grave es más común: **el sismo lejano avisado por SASMEX**. SASMEX acuña el id en
`t=0`, el suelo sigue quieto mientras la onda viaja —y un `normal` NO extendía la
ventana del motor, porque `_episode_event_id` sólo se llamaba con un tier distinto
de `NORMAL`— y cuando la sacudida llega 50 s después el motor acuñaba un id NUEVO.
Ése es el caso Guerrero→CDMX, o sea la forma normal del aviso útil.

Y con el enclavado real es **certeza, no probabilidad**: `_sasmex_latched` no baja
hasta que el operador re-arma, así que el reloj del silencio del tracker **ni
arranca**, mientras el del motor caduca siempre. Por eso «igualar los dos números»
no era una opción: ningún valor concilia dos relojes cuando uno no arranca nunca.

## Lo que de verdad le pasa al ocupante

No es que «el segundo incidente no se cierre jamás» —la nube cierra por SITIO, no
por `event_id`—. Es peor: `OPEN_INCIDENT` devuelve el incidente abierto **más
reciente** del sitio, y un incidente `local_threshold` sin cuórum se oculta entero
por `T-2.105` (una estación sola no ordena evacuar). Así que el segundo incidente
—el instrumental— **tapa al primero, el de SASMEX**, y el teléfono del ocupante
cae a `idle` mientras el edificio se mueve y la sirena suena.

## El arreglo: el segundo reloj no existe

`RuleEngine` deja de caducar por tiempo. Acuña una vez y **retira sólo cuando se
lo dicen**. Quien se lo dice es el `EpisodeTracker`, que es la única autoridad
sobre cuándo termina un episodio, por dos razones declaradas: **silencio** o
**cota**. La divergencia no se vuelve improbable: deja de ser posible, porque ya
no hay dos cosas que comparar.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from takab_edge.config.settings import EdgeSettings
from takab_edge.contracts import SasmexSignal, Tier, TierDecision
from takab_edge.rules import RuleEngine
from takab_edge.rules.episode import EpisodeTracker
from tests.test_rules import TH, _feature

T0 = datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)
SITIO = "11111111-1111-1111-1111-111111111111"


class _Reloj:
    """Los DOS relojes del gabinete, atados — y separables a propósito.

    ⚠️ [T-7.60] `t` es el de pared (fecha lo que viaja a la nube) y `mono` el
    monotónico (cuenta lo que transcurre aquí). Moverlos juntos con `avanzar()`
    es «pasó el tiempo». Mover sólo `t` es «saltó el reloj», que es lo que hace
    un Pi sin RTC cuando NTP contesta — 13 h 25 min el 2026-09-19 — y NO puede
    dar por terminado un episodio sísmico.
    """

    def __init__(self, t: datetime) -> None:
        self.t = t
        self.mono = 0.0

    def __call__(self) -> datetime:
        return self.t

    def avanzar(self, segundos: float) -> None:
        """Pasa el tiempo: los dos relojes, como en la realidad."""
        self.t = self.t + timedelta(seconds=segundos)
        self.mono += segundos

    def saltar(self, segundos: float) -> None:
        """SÓLO el de pared. El tiempo no ha pasado; el reloj se corrigió."""
        self.t = self.t + timedelta(seconds=segundos)

    def en(self, t: float) -> None:
        """Coloca los dos relojes en el segundo `t` desde el origen."""
        self.t = T0 + timedelta(seconds=t)
        self.mono = t


class _Gabinete:
    """Motor + seguidor cableados COMO LOS CABLEA EL SUPERVISOR.

    No es un doble: son las dos clases reales, unidas por el mismo cable que
    `EdgeSupervisor` usa. Lo que se recoge es lo que cruzaría a la nube.
    """

    def __init__(
        self, tmp_path: Path | None = None, *, quiet_s: float = 90.0, max_s: float = 3600.0
    ):
        self.reloj = _Reloj(T0)
        self.motor = RuleEngine(TH, clock=self.reloj)
        self.seguidor = EpisodeTracker(
            quiet_s,
            site_id=SITIO,
            state_path=(tmp_path / "episodio.json") if tmp_path else None,
            max_s=max_s,
            on_episode_end=self.motor.end_episode,
            now=self.reloj,
            mono=lambda: self.reloj.mono,
        )
        self.eventos: list[tuple[float, str]] = []  # LocalEvent que saldrían
        self.cierres: list[tuple[float, str, str]] = []  # (t, event_id, motivo)

    def _observar(self, decision: TierDecision, latched: bool | None) -> None:
        t = (self.reloj.t - T0).total_seconds()
        transicion = self.seguidor.observe(decision, latched=latched, now=self.reloj.t)
        if decision.tier is not Tier.NORMAL:
            self.eventos.append((t, decision.event_id))
        if transicion is not None and transicion.new_tier is Tier.NORMAL:
            self.cierres.append((t, transicion.event_id, "; ".join(transicion.reasons)))

    def sasmex(self, t: float, *, latched: bool | None = False) -> None:
        self.reloj.en(t)  # [T-7.60] los DOS relojes: t es «el instante t», no «la fecha t»
        self._observar(self.motor.evaluate_sasmex(SasmexSignal(active=True)), latched)

    def sacudida(self, t: float, pga: float = 0.12, *, latched: bool | None = False) -> None:
        self.reloj.en(t)  # [T-7.60] los DOS relojes: t es «el instante t», no «la fecha t»
        cuando = T0 + timedelta(seconds=t)
        decision = self.motor.evaluate_features(_feature(pga=pga, channel="ENZ", when=cuando))
        self._observar(decision, latched)

    def calma(self, t: float, *, latched: bool | None = False) -> None:
        self.reloj.en(t)  # [T-7.60] los DOS relojes: t es «el instante t», no «la fecha t»
        cuando = T0 + timedelta(seconds=t)
        decision = self.motor.evaluate_features(_feature(pga=0.0001, channel="ENZ", when=cuando))
        self._observar(decision, latched)

    @property
    def ids_de_evento(self) -> set[str]:
        return {i for _t, i in self.eventos}


# ───────────────────────────── el sismo insignia: avisado por SASMEX


def test_un_sismo_AVISADO_por_sasmex_no_se_parte_en_DOS(tmp_path: Path) -> None:
    """El caso Guerrero→CDMX: aviso, ~50 s de viaje, y luego la sacudida.

    Antes de esta ficha salían DOS `event_uuid` y por tanto dos incidentes, y el
    segundo —instrumental, sin cuórum— tapaba al primero en el teléfono del
    ocupante. Es el escenario normal del producto, no un caso raro.
    """
    g = _Gabinete(tmp_path)
    g.sasmex(0)  # llega el aviso; el suelo aún está quieto
    for t in (10, 20, 30, 40):  # la onda viaja: nada que medir
        g.calma(t)
    g.sacudida(50)  # llega la onda

    assert len(g.ids_de_evento) == 1, (
        "el mismo sismo se partió en varios eventos: "
        f"{sorted(i[:8] for i in g.ids_de_evento)}. El segundo incidente tapa al "
        "primero en el teléfono del ocupante (OPEN_INCIDENT devuelve el más "
        "reciente, y T-2.105 oculta el instrumental sin cuórum)"
    )


def test_una_calma_intermedia_no_parte_el_episodio(tmp_path: Path) -> None:
    """El caso que la ficha nombraba: 30 s < calma < 90 s."""
    g = _Gabinete(tmp_path)
    g.sacudida(0)
    g.sacudida(40)  # separación P/S a distancia, o una réplica temprana
    assert len(g.ids_de_evento) == 1, f"partido en {len(g.ids_de_evento)} eventos"


def test_el_cierre_llega_al_MISMO_id_que_ABRIO(tmp_path: Path) -> None:
    """Criterio 2 de la ficha."""
    g = _Gabinete(tmp_path)
    g.sacudida(0)
    g.sacudida(40)
    for t in (50, 100, 150, 200):
        g.calma(t)

    assert g.cierres, "el episodio no se cerró nunca"
    ids_cerrados = {i for _t, i, _m in g.cierres}
    assert ids_cerrados == g.ids_de_evento, (
        f"se abrieron {sorted(i[:8] for i in g.ids_de_evento)} y se cerraron "
        f"{sorted(i[:8] for i in ids_cerrados)}: alguno se queda sin cierre"
    )


# ─────────────────────── y lo contrario, que sería peor: fundir dos sismos


def test_DOS_sismos_de_VERDAD_siguen_siendo_dos(tmp_path: Path) -> None:
    """⚠️ La contraprueba imprescindible.

    Un arreglo que diera siempre el mismo id sería mucho peor que el defecto:
    archivaría el sismo de la semana que viene dentro del incidente de hoy. Dos
    sacudidas separadas por MÁS que el silencio del episodio tienen que seguir
    dando dos incidentes.
    """
    g = _Gabinete(tmp_path)
    g.sacudida(0)
    for t in (10, 60, 120, 200):  # silencio suficiente: el episodio cierra
        g.calma(t)
    assert g.cierres, "el primer episodio no cerró; este test no está midiendo lo que dice"
    g.sacudida(400)  # un sismo NUEVO, mucho después

    assert len(g.ids_de_evento) == 2, (
        "dos sismos distintos comparten identidad: el segundo quedaría archivado "
        "dentro del incidente del primero"
    )


# ────────────────────────────────── la cota, que no puede callarse


def test_un_episodio_ATASCADO_se_corta_por_COTA_y_lo_DICE(tmp_path: Path) -> None:
    """Un fallback no puede ser `ok`.

    Con el enclavado puesto —que no baja hasta que el operador re-arma— el reloj
    del silencio no arranca nunca. Sin cota, el motor no jubilaría el id jamás y
    el sismo del mes que viene se archivaría dentro del incidente de hoy. Con
    cota, se corta; pero cortar por cota **no es lo mismo** que cerrar por
    silencio, y el papel de la bitácora tiene que distinguirlo.
    """
    g = _Gabinete(tmp_path, max_s=300.0)
    g.sacudida(0, latched=True)
    primero = next(iter(g.ids_de_evento))
    for t in (100, 200, 250):  # enclavado puesto: el silencio ni empieza
        g.calma(t, latched=True)
    assert not g.cierres, "cerró con el enclavado puesto: eso apaga una crisis viva"

    # La decisión que CRUZA el tope pertenece todavía al episodio viejo: el motor
    # acuña antes de que el seguidor la vea, y adelantar esa mirada exigiría que
    # el camino de actuación preguntase al módulo advisory. Lo que importa es que
    # a partir de ahí la identidad esté jubilada.
    g.sacudida(400, latched=True)
    assert g.cierres, "el episodio se cortó por cota SIN DECIRLO en ninguna transición"
    g.sacudida(410, latched=True)
    assert len(g.ids_de_evento) == 2, "la cota no jubiló el episodio atascado"

    motivos = " ".join(m for _t, _i, m in g.cierres).lower()
    assert "cota" in motivos, (
        f"el cierre por cota no se distingue de uno por silencio: motivos={motivos!r}. "
        "Un operador que lea la bitácora tiene que saber que ese episodio no "
        "terminó porque el suelo se calmara"
    )
    assert primero in {i for _t, i, _m in g.cierres}


def test_un_episodio_PERSISTIDO_demasiado_viejo_no_se_hereda(tmp_path: Path) -> None:
    """El otro camino de divergencia, el que ningún reloj cubría: el reinicio.

    El seguidor restauraba `event_id` de disco y el motor no persiste nada, así
    que tras un corte de luz a mitad de sismo el siguiente disparo acuñaba otro
    id con probabilidad 1. Ahora el motor lo hereda del seguidor — y por eso el
    estado guardado necesita fecha y techo: un `episodio.json` de hace tres días
    reutilizaría un `event_uuid` viejo para un sismo nuevo.
    """
    ruta = tmp_path / "episodio.json"
    g = _Gabinete(tmp_path, max_s=300.0)
    g.sacudida(0, latched=True)
    viejo = next(iter(g.ids_de_evento))
    assert ruta.exists(), "el episodio no se persistió; este test no mide lo que dice"

    # El proceso reinicia MUCHO después (el fichero no tiene por qué ser de hoy).
    resucitado = EpisodeTracker(
        90.0,
        site_id=SITIO,
        state_path=ruta,
        max_s=300.0,
        on_episode_end=lambda: None,
        now=lambda: T0 + timedelta(days=3),
    )
    assert resucitado.event_id is None, (
        f"heredó un episodio de hace tres días ({viejo[:8]}…): el próximo sismo se "
        "archivaría dentro del incidente de aquel día"
    )


# ─────────────────────────────────────────── la carrera, ejercida


def test_el_id_del_episodio_se_acuña_UNA_sola_vez_con_DOS_hilos() -> None:
    """Criterio 3 de la ficha, ejercido y sin `sleep`.

    `_episode_event_id` hacía *check-then-act* sobre `self._event_id` sin lock, y
    entran dos hilos: el de SeedLink (`evaluate_features`) y el callback del dueño
    de los pines (`evaluate_sasmex`). Se arranca a los dos contra una barrera para
    que la intercalación sea real, no teórica.
    """
    motor = RuleEngine(TH, clock=_Reloj(T0))
    barrera = threading.Barrier(2)
    ids: list[str] = []
    cerrojo = threading.Lock()

    def por_umbral() -> None:
        barrera.wait()
        d = motor.evaluate_features(_feature(pga=0.12, channel="ENZ", when=T0))
        with cerrojo:
            ids.append(d.event_id)

    def por_sasmex() -> None:
        barrera.wait()
        d = motor.evaluate_sasmex(SasmexSignal(active=True))
        with cerrojo:
            ids.append(d.event_id)

    for _ in range(200):
        motor.end_episode()
        ids.clear()
        barrera.reset()
        hilos = [threading.Thread(target=por_umbral), threading.Thread(target=por_sasmex)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        assert len(set(ids)) == 1, (
            f"dos hilos acuñaron identidades distintas para el mismo sismo: {ids}. "
            "Es el doble disparo SASMEX+umbral, que es el caso NORMAL de un sismo "
            "avisado"
        )


# ───────────────────────── el censo: que el invariante no se erosione


def test_NADIE_MAS_acuña_la_identidad_de_un_episodio() -> None:
    """Derivado del árbol, no de una lista de exentos.

    La divergencia dejó de ser posible porque hay **un solo sitio** que acuña el
    id de un episodio. Si mañana aparece otro, este censo lo dice antes de que
    vuelva a partir un sismo en dos.
    """
    raiz = Path(__file__).resolve().parents[1] / "takab_edge"
    culpables: list[str] = []
    for ruta in sorted(raiz.rglob("*.py")):
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
            if "new_event_id()" not in linea or linea.lstrip().startswith("#"):
                continue
            culpables.append(f"{ruta.relative_to(raiz)}:{n}  {linea.strip()}")

    #: Quién PUEDE acuñar un id, y por qué. No es una lista de exentos que crece:
    #: son los cuatro sitios que acuñan identidades DISTINTAS de la del episodio.
    permitidos = {
        "rules/__init__.py",  # el dueño de la identidad del episodio
        "contracts.py",  # el generador en sí
        "pinlink/server.py",  # el id de una sesión de pines, que no es un sismo
        "audit/__init__.py",  # el id de un registro de auditoría
    }
    fuera = [c for c in culpables if c.split(":")[0] not in permitidos]
    assert not fuera, (
        "hay sitios nuevos que acuñan un id de evento fuera del dueño de la "
        f"identidad del episodio: {fuera}"
    )


def test_el_motor_YA_NO_tiene_un_reloj_de_identidad() -> None:
    """La razón por la que la divergencia es IMPOSIBLE y no sólo improbable.

    No hay dos números que alguien pueda configurar en desacuerdo: el motor no
    tiene ninguno. Si vuelve a aparecer una caducidad por tiempo en el motor, la
    ficha hay que releerla entera.
    """
    import inspect

    # ⚠️ Se mira la FIRMA y los ATRIBUTOS, no el texto del fichero: un barrido de
    # cadenas sobre el fuente se pone rojo por un COMENTARIO que explique el
    # defecto, que es justo lo que hay que poder escribir. Misma trampa que la de
    # los documentos SSM en T-7.47.
    parametros = inspect.signature(RuleEngine.__init__).parameters
    assert "dedup_window_s" not in parametros, (
        "volvió la ventana de dedup del motor. Era el segundo reloj: con el "
        "enclavado puesto el del seguidor no arranca nunca y éste caduca siempre, "
        "así que NINGÚN valor los concilia"
    )
    motor = RuleEngine(TH)
    assert not hasattr(motor, "_episode_end"), "el motor volvió a tener caducidad propia"
    assert not hasattr(motor, "dedup_window_s")


def test_los_ajustes_DECLARAN_la_cota_del_episodio() -> None:
    """Y con un valor que no puede ser menor que el silencio que cierra."""
    s = EdgeSettings(dev_mode=True)
    assert s.episode_max_s > s.episode_quiet_s, (
        "la cota del episodio no puede ser menor que el silencio que lo cierra: "
        "cortaría por cota episodios perfectamente sanos"
    )


# ═══════════════ [T-7.60] el salto de reloj, que NO es el paso del tiempo


def test_un_SALTO_de_reloj_NO_cierra_un_episodio_sismico() -> None:
    """La prueba que acredita `T-7.60`, y la que mide lo que de verdad pasó.

    ⚠️ EL ESCENARIO ES REAL, no un caso de laboratorio. El Raspberry Pi 4 **no
    tiene RTC** (`timedatectl` responde `RTC time: n/a`): al arrancar restaura la
    última hora guardada y sigue con ella hasta que NTP contesta. El 2026-09-19,
    en el gabinete de Puebla, ese salto fue de **13 h 25 min hacia adelante, en
    un instante**.

    Con el silencio contado en reloj de pared, ese salto lo satisfacía de golpe:
    el gabinete daba la sacudida por terminada y sacaba al ocupante de «EVACÚE»
    mientras el suelo seguía moviéndose. Es la inversión exacta de lo que cerró
    `T-7.30`.

    Aquí el suelo NO se ha calmado ni un segundo —el monotónico no avanza— y el
    reloj de pared se va trece horas. El episodio tiene que seguir abierto.
    """
    g = _Gabinete(quiet_s=90.0)
    g.sasmex(0.0, latched=True)
    assert g.eventos, "el episodio no llegó a abrirse; este test no mide nada"
    abierto = g.eventos[-1][1]

    # El reloj salta trece horas y media. El tiempo NO ha pasado.
    g.reloj.saltar(13 * 3600 + 25 * 60)
    g._observar(g.motor.evaluate_sasmex(SasmexSignal(active=True)), True)  # noqa: SLF001

    assert not g.cierres, (
        "un SALTO de reloj cerró el episodio. Con el suelo moviéndose, eso saca "
        f"al ocupante de «EVACÚE» por un ajuste de NTP. Cierres: {g.cierres}"
    )
    assert g.eventos[-1][1] == abierto, "y sigue siendo el MISMO episodio"


def test_el_salto_de_reloj_tampoco_lo_corta_POR_COTA() -> None:
    """La otra mitad, y se escapa aunque se arregle el silencio.

    La cota dura (`max_s`) también restaba dos marcas de pared. Un salto mayor
    que la cota cortaba el episodio «por cota» —diciéndolo, eso sí— sobre un
    sismo de hace un minuto.
    """
    g = _Gabinete(quiet_s=90.0, max_s=3600.0)
    g.sasmex(0.0, latched=True)
    assert g.eventos

    g.reloj.saltar(13 * 3600 + 25 * 60)  # muy por encima de la cota de 1 h
    g._observar(g.motor.evaluate_sasmex(SasmexSignal(active=True)), True)  # noqa: SLF001

    assert not g.cierres, (
        f"el salto de reloj cortó por COTA un episodio recién abierto: {g.cierres}"
    )


def test_pero_el_tiempo_que_SI_pasa_lo_cierra_igual() -> None:
    """La contraprueba: que las dos de arriba no pasen por estar rotas.

    Si el episodio no cerrara NUNCA, aquéllas serían verdes por la peor razón
    posible. Aquí el tiempo transcurre de verdad —los dos relojes— y el episodio
    tiene que cerrar por silencio, como siempre.
    """
    g = _Gabinete(quiet_s=90.0)
    g.sasmex(0.0, latched=True)
    g.calma(10.0, latched=False)
    g.calma(10.0 + 91.0, latched=False)

    assert g.cierres, "el episodio no cerró con el silencio cumplido"
    assert "cota" not in g.cierres[-1][2].lower(), "cerró por cota, no por silencio"
