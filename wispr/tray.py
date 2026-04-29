"""Icono de bandeja del sistema via pystray."""

from __future__ import annotations

import logging
from typing import Callable

from PIL import Image, ImageDraw

from wispr.state import AppState

logger = logging.getLogger(__name__)


def _create_image(color: str) -> Image.Image:
    image = Image.new("RGB", (64, 64), color)
    d = ImageDraw.Draw(image)
    d.rectangle([16, 16, 48, 48], fill="white")
    return image


def _update_tray_icon(icon, state: AppState) -> None:
    if state.get_loading():
        icon.icon = _create_image("yellow")
        icon.title = "WisprLocal \u2014 Cargando modelo..."
    elif state.model is not None:
        icon.icon = _create_image("green")
        icon.title = "WisprLocal \u2014 Listo | PTT: CapsLock"
    else:
        icon.icon = _create_image("gray")
        icon.title = "WisprLocal \u2014 Sin modelo (clic derecho para cargar)"


def start_tray(
    state: AppState,
    config: dict,  # noqa: ARG001 — reservado para configuración en Fase 2
    on_load: Callable[[], None],
    on_unload: Callable[[], None],
    on_quit: Callable[[object], None],
) -> None:
    """Crea el icono de bandeja y bloquea el main thread hasta que se cierra."""

    import pystray

    icon = pystray.Icon("Wispr", _create_image("gray"), "WisprLocal \u2014 Sin modelo (clic derecho para cargar)")

    def _load(_icon, _item):
        on_load()
        _update_tray_icon(icon, state)

    def _unload(_icon, _item):
        on_unload()
        _update_tray_icon(icon, state)

    def _quit(_icon, _item):
        state.shutdown_event.set()
        on_quit(_icon)

    icon.menu = pystray.Menu(
        pystray.MenuItem("Cargar modelo", _load),
        pystray.MenuItem("Descargar modelo", _unload),
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
