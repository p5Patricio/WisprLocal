"""Instalador de WisprLocal.

Uso: python install.py
Requiere: Python 3.12+, Windows, GPU NVIDIA (opcional pero recomendado).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

HERE = Path(__file__).parent.resolve()
VENV_DIR = HERE / ".venv"
PYTHON = VENV_DIR / "Scripts" / "python.exe"
PIP = VENV_DIR / "Scripts" / "pip.exe"
REQUIREMENTS = HERE / "requirements.txt"
LAUNCHER_VBS = HERE / "lanzador.vbs"
STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"

TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu121"


def step(n: int, total: int, msg: str) -> None:
    print(f"\n[{n}/{total}] {msg}")


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def warn(msg: str) -> None:
    print(f"  AVISO  {msg}")


def fail(msg: str) -> None:
    print(f"\n  ERROR: {msg}")
    sys.exit(1)


# ── 1. Verificar Python ────────────────────────────────────────────────────────

def check_python() -> None:
    step(1, 5, "Verificando Python...")
    v = sys.version_info
    if v < (3, 12):
        fail(
            f"Se requiere Python 3.12 o superior. Tenés Python {v.major}.{v.minor}.\n"
            "  Descargá la versión correcta desde https://www.python.org/downloads/"
        )
    ok(f"Python {v.major}.{v.minor}.{v.micro}")


# ── 2. Detectar GPU ───────────────────────────────────────────────────────────

def detect_gpu() -> bool:
    """Retorna True si nvidia-smi detecta al menos una GPU."""
    step(2, 5, "Detectando GPU NVIDIA...")
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi is None:
        warn("nvidia-smi no encontrado. Se instalará PyTorch CPU-only.")
        warn("La transcripción funcionará pero será más lenta.")
        return False
    try:
        result = subprocess.run(
            [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            gpu_name = result.stdout.strip().splitlines()[0]
            ok(f"GPU detectada: {gpu_name}")
            return True
        warn("nvidia-smi no reportó ninguna GPU. Usando CPU.")
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        warn("No se pudo consultar nvidia-smi. Usando CPU.")
        return False


# ── 3. Crear entorno virtual ──────────────────────────────────────────────────

def create_venv() -> None:
    step(3, 5, "Creando entorno virtual...")
    if VENV_DIR.exists():
        warn(f".venv ya existe en {VENV_DIR}. Se reutilizará.")
        ok("Entorno virtual existente")
        return
    venv.create(str(VENV_DIR), with_pip=True)
    ok(f"Entorno virtual creado en {VENV_DIR}")


# ── 4. Instalar dependencias ──────────────────────────────────────────────────

def install_deps(has_gpu: bool) -> None:
    step(4, 5, "Instalando dependencias...")

    def run_pip(*args: str) -> None:
        cmd = [str(PYTHON), "-m", "pip", *args]
        result = subprocess.run(cmd, capture_output=False)
        if result.returncode != 0:
            fail(f"pip falló con código {result.returncode}. Revisá el output de arriba.")

    run_pip("install", "--upgrade", "pip", "--quiet")
    ok("pip actualizado")

    torch_index = TORCH_CUDA_INDEX if has_gpu else TORCH_CPU_INDEX
    print(f"  Instalando PyTorch desde {torch_index} (puede tardar varios minutos)...")
    run_pip(
        "install",
        "torch",
        "--index-url", torch_index,
        "--quiet",
    )
    ok("PyTorch instalado")

    print("  Instalando dependencias del proyecto...")
    run_pip("install", "-r", str(REQUIREMENTS), "--quiet")
    ok("Dependencias instaladas")


# ── 5. Generar lanzador ───────────────────────────────────────────────────────

def generate_launcher() -> None:
    step(5, 5, "Generando lanzador...")
    pythonw = VENV_DIR / "Scripts" / "pythonw.exe"
    if not pythonw.exists():
        warn(f"pythonw.exe no encontrado en {pythonw}. El lanzador puede no funcionar.")

    # VBS usa "" para escapar comillas — el Run necesita la ruta entre comillas dobles
    lines = [
        "' WisprLocal — Lanzador sin ventana de consola",
        "' Generado por install.py — no editar manualmente.",
        'Set WshShell = CreateObject("WScript.Shell")',
        f'WshShell.CurrentDirectory = "{HERE}"',
        f'WshShell.Run """{pythonw}""" & " -m wispr", 0, False',
        "Set WshShell = Nothing",
    ]
    content = "\n".join(lines) + "\n"
    LAUNCHER_VBS.write_text(content, encoding="utf-8")
    ok(f"lanzador.vbs generado en {LAUNCHER_VBS}")

    answer = input("\n  ¿Querés que WisprLocal inicie automáticamente con Windows? [s/N] ").strip().lower()
    if answer in ("s", "si", "sí", "y", "yes"):
        startup_dest = STARTUP_DIR / "WisprLocal.vbs"
        try:
            STARTUP_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(LAUNCHER_VBS, startup_dest)
            ok(f"Copiado a Inicio automático: {startup_dest}")
        except Exception as exc:
            warn(f"No se pudo copiar a Inicio automático: {exc}")
    else:
        ok("Inicio automático omitido")


# ── Resumen ───────────────────────────────────────────────────────────────────

def print_summary() -> None:
    print("\n" + "=" * 60)
    print("  WisprLocal instalado correctamente")
    print("=" * 60)
    print(f"  Proyecto:     {HERE}")
    print(f"  Entorno:      {VENV_DIR}")
    print(f"  Lanzador:     {LAUNCHER_VBS}")
    print()
    print("  Para iniciar WisprLocal:")
    print("    Doble clic en lanzador.vbs")
    print()
    print("  Para iniciar desde terminal:")
    print(f"    {PYTHON} -m wispr")
    print("=" * 60 + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("\nWisprLocal — Instalador")
    print("=" * 60)

    check_python()
    has_gpu = detect_gpu()
    create_venv()
    install_deps(has_gpu)
    generate_launcher()
    print_summary()


if __name__ == "__main__":
    main()
