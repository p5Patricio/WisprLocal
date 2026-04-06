"""Captura de audio via sounddevice."""

from __future__ import annotations

import sounddevice as sd

from wispr.state import AppState


def start_stream(state: AppState, config: dict) -> sd.InputStream:
    """Crea e inicia el InputStream de PortAudio.

    El callback es O(1): sólo encola si está grabando.
    """
    sample_rate: int = config["audio"]["sample_rate"]
    channels: int = config["audio"]["channels"]
    dtype: str = config["audio"]["dtype"]

    def _callback(indata, frames, time_info, status):  # noqa: ARG001
        if state.is_recording():
            state.audio_queue.put(indata.copy())

    stream = sd.InputStream(
        samplerate=sample_rate,
        channels=channels,
        dtype=dtype,
        callback=_callback,
    )
    stream.start()
    return stream


def stop_stream(stream: sd.InputStream) -> None:
    """Detiene y cierra el stream de audio."""
    try:
        stream.stop()
        stream.close()
    except Exception:
        pass
