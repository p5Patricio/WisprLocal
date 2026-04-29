"""Script de construcción con PyInstaller para WisprLocal."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DIST_DIR = PROJECT_ROOT / "dist" / "WisprLocal"


def build() -> None:
    """Ejecuta PyInstaller con los parámetros óptimos para WisprLocal."""
    sep = os.pathsep  # ; en Windows, : en Unix

    add_data = [
        f"assets{sep}assets",
        f"config.toml{sep}.",
    ]

    hidden_imports = [
        "wispr.platform.windows",
        "wispr.platform.linux",
        "wispr.platform.macos",
        "wispr.splash",
        "wispr.settings_gui",
        "wispr.onboarding",
        "wispr.updater",
    ]

    excludes = [
        "tests",
        "docs",
        "notebooks",
        "torch.testing",
        "torch.utils.benchmark",
        "torch.utils.tensorboard",
        "torch.utils.cpp_extension",
        "torch.utils.mobile_optimizer",
        "torch.utils.dlpack",
        "IPython",
        "matplotlib",
        "pytest",
    ]

    icon_path = PROJECT_ROOT / "assets" / "icons" / "app.ico"
    icon_arg = f"--icon={icon_path}" if icon_path.exists() else ""

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onedir",
        "--windowed",
        "--name=WisprLocal",
        f"--distpath={PROJECT_ROOT / 'dist'}",
        f"--workpath={PROJECT_ROOT / 'build'}",
        f"--specpath={PROJECT_ROOT}",
    ]
    if icon_arg:
        cmd.append(icon_arg)

    for data in add_data:
        cmd.append(f"--add-data={data}")

    for imp in hidden_imports:
        cmd.append(f"--hidden-import={imp}")

    for exc in excludes:
        cmd.append(f"--exclude-module={exc}")

    cmd.append(str(PROJECT_ROOT / "wispr" / "__main__.py"))

    log.info("Ejecutando: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)
    log.info("Build completado en %s", DIST_DIR)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        build()
    except subprocess.CalledProcessError as exc:
        log.error("PyInstaller falló con código %s", exc.returncode)
        sys.exit(1)
    except FileNotFoundError:
        log.error("PyInstaller no encontrado. Instalalo con: pip install pyinstaller")
        sys.exit(1)


if __name__ == "__main__":
    main()
