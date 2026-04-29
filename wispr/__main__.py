"""Composition root de WisprLocal."""

from __future__ import annotations

import logging
import pathlib
import sys
import threading

from wispr import config as config_module
from wispr import sounds
from wispr.audio import start_stream, stop_stream
from wispr.hotkeys import start_listener
from wispr.injection import inject_text
from wispr.overlay import RecordingOverlay
from wispr.state import AppState
from wispr.transcription import load_model, transcription_worker, unload_model
from wispr.tray import start_tray

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    config_path = pathlib.Path("config.toml")
    is_first_run = not config_path.exists()

    try:
        config = config_module.load_config()
    except ValueError as exc:
        log.error("Configuración inválida: %s", exc)
        sys.exit(1)

    if is_first_run and sys.platform == "darwin":
        log.warning(
            "macOS: Para que WisprLocal funcione correctamente, concedé permisos de "
            "Accesibilidad a la terminal/IDE desde la que se ejecuta "
            "(Preferencias del Sistema > Seguridad y Privacidad > Accesibilidad)."
        )

    log.info(
        "WisprLocal iniciando... PTT: %s | Toggle: %s",
        config["hotkeys"]["ptt"],
        config["hotkeys"]["toggle"],
    )

    queue_maxsize = config["audio"].get("queue_maxsize", 100)
    state = AppState(audio_queue_maxsize=queue_maxsize)
    overlay = RecordingOverlay(config)

    # 1. Transcription worker daemon
    worker = threading.Thread(
        target=transcription_worker,
        args=(state, config, inject_text, sounds),
        daemon=True,
    )
    worker.start()

    # 2. Model loader daemon (carga automática al arrancar)
    loader = threading.Thread(
        target=load_model,
        args=(state, config, sounds, overlay),
        daemon=True,
    )
    loader.start()

    # 3. Audio stream — siempre activo
    stream = start_stream(state, config)

    # 4. Keyboard listener
    listener = start_listener(state, config, overlay, sounds)

    # 5. Tray — BLOQUEA el main thread
    def _on_quit(icon):
        log.info("Iniciando shutdown...")
        state.shutdown_event.set()
        stop_stream(stream)
        listener.stop()
        state.audio_queue.put(None)
        worker.join(timeout=5)
        if worker.is_alive():
            log.warning("transcription_worker no terminó en 5s")
        loader.join(timeout=5)
        if loader.is_alive():
            log.warning("loader no terminó en 5s")
        unload_model(state)
        overlay.destroy()
        icon.stop()

    try:
        start_tray(
            state,
            config,
            on_load=lambda: threading.Thread(
                target=load_model,
                args=(state, config, sounds, overlay),
                daemon=True,
            ).start(),
            on_unload=lambda: unload_model(state),
            on_quit=_on_quit,
        )
    except KeyboardInterrupt:
        stop_stream(stream)


if __name__ == "__main__":
    main()
