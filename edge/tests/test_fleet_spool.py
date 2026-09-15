"""[T-7.20] El modo `spool`: la flota publicando contra el SOC local.

`make soc-local` levanta el sistema entero —supervisor del edge, consumer real,
handlers, motor de incidentes, consola— sustituyendo **un solo** tramo: IoT Core
+ SQS, por un directorio en disco (`demo/spool.py`). La flota sólo sabía
publicar a SQS o a IoT Core, así que `fleet --replay` —las estaciones sintiendo
la onda de un sismo del catálogo— no se podía enseñar en un navegador sin
desplegar a la nube, y la tabla por estación salía con el arribo TEÓRICO y jamás
con el medido, que es la comparación por la que esa tabla existe (`T-7.17`).

Lo que se fija aquí, por orden de lo que costaría equivocarse:

1. **Las tres claves `meta_*` de la IoT Rule.** Quien lee esos ficheros es el
   consumer de PRODUCCIÓN, que las separa antes de validar contra el schema. Sin
   ellas el mensaje entero acaba en la DLQ y el fallo se lee como «no llegó
   nada».
2. **El orden de publicación se reproduce ordenando por nombre**, que es lo que
   el consumer observa. Es el mismo contrato que `SpoolMqttTransport`.
3. **Escribe y renombra.** El consumer lee el directorio en caliente y sólo mira
   `*.json`: un fichero a medio escribir sería un JSON roto en la DLQ — una
   pérdida silenciosa, que es peor que un error.
4. **El modo exige su directorio.** Sin `--spool-dir` no hay a dónde publicar, y
   adivinar uno dejaría los mensajes en un sitio que nadie lee.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from simulators.fleet import OutMessage, _parse_args, make_spool_sender


def _mensaje(i: int) -> OutMessage:
    return OutMessage(
        topic="takab/features",
        thing=f"gw-sim-{i:04d}",
        payload={"site_id": f"site-sim-{i:03d}", "pga_g": 0.01 * i},
    )


def test_enriquece_con_las_TRES_claves_de_la_iot_rule(tmp_path: Path) -> None:
    make_spool_sender(tmp_path)([_mensaje(1)])

    (fichero,) = sorted(tmp_path.glob("*.json"))
    cuerpo = json.loads(fichero.read_text(encoding="utf-8"))
    assert cuerpo["meta_principal"] == "gw-sim-0001"
    assert cuerpo["meta_topic"] == "takab/features"
    assert isinstance(cuerpo["meta_ts_iot"], int)
    # Y el payload viaja intacto: el enriquecimiento AÑADE, no sustituye.
    assert cuerpo["site_id"] == "site-sim-001"


def test_el_ORDEN_por_nombre_es_el_de_publicacion(tmp_path: Path) -> None:
    """El consumer ordena por nombre; si el nombre no fuera monótono, dos
    mensajes del mismo gabinete podrían ingerirse al revés."""
    enviar = make_spool_sender(tmp_path)
    ok, errores = enviar([_mensaje(i) for i in range(1, 6)])
    assert (ok, errores) == (5, 0)

    leidos = [
        json.loads(p.read_text(encoding="utf-8"))["meta_principal"]
        for p in sorted(tmp_path.glob("*.json"))
    ]
    assert leidos == [f"gw-sim-{i:04d}" for i in range(1, 6)]


def test_no_deja_ficheros_a_MEDIO_ESCRIBIR_a_la_vista(tmp_path: Path) -> None:
    """El temporal no puede terminar en `.json`: el consumer lo leería a medias."""
    make_spool_sender(tmp_path)([_mensaje(1), _mensaje(2)])

    assert len(list(tmp_path.glob("*.json"))) == 2
    assert list(tmp_path.glob("*.tmp")) == [], "quedó un temporal sin renombrar"
    for p in tmp_path.glob("*.json"):
        json.loads(p.read_text(encoding="utf-8"))  # ninguno es JSON roto


def test_crea_el_directorio_si_no_existe(tmp_path: Path) -> None:
    destino = tmp_path / "cola" / "gw-sim-0001"
    make_spool_sender(destino)([_mensaje(1)])
    assert len(list(destino.glob("*.json"))) == 1


def test_el_modo_spool_EXIGE_su_directorio() -> None:
    """Adivinar uno dejaría los mensajes donde nadie los lee, y en silencio."""
    from simulators.fleet import main

    args = _parse_args(["--mode", "spool", "--duration-s", "1"])
    assert args.spool_dir is None
    with pytest.raises(SystemExit, match="--spool-dir"):
        main(["--mode", "spool", "--duration-s", "1"])


def test_los_modos_son_TRES_y_ninguno_mas() -> None:
    """Censo del CLI. `spool` es el único que no habla con AWS; si mañana nace
    otro modo local, que sea una decisión y no un descuido."""
    for bueno in ("sqs", "iot", "spool"):
        assert _parse_args(["--mode", bueno, "--duration-s", "1"]).mode == bueno
    for malo in ("local", "disco", "fichero"):
        with pytest.raises(SystemExit):
            _parse_args(["--mode", malo, "--duration-s", "1"])
