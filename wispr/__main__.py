"""Composition root de WisprLocal."""

from __future__ import annotations

import logging
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

    try:
        cfg = config_module.load_config()
    except ValueError as exc:
        log.error("Configuración inválida: %s", exc)
        sys.exit(1)

    log.info(
        "WisprLocal iniciando... PTT: %s | Toggle: %s",
        cfg["hotkeys"]["ptt"],
        cfg["hotkeys"]["toggle"],
    )

    config = cfg

    state = AppState()
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
            on_quit=lambda icon: (
                stop_stream(stream),
                listener.stop(),
                overlay.destroy(),
                icon.stop(),
            ),
        )
    except KeyboardInterrupt:
        stop_stream(stream)


if __name__ == "__main__":
    main()
