"""Listener de teclado via pynput."""

from __future__ import annotations

import logging

from pynput import keyboard

from wispr.state import AppState

logger = logging.getLogger(__name__)

_active_modifiers: set[str] = set()
_toggle_lock = False


def start_listener(
    state: AppState,
    config: dict,  # noqa: ARG001 — reservado para teclas configurables en Fase 2
    overlay,
    sounds,
) -> keyboard.Listener:
    """Crea e inicia el Listener de teclado.

    CapsLock → PTT (push-to-talk)
    Alt+Shift → toggle de grabación continua
    """
    global _active_modifiers, _toggle_lock
    _active_modifiers = set()
    _toggle_lock = False

    def on_press(key):
        global _toggle_lock

        if state.model is None:
            # Sólo avisar si intenta usar una tecla de grabación
            if key in (
                keyboard.Key.caps_lock,
                keyboard.Key.alt,
                keyboard.Key.alt_l,
                keyboard.Key.alt_r,
            ):
                sounds.play_error()
            return

        # — CapsLock: PTT —
        if key == keyboard.Key.caps_lock:
            if not state.ptt_active:
                state.ptt_active = True
                sounds.play_start()
                overlay.show_ptt()

        # — Modificadores para Alt+Shift —
        if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
            _active_modifiers.add("alt")
        if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            _active_modifiers.add("shift")

        # — Alt+Shift: toggle —
        if "alt" in _active_modifiers and "shift" in _active_modifiers:
            if not _toggle_lock:
                _toggle_lock = True
                state.toggle_active = not state.toggle_active
                if state.toggle_active:
                    sounds.play_start()
                    overlay.show_toggle()
                    logger.info("Toggle ON")
                else:
                    state.audio_queue.put(None)
                    sounds.play_stop()
                    overlay.hide()
                    logger.info("Toggle OFF")

    def on_release(key):
        global _toggle_lock

        # — CapsLock: fin PTT —
        if key == keyboard.Key.caps_lock and state.ptt_active:
            state.ptt_active = False
            state.audio_queue.put(None)
            sounds.play_stop()
            overlay.hide()

        # — Limpiar modificadores —
        if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
            _active_modifiers.discard("alt")
            _toggle_lock = False
        if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            _active_modifiers.discard("shift")

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    return listener
