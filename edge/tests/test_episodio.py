"""[T-7.30] El episodio de alerta: lo único que puede decirle a la nube que terminó.

EL DEFECTO, medido con el WR-1 real el 2026-09-12: tras el pulso, el teléfono se
quedó en la pantalla de crisis **contando**, y hubo que concluir la sacudida a
mano por SQL. La causa es una línea del supervisor —`if decision.tier is
Tier.NORMAL: return`— sumada a que en la nube **nadie escribe `rule_evaluations`**,
que es justo de donde la app deriva `shaking_concluded`. Un sismo real no podía
producir esa fase jamás.

Y EL ARREGLO INGENUO ES PEOR QUE EL DEFECTO. `evaluate_sasmex` deja el motor en
`evacuate_or_hold`, pero `evaluate_features` corre CADA SEGUNDO y `decide()` no
sabe nada del SASMEX: con el suelo quieto devuelve `NORMAL`. Publicar la
transición cruda le diría a la nube que la sacudida terminó **un segundo después
de la alerta, antes de que llegue la onda S** — y sacaría al ocupante de la
pantalla que le dice que evacúe. Por eso esto no es un detector de flancos:

    subir es INMEDIATO · bajar exige silencio SOSTENIDO

Las tres propiedades que lo hacen seguro, y que son estos tests:

1. **El temporizador no corre con el enclavado puesto.** Mientras la alerta siga
   enclavada en el gabinete, no hay cierre que valga.
2. **Falla CERRADO si no se puede leer el enclavado.** Es la dirección contraria
   al fail-open deliberado del modo prueba, y por su propia razón: allí callar
   pierde un sismo; aquí cerrar de más levanta una crisis que sigue viva.
3. **Sobrevive a un reinicio**, porque la forma más probable de que un sismo real
   termine es cortando la luz. Un episodio que solo vive en RAM deja el cierre
   sin emisor y el teléfono en crisis para siempre: el mismo defecto con otra
   cara.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from takab_edge.contracts import AlertSource, Tier, TierDecision
from takab_edge.rules.episode import EpisodeTracker

T0 = datetime(2026, 9, 13, 3, 28, 3, tzinfo=UTC)
QUIET = 30.0


def _d(tier: Tier, source: AlertSource = AlertSource.THRESHOLD) -> TierDecision:
    return TierDecision(tier=tier, source=source, reasons=["prueba"])


SITIO = "site-dev"


class _TrackerDePrueba(EpisodeTracker):
    """El seguidor con los DOS relojes atados al `now` que pasa cada test.

    ⚠️ [T-7.60] Desde que el silencio se cuenta con reloj monotónico, adelantar
    sólo el de pared ya no adelanta nada — y eso es el arreglo, no un estorbo:
    un salto de NTP **no** puede dar por terminado un episodio sísmico.

    Pero estos 36 casos usan `now=T0 + Ns` para decir «pasaron N segundos», que
    es una forma legítima de escribirlo y se lee bien. Así que el rig ata los dos
    relojes: el `now` que recibe `observe()` mueve también el monotónico, y los
    casos siguen midiendo lo que dicen medir.

    Lo que NO puede hacer este rig es esconder la diferencia, y por eso existe
    `test_un_SALTO_de_reloj_no_cierra_un_episodio`: allí el reloj de pared salta
    trece horas y el monotónico **no se mueve**, que es lo que de verdad pasó en
    el gabinete el 2026-09-19.
    """

    def __init__(self, *args, **kw) -> None:
        self._mono_box = [0.0]
        kw.setdefault("mono", lambda: self._mono_box[0])
        super().__init__(*args, **kw)

    def observe(self, decision, *, latched, now):  # noqa: ANN001, ANN201
        self._mono_box[0] = (now - T0).total_seconds()
        return super().observe(decision, latched=latched, now=now)


def _tracker(**kw) -> EpisodeTracker:
    # ⚠️ [T-7.49] El reloj va INYECTADO y anclado en `T0`. Desde que el episodio
    # persistido lleva `opened_at` y tiene cota de edad, un seguidor que restaure
    # con el reloj de pared vería un episodio abierto en 2026 «hace años» y lo
    # descartaría — correctamente, pero midiendo otra cosa que la que esta suite
    # dice medir. Es la misma razón por la que `observe()` recibe `now`.
    kw.setdefault("now", lambda: T0)
    return _TrackerDePrueba(quiet_s=QUIET, site_id=SITIO, **kw)


# --------------------------------------------------------------------- abrir


def test_la_escalada_se_publica_AL_INSTANTE() -> None:
    """Subir no espera: es la mitad que protege."""
    t = _tracker()
    tr = t.observe(_d(Tier.EVACUATE_OR_HOLD, AlertSource.SASMEX), latched=True, now=T0)
    assert tr is not None
    assert tr.prev_tier is Tier.NORMAL and tr.new_tier is Tier.EVACUATE_OR_HOLD
    assert tr.source is AlertSource.SASMEX


def test_dentro_del_episodio_una_BAJADA_no_publica_nada() -> None:
    """`evacuate_or_hold → watch` no es el fin de nada: el episodio sigue."""
    t = _tracker()
    t.observe(_d(Tier.EVACUATE_OR_HOLD), latched=True, now=T0)
    assert t.observe(_d(Tier.WATCH), latched=True, now=T0 + timedelta(seconds=2)) is None


def test_una_escalada_MAYOR_dentro_del_episodio_sí_publica() -> None:
    t = _tracker()
    t.observe(_d(Tier.WATCH), latched=False, now=T0)
    tr = t.observe(_d(Tier.EVACUATE_OR_HOLD), latched=True, now=T0 + timedelta(seconds=3))
    assert tr is not None and tr.new_tier is Tier.EVACUATE_OR_HOLD
    assert tr.prev_tier is Tier.WATCH


# --------------------------------------------------------------------- cerrar


def test_el_NORMAL_de_un_segundo_despues_del_SASMEX_no_cierra_nada() -> None:
    """EL TEST QUE JUSTIFICA LA FICHA.

    Es exactamente la secuencia real: pulso del WR-1 y, un segundo después, una
    feature tranquila que `decide()` clasifica como NORMAL. Si esto publicara un
    cierre, el ocupante saldría de «EVACÚE AHORA» antes de que llegue la onda.
    """
    t = _tracker()
    t.observe(_d(Tier.EVACUATE_OR_HOLD, AlertSource.SASMEX), latched=True, now=T0)
    assert t.observe(_d(Tier.NORMAL), latched=True, now=T0 + timedelta(seconds=1)) is None


def test_el_silencio_SOSTENIDO_cierra_el_episodio() -> None:
    t = _tracker()
    abre = t.observe(_d(Tier.EVACUATE_OR_HOLD, AlertSource.SASMEX), latched=True, now=T0)
    # El operador suelta el enclavado y el suelo sigue quieto.
    t.observe(_d(Tier.NORMAL), latched=False, now=T0 + timedelta(seconds=10))
    cierra = t.observe(_d(Tier.NORMAL), latched=False, now=T0 + timedelta(seconds=10 + QUIET))
    assert cierra is not None
    assert cierra.new_tier is Tier.NORMAL and cierra.prev_tier is Tier.EVACUATE_OR_HOLD
    # El cierre lleva el id del EPISODIO, no el de la decisión NORMAL (que el
    # motor regenera en cada evaluación): así la nube casa las dos filas.
    assert cierra.event_id == abre.event_id


def test_con_el_enclavado_PUESTO_el_reloj_del_silencio_no_corre() -> None:
    """Mientras el gabinete siga enclavado, no hay cierre: la crisis sigue viva."""
    t = _tracker()
    t.observe(_d(Tier.EVACUATE_OR_HOLD, AlertSource.SASMEX), latched=True, now=T0)
    for s in range(1, int(QUIET) * 3, 5):
        assert t.observe(_d(Tier.NORMAL), latched=True, now=T0 + timedelta(seconds=s)) is None


def test_sin_poder_leer_el_enclavado_falla_CERRADO() -> None:
    """`latched=None` = no se pudo leer. Se prefiere no cerrar.

    Es la dirección contraria al fail-open del modo prueba, y por su razón: allí
    callar pierde un sismo real; aquí cerrar de más apaga una crisis que sigue.
    """
    t = _tracker()
    t.observe(_d(Tier.EVACUATE_OR_HOLD, AlertSource.SASMEX), latched=True, now=T0)
    for s in range(1, int(QUIET) * 3, 5):
        assert t.observe(_d(Tier.NORMAL), latched=None, now=T0 + timedelta(seconds=s)) is None


def test_un_repunte_REARMA_el_silencio() -> None:
    """Si vuelve a moverse, el reloj empieza de cero. No se cierra por acumulación."""
    t = _tracker()
    t.observe(_d(Tier.WATCH), latched=False, now=T0)
    t.observe(_d(Tier.NORMAL), latched=False, now=T0 + timedelta(seconds=5))
    t.observe(_d(Tier.WATCH), latched=False, now=T0 + timedelta(seconds=20))
    # El silencio vuelve a contarse desde el primer `normal` POSTERIOR al repunte
    # (T0+25), no desde el repunte ni desde el silencio anterior.
    assert t.observe(_d(Tier.NORMAL), latched=False, now=T0 + timedelta(seconds=25)) is None
    assert (
        t.observe(_d(Tier.NORMAL), latched=False, now=T0 + timedelta(seconds=25 + QUIET - 1))
        is None
    ), "cerró antes de completar el silencio: el repunte no rearmó el reloj"
    assert (
        t.observe(_d(Tier.NORMAL), latched=False, now=T0 + timedelta(seconds=25 + QUIET))
        is not None
    )


def test_sin_episodio_abierto_el_NORMAL_no_publica_nada() -> None:
    """El 99,9 % del tiempo. Publicar aquí sería logging por intervalo (regla 10)."""
    t = _tracker()
    for s in range(0, 200, 10):
        assert t.observe(_d(Tier.NORMAL), latched=False, now=T0 + timedelta(seconds=s)) is None


def test_el_episodio_SIGUIENTE_es_otro_episodio() -> None:
    t = _tracker()
    a = t.observe(_d(Tier.EVACUATE_OR_HOLD), latched=False, now=T0)
    t.observe(_d(Tier.NORMAL), latched=False, now=T0 + timedelta(seconds=1))
    t.observe(_d(Tier.NORMAL), latched=False, now=T0 + timedelta(seconds=1 + QUIET))
    b = t.observe(_d(Tier.WATCH), latched=False, now=T0 + timedelta(seconds=500))
    assert b is not None and b.event_id != a.event_id
    assert b.prev_tier is Tier.NORMAL


# ------------------------------------------------------------------ reinicio


def test_el_episodio_SOBREVIVE_a_un_reinicio(tmp_path) -> None:
    """La forma más probable de que un sismo real termine es cortando la luz.

    Con el estado solo en RAM, el proceso que vuelve no sabe que hay un episodio
    abierto, nunca emite el cierre y el teléfono se queda en crisis para siempre
    — el mismo defecto que esta ficha arregla, con otra cara.
    """
    estado = tmp_path / "episodio.json"
    t = _tracker(state_path=estado)
    abre = t.observe(_d(Tier.EVACUATE_OR_HOLD, AlertSource.SASMEX), latched=True, now=T0)
    assert estado.exists(), "el episodio abierto no se persistió"

    # El Pi se va y vuelve: proceso nuevo, misma ruta de estado.
    otro = _tracker(state_path=estado)
    t2 = T0 + timedelta(seconds=120)
    assert otro.observe(_d(Tier.NORMAL), latched=False, now=t2) is None  # arranca el silencio
    cierra = otro.observe(_d(Tier.NORMAL), latched=False, now=t2 + timedelta(seconds=QUIET))
    assert cierra is not None, "tras reiniciar, el episodio abierto no se cerró nunca"
    assert cierra.event_id == abre.event_id
    assert cierra.prev_tier is Tier.EVACUATE_OR_HOLD


def test_al_cerrar_se_OLVIDA_el_episodio(tmp_path) -> None:
    """Si el estado sobreviviera al cierre, el reinicio siguiente reabriría un
    episodio que ya terminó."""
    estado = tmp_path / "episodio.json"
    t = _tracker(state_path=estado)
    t.observe(_d(Tier.WATCH), latched=False, now=T0)
    t.observe(_d(Tier.NORMAL), latched=False, now=T0 + timedelta(seconds=1))
    t.observe(_d(Tier.NORMAL), latched=False, now=T0 + timedelta(seconds=1 + QUIET))
    assert (
        _tracker(state_path=estado).observe(
            _d(Tier.NORMAL), latched=False, now=T0 + timedelta(seconds=900)
        )
        is None
    )


def test_un_estado_ILEGIBLE_no_tumba_el_gabinete(tmp_path) -> None:
    """Un corte a mitad de escritura no puede impedir que el edge arranque: la
    detección vale más que la continuidad del episodio."""
    estado = tmp_path / "episodio.json"
    estado.write_text("{esto no es json", encoding="utf-8")
    t = _tracker(state_path=estado)
    assert t.observe(_d(Tier.WATCH), latched=False, now=T0) is not None


def test_la_transicion_declara_EL_MISMO_sitio_que_el_evento() -> None:
    """Apertura y cierre tienen que caer en el mismo sitio.

    El `LocalEvent` se atribuye por `payload.site_id` (`settings.site_id`), no
    por el sitio propio del gateway en el registro. Si el cierre se atribuyera
    por el registro, en cuanto un gabinete sim atendiera a más de un sitio un
    incidente abierto en el X se concluiría en el Y — y el teléfono del X se
    quedaría contando, que es justo el defecto que esta ficha cierra.
    """
    t = _tracker()
    abre = t.observe(_d(Tier.EVACUATE_OR_HOLD, AlertSource.SASMEX), latched=True, now=T0)
    t.observe(_d(Tier.NORMAL), latched=False, now=T0 + timedelta(seconds=1))
    cierra = t.observe(_d(Tier.NORMAL), latched=False, now=T0 + timedelta(seconds=1 + QUIET))
    assert abre.site_id == cierra.site_id == SITIO
