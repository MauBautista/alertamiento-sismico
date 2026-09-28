"""[T-9.60 · D-46] El worker `catalog-sync`: el catálogo de México al día, sin inventar.

Lo que fija esta suite, por orden de lo que costaría equivocarse:

1. **Nunca queda `ok` si no se escribió.** Un fallo HTTP o de base deja
   `fallido` con su motivo y NO avanza `ultimo_updated`: la siguiente pasada
   vuelve a pedir lo mismo. Un catálogo congelado que dijera «al día» es la
   mentira que la regla de oro 7 prohíbe.
2. **Una fila de otro origen no se pisa.** Las sembradas (`seed`) y las que
   escribió la consulta por incidente (`catalogo`) citan dictámenes firmados;
   el worker sólo reescribe lo que él mismo escribió.
3. **Idempotencia** (regla de oro 3): dos pasadas sobre la misma respuesta no
   duplican una fila, y una revisión de magnitud en la fuente SÍ se refleja.
4. **Apagado, ocupado y truncado se DICEN** en el estado o en el resultado.

Sin red en ningún momento: el transporte es `httpx.MockTransport`, y el camino
apagado se prueba con un transporte que revienta si alguien lo toca.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.catalogo import fdsn
from takab_api.catalogo import sincroniza as S
from takab_api.settings import Settings
from tests.catalogo.fixtures import CRUDA_TEHUANTEPEC, cruda, dsn

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def _settings(**over) -> Settings:
    return Settings(**{"catalog_usgs_enabled": True, **over})


def _ms(t: datetime) -> int:
    return int(t.timestamp() * 1000)


def _evento(
    pid: str,
    *,
    origen: datetime,
    mag: float | None = 4.5,
    actualizado: datetime | None = None,
    status: str = "automatic",
    lat: float = 16.5,
    lon: float = -98.2,
    depth: float = 20.0,
    mmi: float | None = None,
) -> dict:
    """Un feature con la forma del FDSN de USGS (`[lon, lat, prof]`)."""
    return {
        "type": "Feature",
        "id": pid,
        "properties": {
            "mag": mag,
            "place": f"lugar de {pid}",
            "time": _ms(origen),
            "updated": _ms(actualizado or origen + timedelta(minutes=20)),
            "status": status,
            "magType": "mww",
            "mmi": mmi,
            "url": f"https://earthquake.usgs.gov/earthquakes/eventpage/{pid}",
        },
        "geometry": {"type": "Point", "coordinates": [lon, lat, depth]},
    }


def _sobre(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "metadata": {}, "features": features}


class Fuente:
    """Un USGS de mentira que HONRA `starttime`, `orderby=time-asc` y `limit`.

    Guarda cada URL que se le pide: la pregunta es la mitad de lo que se prueba.
    """

    def __init__(self, features: list[dict], status: int = 200) -> None:
        self.features = features
        self.status = status
        self.pedidas: list[dict[str, str]] = []

    def transporte(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            q = {k: v[0] for k, v in parse_qs(urlparse(str(request.url)).query).items()}
            self.pedidas.append(q)
            if self.status != 200:
                return httpx.Response(self.status, text="mantenimiento")
            desde = datetime.fromisoformat(q["starttime"].replace("Z", "+00:00"))
            vivos = sorted(
                (f for f in self.features if f["properties"]["time"] >= _ms(desde)),
                key=lambda f: f["properties"]["time"],
            )
            return httpx.Response(200, json=_sobre(vivos[: int(q["limit"])]))

        return httpx.MockTransport(handler)


def _transporte_que_revienta() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise AssertionError("el camino apagado abrió un socket")

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# La pregunta (puro, sin base)
# ---------------------------------------------------------------------------


def test_la_url_de_sincronizacion_lleva_la_caja_de_mexico_y_el_cursor() -> None:
    url = fdsn.url_de_sincronizacion(
        "https://x/query",
        desde_updated=datetime(2026, 9, 1, tzinfo=UTC),
        desde_origen=datetime(2026, 7, 1, tzinfo=UTC),
        min_mag=4.0,
        caja=fdsn.CAJA_MEXICO,
        limite=2000,
    )
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert q == {
        "format": "geojson",
        "minlatitude": "14",
        "maxlatitude": "33.5",
        "minlongitude": "-118.5",
        "maxlongitude": "-86",
        "minmagnitude": "4",
        "updatedafter": "2026-09-01T00:00:00Z",
        "starttime": "2026-07-01T00:00:00Z",
        "orderby": "time-asc",
        "limit": "2000",
    }


def test_parsea_conserva_updated_mmi_y_url_sin_romper_a_la_consulta() -> None:
    t0 = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
    (ev,) = fdsn.parsea(_sobre([_evento("us1", origen=t0, mmi=4.2)]))
    assert ev.actualizado_en_fuente == t0 + timedelta(minutes=20)
    assert ev.mmi == 4.2
    assert ev.url == "https://earthquake.usgs.gov/earthquakes/eventpage/us1"
    # Los usuarios de siempre construyen `EventoPublicado` sin los campos nuevos.
    viejo = fdsn.EventoPublicado("x", t0, 5.0, 1.0, 2.0, 3.0, "p", "reviewed")
    assert viejo.mmi is None and viejo.url is None and viejo.actualizado_en_fuente is None


def test_el_tope_de_bytes_de_la_sincronizacion_cubre_el_limite_con_el_peor_caso() -> None:
    """La cota se DERIVA del peor peso por evento archivado (1097 B, Valdez), no se
    teclea: `catalog_usgs_max_bytes` (512 KB) no alcanza para 2000 eventos, y por eso
    la sincronización lleva su propio tope."""
    from tests.catalogo.fixtures import CRUDA_AUTOMATICA

    peor = max(
        len(r.read_bytes()) / len(cruda(r)["features"])
        for r in (CRUDA_AUTOMATICA, CRUDA_TEHUANTEPEC)
    )
    s = Settings()
    necesario = peor * s.catalog_sync_limite
    assert s.catalog_usgs_max_bytes < necesario, "si ya cabía, el tope propio sobra"
    assert s.catalog_sync_max_bytes >= 1.5 * necesario


def test_sincroniza_apagada_no_abre_un_socket() -> None:
    with pytest.raises(fdsn.SinRespuesta, match="apagada"):
        fdsn.sincroniza(
            Settings(catalog_usgs_enabled=False),
            desde_updated=NOW,
            desde_origen=NOW,
            transport=_transporte_que_revienta(),
        )


def test_sincroniza_cuenta_los_publicados_aunque_alguno_se_descarte() -> None:
    """El truncado se decide con lo que MANDÓ la fuente, no con lo que se pudo leer:
    un evento sin coordenadas no puede esconder que la página vino llena."""
    t0 = NOW - timedelta(days=1)
    roto = _evento("roto", origen=t0)
    roto["geometry"] = None
    fuente = Fuente([_evento("bueno", origen=t0), roto])
    r = fdsn.sincroniza(
        _settings(),
        desde_updated=t0 - timedelta(days=1),
        desde_origen=t0 - timedelta(days=1),
        transport=fuente.transporte(),
    )
    assert r.publicados == 2
    assert [e.provider_event_id for e in r.eventos] == ["bueno"]


# ---------------------------------------------------------------------------
# La pasada (contra la base, con el rol del worker)
# ---------------------------------------------------------------------------


class Esc:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def pasada(self, fuente: Fuente | None, *, now: datetime = NOW, **over) -> S.PasadaSync:
        """Con el rol del worker (`takab_ingest`), no como superusuario: así se
        verifican los GRANT de la 0076."""
        self.conn.execute('SET ROLE "takab_ingest"')
        try:
            return S.run_catalog_sync_pass(
                self.conn,
                _settings(**over),
                now=now,
                transport=fuente.transporte() if fuente else _transporte_que_revienta(),
            )
        finally:
            self.conn.rollback()
            self.conn.execute("RESET ROLE")
            self.conn.commit()

    def estado(self) -> dict | None:
        return self.conn.execute(
            "SELECT * FROM catalog_sync_state WHERE fuente = 'USGS'"
        ).fetchone()

    def fila(self, pid: str) -> dict | None:
        return self.conn.execute(
            "SELECT catalog_key, origen, magnitude::float8 AS magnitude, review_status,"
            " source_ref, usgs_mmi::float8 AS usgs_mmi, usgs_url, actualizado_en_fuente,"
            " consulted_at FROM reference_earthquakes"
            " WHERE source = 'USGS' AND provider_event_id = %s",
            (pid,),
        ).fetchone()

    def cuantas(self, origen: str = "catalog_sync") -> int:
        return self.conn.execute(
            "SELECT count(*) AS n FROM reference_earthquakes WHERE origen = %s", (origen,)
        ).fetchone()["n"]


@pytest.fixture
def esc() -> Iterator[Esc]:
    conn = psycopg.connect(dsn(), autocommit=False, row_factory=dict_row)
    try:
        _limpia(conn)
        yield Esc(conn)
    finally:
        _limpia(conn)
        conn.close()


def _limpia(conn: psycopg.Connection) -> None:
    conn.rollback()
    conn.execute("RESET ROLE")
    conn.execute("DELETE FROM catalog_sync_state")
    conn.execute("DELETE FROM reference_earthquakes WHERE origen = 'catalog_sync'")
    conn.execute("DELETE FROM reference_earthquakes WHERE catalog_key LIKE 'T960-%'")
    conn.commit()


def test_primera_corrida_pide_90_dias_y_escribe_ok(esc: Esc) -> None:
    fuente = Fuente(cruda(CRUDA_TEHUANTEPEC)["features"])
    # Tehuantepec es de 2017: se pide «ahora» como si fuera el día siguiente.
    ahora = datetime(2017, 9, 9, tzinfo=UTC)
    r = esc.pasada(fuente, now=ahora)

    (q,) = fuente.pedidas
    noventa = (ahora - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert q["updatedafter"] == noventa
    assert q["starttime"] == noventa
    assert q["minmagnitude"] == "4"
    assert r.estado == "ok" and r.escritos == 14 and not r.truncada

    st = esc.estado()
    assert st["estado"] == "ok"
    assert st["n_ultima"] == 14
    assert st["ultimo_ok"] == ahora and st["ultima_corrida"] == ahora
    assert st["error"] is None
    mayor = max(f["properties"]["updated"] for f in cruda(CRUDA_TEHUANTEPEC)["features"])
    assert st["ultimo_updated"] == datetime.fromtimestamp(mayor / 1000, tz=UTC)

    fila = esc.fila("us2000ay3t")
    assert fila["catalog_key"] == "USGS-us2000ay3t"
    assert fila["origen"] == "catalog_sync"
    assert fila["magnitude"] == 4.4
    assert fila["review_status"] == "confirmado"
    assert fila["usgs_url"] == "https://earthquake.usgs.gov/earthquakes/eventpage/us2000ay3t"
    assert fila["consulted_at"] == ahora
    assert fila["source_ref"].startswith("USGS FDSN us2000ay3t (mb 4.4")

    # La segunda pide DESDE el mayor `updated` visto, no otra vez 90 días.
    esc.pasada(fuente, now=ahora + timedelta(minutes=10))
    assert fuente.pedidas[1]["updatedafter"] == st["ultimo_updated"].strftime("%Y-%m-%dT%H:%M:%SZ")


def test_el_upsert_es_idempotente(esc: Esc) -> None:
    fuente = Fuente(cruda(CRUDA_TEHUANTEPEC)["features"])
    ahora = datetime(2017, 9, 9, tzinfo=UTC)
    esc.pasada(fuente, now=ahora)
    # La misma respuesta otra vez: una fuente que no respeta `updatedafter` no
    # puede duplicar nada.
    fuente2 = Fuente(cruda(CRUDA_TEHUANTEPEC)["features"])
    r = esc.pasada(fuente2, now=ahora + timedelta(minutes=10))
    assert r.estado == "ok"
    assert esc.cuantas() == 14


def test_no_pisa_una_fila_sembrada(esc: Esc) -> None:
    t0 = NOW - timedelta(days=3)
    esc.conn.execute(
        "INSERT INTO reference_earthquakes (catalog_key, origin_time, magnitude, place,"
        " epicenter, depth_km, source, source_ref, provider_event_id)"
        " VALUES ('T960-SEED', %s, 7.1, 'sembrado a mano',"
        " ST_SetSRID(ST_MakePoint(-98.2, 16.5), 4326)::geography, 20, 'USGS',"
        " 'cita del seed', 'usSEED')",
        (t0,),
    )
    esc.conn.commit()
    fuente = Fuente([_evento("usSEED", origen=t0, mag=6.9), _evento("usOTRO", origen=t0)])
    r = esc.pasada(fuente)
    assert r.estado == "ok"
    assert r.escritos == 1 and r.respetadas == 1
    seed = esc.fila("usSEED")
    assert seed["catalog_key"] == "T960-SEED"
    assert seed["origen"] == "seed"
    assert seed["magnitude"] == 7.1
    assert seed["source_ref"] == "cita del seed"
    assert esc.fila("usOTRO")["origen"] == "catalog_sync"


def test_no_pisa_una_fila_de_la_consulta_por_incidente(esc: Esc) -> None:
    t0 = NOW - timedelta(days=3)
    esc.conn.execute(
        "INSERT INTO reference_earthquakes (catalog_key, origin_time, magnitude, place,"
        " epicenter, depth_km, source, source_ref, provider_event_id, origen)"
        " VALUES ('T960-CONS', %s, 5.2, 'de la consulta',"
        " ST_SetSRID(ST_MakePoint(-98.2, 16.5), 4326)::geography, 20, 'USGS',"
        " 'cita de la consulta', 'usCONS', 'catalogo')",
        (t0,),
    )
    esc.conn.commit()
    esc.pasada(Fuente([_evento("usCONS", origen=t0, mag=5.5)]))
    fila = esc.fila("usCONS")
    assert (fila["origen"], fila["magnitude"]) == ("catalogo", 5.2)


def test_una_revision_de_magnitud_se_actualiza(esc: Esc) -> None:
    t0 = NOW - timedelta(days=2)
    esc.pasada(Fuente([_evento("usREV", origen=t0, mag=4.4, status="automatic")]))
    assert esc.fila("usREV")["review_status"] == "preliminar"

    revisado = t0 + timedelta(days=1)
    esc.pasada(
        Fuente(
            [_evento("usREV", origen=t0, mag=4.7, status="reviewed", actualizado=revisado, mmi=4.1)]
        ),
        now=NOW + timedelta(minutes=10),
    )
    fila = esc.fila("usREV")
    assert fila["magnitude"] == 4.7
    assert fila["review_status"] == "confirmado"
    assert fila["actualizado_en_fuente"] == revisado
    assert fila["usgs_mmi"] == 4.1
    assert fila["consulted_at"] == NOW + timedelta(minutes=10)
    assert esc.cuantas() == 1


def test_un_fallo_http_deja_fallido_sin_avanzar(esc: Esc) -> None:
    t0 = NOW - timedelta(days=2)
    esc.pasada(Fuente([_evento("usA", origen=t0)]))
    antes = esc.estado()
    assert antes["estado"] == "ok"

    r = esc.pasada(Fuente([], status=503), now=NOW + timedelta(minutes=10))
    assert r.estado == "fallido"
    st = esc.estado()
    assert st["estado"] == "fallido"
    assert "HTTP 503" in st["error"]
    assert st["ultimo_updated"] == antes["ultimo_updated"]
    assert st["ultimo_ok"] == antes["ultimo_ok"]
    assert st["ultima_corrida"] == NOW + timedelta(minutes=10)


def test_un_fallo_al_escribir_no_deja_ok(esc: Esc, monkeypatch: pytest.MonkeyPatch) -> None:
    """El caso que la cabecera promete: la red contestó y la BASE falló."""
    t0 = NOW - timedelta(days=2)

    def revienta(*_a, **_k):
        raise psycopg.errors.CheckViolation("x" * 1000)

    monkeypatch.setattr(S, "_graba", revienta)
    r = esc.pasada(Fuente([_evento("usB", origen=t0)]))
    assert r.estado == "fallido"
    st = esc.estado()
    assert st["estado"] == "fallido"
    assert st["ultimo_ok"] is None and st["ultimo_updated"] is None
    assert len(st["error"]) <= 300
    assert esc.fila("usB") is None


def test_apagado_se_declara_y_no_consulta(esc: Esc) -> None:
    r = esc.pasada(None, catalog_usgs_enabled=False)
    assert r.estado == "apagado"
    st = esc.estado()
    assert st["estado"] == "apagado"
    assert "apagada" in st["error"]
    assert st["ultima_corrida"] == NOW
    assert st["ultimo_ok"] is None


def test_el_truncado_se_declara_y_la_siguiente_sigue_desde_ahi(esc: Esc) -> None:
    base = NOW - timedelta(days=10)
    # `updated` DECRECIENTE con el origen: el caso en que avanzar la marca de
    # `updated` al truncar se saltaría los que faltan (la fuente ordena por hora
    # de origen, no por `updated`).
    feats = [
        _evento(
            f"usT{i}", origen=base + timedelta(hours=i), actualizado=NOW - timedelta(hours=1 + i)
        )
        for i in range(4)
    ]
    fuente = Fuente(feats)
    r1 = esc.pasada(fuente, catalog_sync_limite=3)
    assert r1.truncada and r1.estado == "ok" and r1.escritos == 3
    st1 = esc.estado()
    assert st1["pagina_desde"] == base + timedelta(hours=2)
    assert st1["ultimo_updated"] is None, "no se avanza la marca a mitad de página"

    r2 = esc.pasada(fuente, now=NOW + timedelta(minutes=10), catalog_sync_limite=3)
    assert fuente.pedidas[1]["starttime"] == (base + timedelta(hours=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    assert not r2.truncada
    st2 = esc.estado()
    assert st2["pagina_desde"] is None
    assert st2["ultimo_updated"] == NOW - timedelta(hours=1)  # el mayor de TODAS las páginas
    assert esc.cuantas() == 4


def test_un_evento_sin_magnitud_no_se_escribe_y_se_cuenta(esc: Esc) -> None:
    t0 = NOW - timedelta(days=1)
    r = esc.pasada(Fuente([_evento("usSM", origen=t0, mag=None), _evento("usCM", origen=t0)]))
    assert r.escritos == 1 and r.sin_magnitud == 1
    assert esc.fila("usSM") is None


def test_ocupado_se_dice_y_no_pregunta(esc: Esc) -> None:
    otra = psycopg.connect(dsn(), autocommit=True)
    try:
        otra.execute("SELECT pg_advisory_lock(%s)", (S.LOCK_KEY,))
        r = esc.pasada(None)
        assert r.estado == "ocupado"
    finally:
        otra.close()
    assert esc.estado() is None


def test_takab_app_no_escribe_el_estado(esc: Esc) -> None:
    esc.conn.execute('SET ROLE "takab_app"')
    esc.conn.execute("SELECT count(*) FROM catalog_sync_state")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        esc.conn.execute(
            "INSERT INTO catalog_sync_state (fuente, estado) VALUES (%s, 'nunca')",
            (str(uuid.uuid4()),),
        )


def test_los_grant_de_la_nube_estan_escritos() -> None:
    """En la nube no vale el `ALL TABLES` de la 0001: los GRANT van en la 0076."""
    from tests.informes.test_privilegios_de_la_nube import _concedidas_a_ingest

    concedidas = _concedidas_a_ingest()
    assert {"catalog_sync_state", "reference_earthquakes"} <= concedidas


def test_el_worker_sobrevive_a_una_pasada_que_revienta() -> None:
    from takab_api.catalogo.sincroniza import CatalogSyncWorker

    llamadas: list[int] = []

    def pasada(_conn_factory, _settings) -> None:
        llamadas.append(1)
        if len(llamadas) == 1:
            raise RuntimeError("la base se fue")
        worker.stop()

    worker = CatalogSyncWorker(lambda: None, _settings(), poll_s=0.0, pasada=pasada)
    worker.run()
    assert len(llamadas) == 2
