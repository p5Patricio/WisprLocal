"""Feedback auditivo via winsound. Cada función lanza un daemon thread."""

import threading
import winsound


def _beep(freq: int, duration: int) -> None:
    winsound.Beep(freq, duration)


def play_start() -> None:
    """1200Hz / 100ms — inicio de grabación."""
    threading.Thread(target=_beep, args=(1200, 100), daemon=True).start()


def play_stop() -> None:
    """800Hz / 100ms — fin de grabación."""
    threading.Thread(target=_beep, args=(800, 100), daemon=True).start()


def play_ready() -> None:
    """1000Hz/80ms + 1200Hz/80ms — modelo listo."""

    def _double():
        winsound.Beep(1000, 80)
        winsound.Beep(1200, 80)

    threading.Thread(target=_double, daemon=True).start()


def play_error() -> None:
    """400Hz / 300ms — error."""
    threading.Thread(target=_beep, args=(400, 300), daemon=True).start()
