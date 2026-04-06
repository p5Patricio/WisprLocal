"""Carga de modelo y worker de transcripción."""

from __future__ import annotations

import logging
from typing import Callable

import numpy as np
from faster_whisper import WhisperModel

from wispr.state import AppState

logger = logging.getLogger(__name__)


def load_model(state: AppState, config: dict, sounds, overlay=None) -> None:
    """Carga WhisperModel en GPU y avisa via sounds.play_ready().

    overlay: instancia de RecordingOverlay (opcional). Si se provee, muestra
    el estado "loading" durante la carga y lo oculta al terminar.
    """
    if state.model is not None or state.is_loading:
        return

    state.is_loading = True
    model_cfg = config["model"]
    logger.info("Cargando modelo %s en %s...", model_cfg["name"], model_cfg["device"])

    if overlay is not None:
        overlay.show_loading()

    try:
        model = WhisperModel(
            model_cfg["name"],
            device=model_cfg["device"],
            compute_type=model_cfg["compute_type"],
        )
        state.set_model(model)
        sounds.play_ready()
        logger.info("Modelo cargado y listo.")
    except Exception:
        logger.exception("Error al cargar el modelo")
        sounds.play_error()
    finally:
        state.is_loading = False
        if overlay is not None:
            overlay.hide()


def unload_model(state: AppState) -> None:
    """Libera el modelo de VRAM."""
    if state.model is None:
        return
    logger.info("Liberando modelo de VRAM...")
    state.clear_model()
    logger.info("VRAM liberada.")


def transcription_worker(
    state: AppState,
    config: dict,
    injection_fn: Callable[[str], None],
    sounds,
) -> None:
    """Worker daemon: acumula chunks de audio y transcribe al recibir sentinel None."""
    sample_rate: int = config["audio"]["sample_rate"]
    transcription_cfg = config["transcription"]
    min_duration: float = transcription_cfg["min_duration"]
    min_frames = int(sample_rate * min_duration)
    language: str | None = transcription_cfg["language"] or None
    prompt: str = transcription_cfg["prompt"]
    beam_size: int = transcription_cfg["beam_size"]

    buffer: list = []
    while True:
        chunk = state.audio_queue.get()
        if chunk is None:
            # Sentinel: procesar buffer acumulado
            if buffer and state.model is not None:
                audio_np = np.concatenate(buffer, axis=0).flatten()
                if len(audio_np) >= min_frames:
                    # Normalizar
                    peak = np.max(np.abs(audio_np))
                    if peak > 0:
                        audio_np = audio_np / peak

                    try:
                        segments, _ = state.model.transcribe(
                            audio_np,
                            language=language,
                            task="transcribe",
                            beam_size=beam_size,
                            initial_prompt=prompt,
                        )
                        text = "".join(seg.text for seg in segments).strip()
                        if text:
                            logger.info("Transcripción: %s", text)
                            injection_fn(text)
                    except Exception:
                        logger.exception("Error en transcripción")
                        sounds.play_error()
            buffer = []
        else:
            buffer.append(chunk)
