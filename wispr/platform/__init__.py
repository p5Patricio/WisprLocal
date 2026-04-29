"""Factory de plataforma: exporta get_platform()."""

from __future__ import annotations

import sys

from wispr.platform.base import BasePlatform

_platform_instance: BasePlatform | None = None


def get_platform() -> BasePlatform:
    """Retorna la instancia singleton de la plataforma detectada."""
    global _platform_instance
    if _platform_instance is not None:
        return _platform_instance

    if sys.platform == "win32":
        from wispr.platform.windows import WindowsPlatform

        _platform_instance = WindowsPlatform()
    elif sys.platform == "darwin":
        from wispr.platform.macos import MacPlatform

        _platform_instance = MacPlatform()
    elif sys.platform.startswith("linux"):
        from wispr.platform.linux import LinuxPlatform

        _platform_instance = LinuxPlatform()
    else:
        from wispr.errors import UnsupportedPlatformError

        raise UnsupportedPlatformError(f"Plataforma no soportada: {sys.platform}")

    return _platform_instance
