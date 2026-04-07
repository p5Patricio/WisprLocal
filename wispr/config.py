"""Carga y validación de configuración desde config.toml."""

from __future__ import annotations

import copy
import logging
import pathlib
import tomllib

log = logging.getLogger(__name__)

DEFAULTS = {
    "model": {
        "name": "large-v3",
        "device": "cuda",
        "compute_type": "int8_float16",
    },
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
        "dtype": "float32",
    },
    "hotkeys": {
        "ptt": "caps_lock",
        "toggle": "f10",
        "load_model_key": "",
    },
    "overlay": {
        "enabled": True,
        "position": "bottom-right",
        "opacity": 0.85,
        "font_size": 14,
    },
    "transcription": {
        "language": "",
        "prompt": "Nota técnica. Testing code, PRs, backend logs. Spanglish mode.",
        "min_duration": 0.3,
        "beam_size": 1,
    },
}

DEFAULT_TOML_CONTENT = """\
# WisprLocal — Configuración
# Editá este archivo para personalizar la herramienta.
# Los cambios se aplican al reiniciar la aplicación.

[model]
# Modelo de Whisper a usar. Opciones: tiny, base, small, medium, large-v2, large-v3
name = "large-v3"
# Dispositivo de cómputo. Opciones: "cuda" (GPU NVIDIA), "cpu"
device = "cuda"
# Tipo de cómputo. Opciones: "float16", "int8_float16", "int8"
# float16 = máxima calidad, int8_float16 = balance calidad/VRAM, int8 = mínima VRAM
compute_type = "int8_float16"

[audio]
# Frecuencia de muestreo en Hz. No cambiar salvo que tengas problemas de audio.
sample_rate = 16000
# Canales de audio (1 = mono, recomendado)
channels = 1
# Tipo de dato del audio interno
dtype = "float32"

[hotkeys]
# Tecla para Push-to-Talk (mantener presionada mientras hablás)
# Opciones comunes: "caps_lock", "f9", "f10", "f11", "f12", "scroll_lock"
ptt = "caps_lock"
# Tecla para Toggle (presionar para iniciar grabación, volver a presionar para detener)
# Opciones comunes: "f10", "f11", "f12", "scroll_lock", "pause"
toggle = "f10"
# (Opcional) Tecla para cargar/descargar el modelo manualmente. Dejar vacío para desactivar.
load_model_key = ""

[overlay]
# Mostrar indicador visual de grabación en pantalla
enabled = true
# Posición del indicador. Opciones: "bottom-right", "bottom-left", "top-right", "top-left"
position = "bottom-right"
# Opacidad del indicador (0.1 = casi invisible, 1.0 = sólido)
opacity = 0.85
# Tamaño de la fuente del indicador
font_size = 14

[transcription]
# Idioma de transcripción. "" = detección automática (recomendado para Spanglish)
language = ""
# Prompt para guiar la transcripción bilingüe
prompt = "Nota técnica. Testing code, PRs, backend logs. Spanglish mode."
# Mínimo de segundos de audio para transcribir (evita transcribir ruido)
min_duration = 0.3
# Tamaño del beam para la transcripción (1 = más rápido, más = más preciso)
beam_size = 1
"""


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base recursively. Override wins on conflicts."""
    result = copy.deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _validate(config: dict) -> None:
    """Raise ValueError on invalid config values."""
    valid_devices = ("cuda", "cpu")
    if config["model"]["device"] not in valid_devices:
        raise ValueError(
            f"model.device debe ser uno de {valid_devices}, se recibió: '{config['model']['device']}'"
        )

    valid_compute = ("float16", "int8_float16", "int8", "float32")
    if config["model"]["compute_type"] not in valid_compute:
        raise ValueError(f"model.compute_type debe ser uno de {valid_compute}")

    valid_positions = ("bottom-right", "bottom-left", "top-right", "top-left")
    if config["overlay"]["position"] not in valid_positions:
        raise ValueError(f"overlay.position debe ser uno de {valid_positions}")

    opacity = config["overlay"]["opacity"]
    if not (0.1 <= opacity <= 1.0):
        raise ValueError(
            f"overlay.opacity debe estar entre 0.1 y 1.0, se recibió: {opacity}"
        )

    if not isinstance(config["hotkeys"]["ptt"], str) or not config["hotkeys"]["ptt"].strip():
        raise ValueError("hotkeys.ptt debe ser un string no vacío")

    toggle = config["hotkeys"]["toggle"]
    if isinstance(toggle, list):
        if not toggle:
            raise ValueError("hotkeys.toggle no puede ser una lista vacía")
        for k in toggle:
            if not isinstance(k, str):
                raise ValueError(f"hotkeys.toggle debe contener strings, se recibió: {type(k)}")
        # Warn on dangerous combos
        if set(k.lower() for k in toggle) == {"win", "l"}:
            log.warning("hotkeys.toggle = ['win', 'l'] conflicta con el bloqueo de pantalla de Windows")
    elif isinstance(toggle, str):
        if not toggle.strip():
            raise ValueError("hotkeys.toggle debe ser un string no vacío")
    else:
        raise ValueError("hotkeys.toggle debe ser un string o una lista de strings")


def _write_default_config(path: pathlib.Path) -> None:
    """Write a commented default config.toml."""
    path.write_text(DEFAULT_TOML_CONTENT, encoding="utf-8")


def load_config(path: str = "config.toml") -> dict:
    """Carga config.toml, fusiona con DEFAULTS y valida. Crea el archivo si no existe."""
    p = pathlib.Path(path)
    if not p.exists():
        log.info(
            "config.toml no encontrado, creando con valores por defecto en %s",
            p.resolve(),
        )
        _write_default_config(p)
        return copy.deepcopy(DEFAULTS)

    with open(p, "rb") as f:
        user_config = tomllib.load(f)

    config = _deep_merge(DEFAULTS, user_config)
    _validate(config)
    return config
