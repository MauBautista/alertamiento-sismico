"""[T-9.35 · D-43] El diagnóstico de sensores fantasma es SOLO LECTURA.

`infra/scripts/diagnostico_sensores.sh` entra a la base de la NUBE por el túnel
SSM con el superusuario. Con esas credenciales, lo único que impide que un
diagnóstico escriba es el propio guion. La baja de un sensor la hace una persona
desde la consola (DAR DE BAJA → `queries/sensors.py::_RETIRE`), nunca esto.

Se guarda en el TEXTO del guion, que es lo que corre:

* reutiliza el túnel de `lib/tunel.sh` (no una cuarta copia del reenvío);
* abre la transacción `BEGIN READ ONLY` antes de cualquier consulta, así que un
  `INSERT` que se colara lo rechazaría la base misma;
* no contiene ninguna sentencia de escritura ni de DDL;
* consulta lo que la ficha pide: `status`, `kind`, `calibration_source` y las
  filas de `waveform_features_1s`, por sitio.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GUION = REPO / "infra" / "scripts" / "diagnostico_sensores.sh"

# Palabras que escriben o cambian el esquema. Se buscan como palabra entera y sin
# distinguir mayúsculas, sobre el guion SIN comentarios (el comentario que explica
# por qué no hay `UPDATE` no es un `UPDATE`).
_ESCRITURA = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "TRUNCATE",
    "ALTER",
    "DROP",
    "CREATE",
    "GRANT",
    "REVOKE",
    "COPY",
    "MERGE",
    "CALL",
)


def _sin_comentarios(texto: str) -> str:
    lineas = []
    for linea in texto.splitlines():
        if linea.lstrip().startswith("#"):
            continue
        # Comentario SQL de línea.
        lineas.append(re.sub(r"--.*$", "", linea))
    return "\n".join(lineas)


def test_el_guion_existe_y_es_ejecutable() -> None:
    assert GUION.is_file(), f"falta {GUION.relative_to(REPO)}"
    assert GUION.stat().st_mode & 0o111, "el guion debe ser ejecutable"


def test_usa_el_tunel_compartido() -> None:
    texto = GUION.read_text(encoding="utf-8")
    assert "lib/tunel.sh" in texto
    assert "abrir_tunel" in texto
    assert "start-session" not in texto, "el reenvío SSM vive en lib/tunel.sh, no se copia"


def test_abre_transaccion_read_only() -> None:
    codigo = _sin_comentarios(GUION.read_text(encoding="utf-8"))
    assert re.search(r"\bBEGIN\s+READ\s+ONLY\b", codigo, re.IGNORECASE), (
        "toda consulta debe correr dentro de BEGIN READ ONLY"
    )
    # Y no hay ningún camino que la cambie a escritura.
    assert not re.search(r"\bREAD\s+WRITE\b", codigo, re.IGNORECASE)
    assert not re.search(r"default_transaction_read_only\s*=\s*off", codigo, re.IGNORECASE)


def test_no_contiene_sentencias_de_escritura() -> None:
    codigo = _sin_comentarios(GUION.read_text(encoding="utf-8"))
    encontradas = [
        palabra for palabra in _ESCRITURA if re.search(rf"\b{palabra}\b", codigo, re.IGNORECASE)
    ]
    assert encontradas == [], f"el diagnóstico es de solo lectura; contiene {encontradas}"


def test_no_ejecuta_ficheros_sql_externos() -> None:
    """Un `-f fichero.sql` escondería la escritura fuera del texto que se revisa."""
    codigo = _sin_comentarios(GUION.read_text(encoding="utf-8"))
    assert not re.search(r"\s-f\s", codigo)
    assert r"\i " not in codigo and r"\ir " not in codigo


def test_consulta_lo_que_pide_la_ficha() -> None:
    codigo = _sin_comentarios(GUION.read_text(encoding="utf-8"))
    for columna in ("status", "kind", "calibration_source", "waveform_features_1s", "site"):
        assert columna in codigo, f"el diagnóstico debe mostrar {columna}"


def test_sintaxis_bash_valida() -> None:
    subprocess.run(["bash", "-n", str(GUION)], check=True, timeout=30)


# ── [F3·r2] `sites.code` se REPITE entre tenants: se agrupa por `site_id` ──────


def _sql_del_guion() -> list[str]:
    texto = GUION.read_text(encoding="utf-8")
    sql = texto.split("<<'SQL'", 1)[1].rsplit("\nSQL", 1)[0]
    sql = re.sub(r"--.*$", "", sql, flags=re.MULTILINE).replace(":'sitio'", "%(sitio)s")
    return [s.strip() for s in sql.split(";") if s.strip()]


def test_el_resumen_agrupa_por_site_id_y_dice_el_tenant() -> None:
    """Dos tenants con un sitio del MISMO código: el resumen tenía UNA fila que
    sumaba los sensores de los dos, y ninguna de las dos consultas decía de quién."""
    import uuid

    import psycopg

    from tests.dictamen.test_service import _dsn

    sentencias = _sql_del_guion()
    assert sentencias[0].upper() == "BEGIN READ ONLY"
    assert sentencias[-1].upper() == "ROLLBACK"
    codigo = f"DUP-{uuid.uuid4().hex[:6]}"
    with psycopg.connect(_dsn(), autocommit=False) as conn:
        try:
            for n, calibrado in ((1, "fabricante"), (2, None)):
                tenant, site = str(uuid.uuid4()), str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'Diag')",
                    (tenant, f"T{n}-{tenant[:6]}"),
                )
                conn.execute(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                    "(%s,%s,%s,'S', ST_SetSRID(ST_MakePoint(-99.1, 19.4),4326)::geography)",
                    (site, tenant, codigo),
                )
                conn.execute(
                    "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model, status, "
                    "calibration_source) VALUES (%s,%s,%s,'ground','RS4D','active',%s)",
                    (str(uuid.uuid4()), tenant, site, calibrado),
                )
            # sólo las consultas (el BEGIN/ROLLBACK del guion los hace esta conexión)
            detalle = conn.execute(sentencias[1], {"sitio": codigo}).fetchall()
            resumen = conn.execute(sentencias[2], {"sitio": codigo}).fetchall()
            cols = [c.name for c in conn.execute(sentencias[2], {"sitio": codigo}).description]
        finally:
            conn.rollback()
    assert len(detalle) == 2
    assert len(resumen) == 2, "un sitio por tenant, no la suma de los dos"
    assert "tenant" in cols
    veredictos = sorted(r[cols.index("dictamen_v2")] for r in resumen)
    assert veredictos == ["no puede salir VERDE: hay activos sin calibrar", "puede salir VERDE"]


def test_calibrado_con_SOLO_ESPACIOS_es_sin_calibrar_como_en_el_worker() -> None:
    """[F3·r3] El worker usa ``NULLIF(btrim(calibration_source), '')``: un valor de
    sólo espacios es SIN calibrar y deja el sitio en AMARILLO. El diagnóstico decía
    'ok' / «puede salir VERDE» con ese mismo sensor."""
    import uuid

    import psycopg

    from tests.dictamen.test_service import _dsn

    sentencias = _sql_del_guion()
    codigo = f"ESP-{uuid.uuid4().hex[:6]}"
    with psycopg.connect(_dsn(), autocommit=False) as conn:
        try:
            tenant, site = str(uuid.uuid4()), str(uuid.uuid4())
            conn.execute(
                "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'Diag')",
                (tenant, f"TE-{tenant[:6]}"),
            )
            conn.execute(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(%s,%s,%s,'S', ST_SetSRID(ST_MakePoint(-99.1, 19.4),4326)::geography)",
                (site, tenant, codigo),
            )
            sensor = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model, status, "
                "calibration_source) VALUES (%s,%s,%s,'ground','RS4D','active','   ')",
                (sensor, tenant, site),
            )
            conn.execute(
                "INSERT INTO waveform_features_1s (ts, tenant_id, site_id, sensor_id, channel, "
                "pga_g) VALUES (now(), %s, %s, %s, 'ENZ', 0.01)",
                (tenant, site, sensor),
            )
            det = conn.execute(sentencias[1], {"sitio": codigo})
            dcols = [c.name for c in det.description]
            detalle = det.fetchall()
            res = conn.execute(sentencias[2], {"sitio": codigo})
            rcols = [c.name for c in res.description]
            resumen = res.fetchall()
        finally:
            conn.rollback()
    [fila] = detalle
    assert fila[dcols.index("lectura")] == "activo sin calibrar: impide VERDE"
    assert fila[dcols.index("calibration_source")] == "— SIN CALIBRAR —"
    [r] = resumen
    assert r[rcols.index("dictamen_v2")] == "no puede salir VERDE: hay activos sin calibrar"
