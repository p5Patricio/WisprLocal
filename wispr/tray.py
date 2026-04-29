"""Icono de bandeja del sistema via pystray."""

from __future__ import annotations

import logging
import pathlib
import threading
import tkinter as tk
from typing import Callable

from PIL import Image, ImageDraw

from wispr.state import AppState

logger = logging.getLogger(__name__)

_ASSETS_DIR = pathlib.Path(__file__).parent.parent / "assets" / "icons"


def _load_icon(name: str, fallback_color: str) -> Image.Image:
    """Carga un ícono desde *assets/icons/* o genera un cuadrado de fallback."""
    path = _ASSETS_DIR / name
    if path.exists():
        return Image.open(path).convert("RGBA")
    image = Image.new("RGB", (64, 64), fallback_color)
    d = ImageDraw.Draw(image)
    d.rectangle([16, 16, 48, 48], fill="white")
    return image


def _update_tray_icon(icon, state: AppState) -> None:
    if state.get_loading():
        icon.icon = _load_icon("tray_loading.png", "yellow")
        icon.title = "WisprLocal \u2014 Cargando modelo..."
    elif state.model is not None:
        icon.icon = _load_icon("tray_ready.png", "green")
        icon.title = "WisprLocal \u2014 Listo | PTT: CapsLock"
    else:
        icon.icon = _load_icon("tray_idle.png", "gray")
        icon.title = "WisprLocal \u2014 Sin modelo (clic derecho para cargar)"


def start_tray(
    state: AppState,
    config: dict,
    on_load: Callable[[], None],
    on_unload: Callable[[], None],
    on_quit: Callable[[object], None],
    master: tk.Tk | None = None,
) -> None:
    """Crea el icono de bandeja y lo ejecuta. NO bloquea — debe llamarse desde un thread daemon."""

    import pystray

    icon = pystray.Icon(
        "Wispr",
        _load_icon("tray_idle.png", "gray"),
        "WisprLocal \u2014 Sin modelo (clic derecho para cargar)",
    )

    def _load(_icon, _item):
        on_load()
        _update_tray_icon(icon, state)

    def _unload(_icon, _item):
        on_unload()
        _update_tray_icon(icon, state)

    def _quit(_icon, _item):
        state.shutdown_event.set()
        on_quit(_icon)

    def _settings(_icon, _item):
        if master is not None:
            master.after(0, _open_settings)

    def _open_settings() -> None:
        try:
            from wispr.settings_gui import SettingsGUI
            SettingsGUI(master=master, config=config)
        except Exception as exc:
            logger.warning("No se pudo abrir SettingsGUI: %s", exc)

    icon.menu = pystray.Menu(
        pystray.MenuItem("Cargar modelo", _load),
        pystray.MenuItem("Descargar modelo", _unload),
        pystray.MenuItem("Configuración", _settings),
        pystray.MenuItem("Salir", _quit),
    )

    logger.info("Tray iniciado.")
    try:
        icon.run()
    except Exception as exc:
        logger.warning(
            "No se pudo iniciar el icono de bandeja: %s. Continuando sin tray...",
            exc,
        )
        state.shutdown_event.wait()
