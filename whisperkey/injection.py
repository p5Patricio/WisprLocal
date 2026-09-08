"""Inyección de texto via pyperclip + atajo de plataforma."""

from __future__ import annotations

import logging
import time

import pyperclip
from pynput import keyboard

from whisperkey.errors import InjectionError
from whisperkey.platform import get_platform

log = logging.getLogger(__name__)
_CLIPBOARD_SIZE_LIMIT = 5 * 1024 * 1024

# El portapapeles se confirma sondeándolo, no esperando a ciegas. Una espera
# fija de 150 ms era el 28% de la latencia percibida de un dictado corto,
# mientras que la confirmación real suele llegar en pocos milisegundos.
_CLIPBOARD_POLL_INTERVAL_S = 0.004
_CLIPBOARD_TIMEOUT_S = 0.5
# Margen mínimo entre el paste y la restauración del portapapeles: si se
# restaura demasiado pronto, la aplicación destino pega el contenido viejo.
_RESTORE_DELAY_S = 0.12

_KEY_MAP = {
    "ctrl": keyboard.Key.ctrl,
    "command": keyboard.Key.cmd,
    "alt": keyboard.Key.alt,
    "shift": keyboard.Key.shift,
}

_platform = get_platform()


def _wait_for_clipboard(expected: str, timeout_s: float | None = None) -> bool:
    """Sondea el portapapeles hasta que contenga *expected*.

    Devuelve True si se confirmó. Pegar antes de que el portapapeles esté listo
    inserta el contenido anterior, así que la confirmación importa; lo que no
    hace falta es esperar un tiempo fijo pensado para el peor caso.
    """
    timeout_s = _CLIPBOARD_TIMEOUT_S if timeout_s is None else timeout_s
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if pyperclip.paste() == expected:
                return True
        except Exception:  # pragma: no cover - portapapeles ocupado por otra app
            pass
        time.sleep(_CLIPBOARD_POLL_INTERVAL_S)
    return False


def inject_text(text: str, restore_delay_s: float | None = None) -> None:
    """Inyecta *text* en la aplicación activa via clipboard + atajo de plataforma.

    1. No-op si *text* es vacío.
    2. Guarda el contenido previo del clipboard (si es texto y <= 5 MB).
    3. Copia *text* y espera la confirmación real del portapapeles.
    4. Envía el atajo de pegar según la plataforma via pynput.
    5. Restaura el clipboard previo tras un margen breve.
    """
    if not text:
        return

    restore_delay_s = _RESTORE_DELAY_S if restore_delay_s is None else restore_delay_s
    previous = None
    should_restore = False
    try:
        previous = pyperclip.paste()
        if previous is not None and isinstance(previous, str):
            size = len(previous.encode("utf-8"))
            should_restore = size <= _CLIPBOARD_SIZE_LIMIT
    except Exception:
        pass

    try:
        pyperclip.copy(text)
        if not _wait_for_clipboard(text):
            log.warning(
                "El portapapeles no confirmó el texto en %.0f ms; pegando igual.",
                _CLIPBOARD_TIMEOUT_S * 1000,
            )

        shortcut = _platform.get_paste_shortcut()
        modifier = _KEY_MAP[shortcut[0]]
        char_key = shortcut[1]

        controller = keyboard.Controller()
        with controller.pressed(modifier):
            controller.press(char_key)
            controller.release(char_key)

        if should_restore:
            time.sleep(restore_delay_s)
    except Exception as exc:
        raise InjectionError(f"Fallo al inyectar texto: {exc}") from exc
    finally:
        if should_restore:
            try:
                pyperclip.copy(previous)
            except Exception:
                pass
