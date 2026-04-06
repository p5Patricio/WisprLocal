"""Inyección de texto via pyperclip + Ctrl+V."""

import time

import pyperclip
from pynput import keyboard


def inject_text(text: str, delay_ms: int = 100) -> None:
    """Inyecta *text* en la aplicación activa via clipboard + Ctrl+V.

    1. No-op si *text* es vacío.
    2. Guarda el clipboard previo.
    3. Copia *text* al clipboard.
    4. Espera *delay_ms* ms para que la app procese el foco.
    5. Envía Ctrl+V via pynput.
    6. Restaura el clipboard previo.
    """
    if not text:
        return

    try:
        previous = pyperclip.paste()
    except Exception:
        previous = ""

    try:
        pyperclip.copy(text)
        time.sleep(delay_ms / 1000)
        controller = keyboard.Controller()
        with controller.pressed(keyboard.Key.ctrl):
            controller.press("v")
            controller.release("v")
    finally:
        try:
            pyperclip.copy(previous)
        except Exception:
            pass
