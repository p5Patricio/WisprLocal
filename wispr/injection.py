"""Inyección de texto via pyperclip + Ctrl+V."""

import time

import pyperclip
from pynput import keyboard


def inject_text(text: str, pre_delay_ms: int = 150, post_delay_ms: int = 400) -> None:
    """Inyecta *text* en la aplicación activa via clipboard + Ctrl+V.

    1. No-op si *text* es vacío.
    2. Copia *text* al clipboard.
    3. Espera *pre_delay_ms* ms para que el clipboard se registre.
    4. Envía Ctrl+V via pynput.
    5. Espera *post_delay_ms* ms para que la app procese el paste antes de continuar.
    El texto queda en el clipboard para que el usuario pueda pegarlo manualmente si lo desea.
    """
    if not text:
        return

    pyperclip.copy(text)
    time.sleep(pre_delay_ms / 1000)

    controller = keyboard.Controller()
    with controller.pressed(keyboard.Key.ctrl):
        controller.press("v")
        controller.release("v")

    time.sleep(post_delay_ms / 1000)
