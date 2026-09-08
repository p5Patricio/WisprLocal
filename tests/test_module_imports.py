"""Todo módulo de la aplicación debe al menos compilar e importarse.

settings_gui.py estuvo con un error de sintaxis desde el 2026-08-15 y salió así
en v1.2.0 y v1.3.0: la ventana de configuración fallaba al abrirse y la suite
quedaba verde porque ningún test importaba ese módulo.
"""

from __future__ import annotations

import ast
import importlib
import pathlib

import pytest

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "whisperkey"
MODULES = sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in str(p))


@pytest.mark.parametrize("path", MODULES, ids=lambda p: str(p.name))
def test_module_parses(path: pathlib.Path) -> None:
    """Detecta errores de sintaxis aunque nada más importe el módulo."""
    source = path.read_text(encoding="utf-8")
    try:
        ast.parse(source, filename=str(path))
    except SyntaxError as exc:  # pragma: no cover - el mensaje es el valor
        pytest.fail(f"{path.name} no compila: {exc.msg} (línea {exc.lineno})")


IMPORTABLES = [
    "whisperkey.audio",
    "whisperkey.config",
    "whisperkey.engine",
    "whisperkey.errors",
    "whisperkey.history",
    "whisperkey.hotkeys",
    "whisperkey.injection",
    "whisperkey.onboarding",
    "whisperkey.overlay",
    "whisperkey.settings_gui",
    "whisperkey.sounds",
    "whisperkey.splash",
    "whisperkey.state",
    "whisperkey.theme",
    "whisperkey.transcription",
    "whisperkey.tray",
    "whisperkey.updater",
    "whisperkey.version",
]


@pytest.mark.parametrize("name", IMPORTABLES)
def test_module_imports(name: str) -> None:
    importlib.import_module(name)


def test_settings_window_builds() -> None:
    """La ventana de configuración debe construirse de verdad, no sólo importar.

    El error de sintaxis de settings_gui.py sobrevivió tres semanas porque nada
    lo importaba; mezclar pack y grid en un mismo contenedor tampoco lo detecta
    un import. Esto ejerce la construcción completa de las seis pestañas.
    """
    ctk = pytest.importorskip("customtkinter")
    tk = pytest.importorskip("tkinter")
    from whisperkey import config as config_module, theme
    from whisperkey.settings_gui import SettingsGUI

    try:
        theme.apply()
        root = ctk.CTk()
    except tk.TclError:  # pragma: no cover - entorno sin display
        pytest.skip("sin display disponible")

    root.withdraw()
    try:
        gui = SettingsGUI(master=root, config=config_module._deep_merge(config_module.DEFAULTS, {}))
        assert gui._window.winfo_exists()
        for pestana in ("Modelo", "Audio", "Hotkeys", "Overlay", "Historial", "Sistema"):
            assert gui._tabview.tab(pestana) is not None
    finally:
        root.destroy()


def test_onboarding_wizard_builds() -> None:
    """Mismo contrato para el asistente de primer uso."""
    ctk = pytest.importorskip("customtkinter")
    tk = pytest.importorskip("tkinter")
    from whisperkey import theme
    from whisperkey.onboarding import OnboardingWizard

    try:
        theme.apply()
        root = ctk.CTk()
    except tk.TclError:  # pragma: no cover - entorno sin display
        pytest.skip("sin display disponible")

    root.withdraw()
    try:
        wizard = OnboardingWizard(master=root)
        assert wizard._window.winfo_exists()
    finally:
        root.destroy()
