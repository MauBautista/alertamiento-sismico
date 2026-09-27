# tools/audio · canal de audio auditable (T-9.10 · D-40)

Todo audio que suena en el edificio (edge) o en el teléfono (mobile) tiene una entrada en
`shared/audio/MANIFEST.json` con su sha256, duración, formato, sonoridad, fuente y licencia.

## Regenerar

```bash
tools/audio/gen_voces.sh      # requiere uv, curl, jq, sha256sum
```

De punta a punta: verifica el modelo de voz, sintetiza, normaliza, copia a las rutas de
`voces.json`, reescribe el manifiesto y lo verifica. Dos corridas en la misma máquina dan los
mismos bytes (medido 2026-09-27). Con otra CPU u otra versión de `onnxruntime` los bytes
pueden cambiar: entonces cambia el sha256 del manifiesto y hay que comitear ambos juntos.

Añadir una voz = añadir una entrada a `voces.json` y correr el script.

## Qué hace cada pieza

| Fichero | Qué hace | Entorno |
|---|---|---|
| `voces.json` | Versión fijada de Piper y onnxruntime, modelo con sus sha256, y cada voz (texto, semilla, parámetros, rutas, duración máxima) | — |
| `gen_voces.sh` | Orquesta todo. **No confía en la caché**: si el `.onnx` o el `.onnx.json` faltan o su sha256 no cuadra, los descarga de `huggingface.co/rhasspy/piper-voices` y vuelve a verificar | bash |
| `sintetiza.py` | Piper por su API con `onnxruntime.set_seed` (el CLI de piper mete ruido sin semilla: dos corridas daban bytes distintos) | `uv run --no-project --with piper-tts==1.3.0 --with onnxruntime==1.30.0` |
| `normaliza.py` | Mono PCM16 a 22 050 o 44 100 Hz; recorta la cola (deja 100 ms + fundido de 10 ms); −16 LUFS integrados, limitado para quedar en ≤ −1 dBTP de pico verdadero (×4 con `resample_poly`). `--mide` solo mide | `uv run --no-project --with numpy==2.5.3 --with scipy==1.18.1 --with pyloudnorm==0.2.0` |
| `manifiesto.py` | Escribe el manifiesto. La procedencia se declara (tonos existentes en el código, voces en `voces.json`), las cifras se miden | el mismo que `normaliza.py` |
| `verifica_manifiesto.py` | Solo stdlib. Sale ≠ 0 si una ruta no cuadra en sha256, duración (±5 ms), frecuencia o canales, o si algún `.wav/.mp3/.ogg/.caf` de `mobile/assets`, `edge/` o `shared/audio` falta en el manifiesto | `python3` |

`api/tests/test_censo_audio.py` corre el verificador y además exige: el aviso de movimiento en
≤ 4,0 s, licencia no vacía en toda entrada, ninguna herramienta GPL declarada como dependencia
y ningún modelo de voz dentro del repo.

## Licencias

- **Piper (`piper-tts` 1.x) es GPL-3.0** e incluye espeak-ng (GPL-3.0). Por eso **no entra en
  ningún `pyproject.toml` ni `package.json`** del repo (D-24, `ci/check-licenses.sh`): se
  ejecuta aislado con `uv run --no-project`. Lo que produce (el WAV) no es código de Piper.
- **Voz `es_MX-claude-high`**: licencia apache-2.0 declarada en su MODEL_CARD
  (rhasspy/piper-voices; dataset HirCoir/Piper-TTS-Spanish). El modelo no se versiona.
- **Alternativa**: `es_MX-ald-medium` (dataset con licencia Unlicense), por si la anterior
  deja de ser aceptable; sus sha256 están en `voces.json`.
- Los tonos del edge (`siren`, `simulacro`) son originales de TAKAB y sus scripts en
  `edge/scripts/` los reproducen byte a byte. `prueba.wav` se declara original de TAKAB
  (T-2.49) pero **no hay generador en el repo**: el manifiesto lo dice tal cual.

## Lo que el manifiesto deja a la vista

La sirena (`alerta_sismica.wav` en la app) mide −7,7 LUFS y la voz −16 LUFS: si ambas suenan
en el teléfono, la voz se oirá bastante más baja. Esto se decide al escucharlo (T-9.11/T-9.70),
no aquí.
