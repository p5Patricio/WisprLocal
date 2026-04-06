"""Icono de bandeja del sistema via pystray."""

from __future__ import annotations

import logging
from typing import Callable

import pystray
from PIL import Image, ImageDraw

from wispr.state import AppState

logger = logging.getLogger(__name__)


def _create_image(color: str) -> Image.Image:
    image = Image.new("RGB", (64, 64), color)
    d = ImageDraw.Draw(image)
    d.rectangle([16, 16, 48, 48], fill="white")
    return image


def _update_tray_icon(icon: pystray.Icon, state: AppState) -> None:
    if state.model is not None:
        icon.icon = _create_image("green")
        icon.title = "Wispr Local - Listo"
    else:
        icon.icon = _create_image("gray")
        icon.title = "Wispr Local - Sin modelo (VRAM libre)"


def start_tray(
    state: AppState,
    config: dict,  # noqa: ARG001 — reservado para configuración en Fase 2
    on_load: Callable[[], None],
    on_unload: Callable[[], None],
    on_quit: Callable[[pystray.Icon], None],
) -> None:
    """Crea el icono de bandeja y bloquea el main thread hasta que se cierra."""

    icon = pystray.Icon("Wispr", _create_image("gray"), "Wispr Local - Sin modelo")

    def _load(_icon, _item):
        on_load()
        _update_tray_icon(icon, state)

    def _unload(_icon, _item):
        on_unload()
        _update_tray_icon(icon, state)

    def _quit(_icon, _item):
        on_quit(_icon)

    icon.menu = pystray.Menu(
        pystray.MenuItem("Cargar modelo", _load),
        pystray.MenuItem("Descargar modelo", _unload),
        pystray.MenuItem("Salir", _quit),
    )

    logger.info("Tray iniciado.")
    icon.run()
