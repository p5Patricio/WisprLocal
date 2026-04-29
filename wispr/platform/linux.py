"""Implementación de BasePlatform para Linux."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from wispr.platform.base import BasePlatform

log = logging.getLogger(__name__)


class LinuxPlatform(BasePlatform):
    """Plataforma Linux: beep, Ctrl+V, systemd service + run.sh."""

    def play_beep(self, freq: int, duration: float) -> None:
        try:
            os.system(f"beep -f {freq} -l {int(duration * 1000)}")
        except Exception:
            print("\a")

    def get_paste_shortcut(self) -> tuple[str, str]:
        return ("ctrl", "v")

    def detect_gpu(self) -> tuple[str, str]:
        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi is not None:
            try:
                result = subprocess.run(
                    [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return ("cuda", "int8_float16")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        return ("cpu", "int8")

    def get_project_root(self) -> Path:
        return Path(__file__).parent.parent.parent.resolve()

    def get_venv_python(self) -> Path:
        return self.get_project_root() / ".venv" / "bin" / "python"

    def generate_launcher(self) -> None:
        """Generar run.sh en la raíz del proyecto."""
        here = self.get_project_root()
        python = self.get_venv_python()
        run_sh = here / "run.sh"

        lines = [
            "#!/bin/bash",
            "# WisprLocal — Lanzador",
            "# Generado por install.py — no editar manualmente.",
            f"cd '{here}'",
            f"nohup '{python}' -m wispr >/dev/null 2>&1 &",
            "echo $! > wisprlocal.pid",
        ]
        content = "\n".join(lines) + "\n"
        run_sh.write_text(content, encoding="utf-8")
        run_sh.chmod(0o755)
        log.info("run.sh generado en %s", run_sh)

    def _generate_desktop_file(self) -> None:
        """Generar archivo .desktop para lanzador gráfico en Linux."""
        here = self.get_project_root()
        python = self.get_venv_python()
        apps_dir = Path.home() / ".local" / "share" / "applications"
        apps_dir.mkdir(parents=True, exist_ok=True)
        desktop_path = apps_dir / "wisprlocal.desktop"

        content = f"""\
[Desktop Entry]
Name=WisprLocal
Comment=Dictado por voz local con Whisper
Exec={python} -m wispr
Icon={here}/wispr/icon.png
Type=Application
Terminal=false
Categories=Utility;AudioVideo;
"""
        desktop_path.write_text(content, encoding="utf-8")
        log.info("Archivo .desktop generado: %s", desktop_path)

    def setup_autostart(self) -> None:
        """Crear y habilitar servicio systemd de usuario."""
        here = self.get_project_root()
        python = self.get_venv_python()

        self._generate_desktop_file()

        service_dir = Path.home() / ".config" / "systemd" / "user"
        service_dir.mkdir(parents=True, exist_ok=True)
        service_path = service_dir / "wisprlocal.service"

        service_content = f"""\
[Unit]
Description=WisprLocal
After=graphical-session.target

[Service]
Type=simple
ExecStart={python} -m wispr
WorkingDirectory={here}
Restart=on-failure

[Install]
WantedBy=default.target
"""
        service_path.write_text(service_content, encoding="utf-8")

        try:
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["systemctl", "--user", "enable", "wisprlocal.service"],
                check=True,
                capture_output=True,
            )
            log.info("Servicio systemd habilitado: %s", service_path)
        except Exception as exc:
            log.warning("No se pudo habilitar el servicio systemd: %s", exc)
