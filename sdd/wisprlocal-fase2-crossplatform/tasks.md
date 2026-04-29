# Tasks: WisprLocal Fase 2 — Cross-Platform

## Phase 1: Infraestructura (Platform)

| # | Archivo(s) | Descripción | Criterio de aceptación | Esfuerzo |
|---|------------|-------------|------------------------|----------|
| 1.1 | `wispr/platform/__init__.py` | Factory `get_platform()` que detecta OS y retorna instancia concreta. | Devuelve la implementación correcta según `sys.platform`. Sin dependencias circulares. | small |
| 1.2 | `wispr/platform/base.py` | `BasePlatform(ABC)` con 6 métodos abstractos. | Todos los métodos definidos con tipado; sin implementación por defecto. | small |
| 1.3 | `wispr/platform/windows.py` | `WindowsPlatform`: `winsound`, Ctrl+V, NVIDIA, `.vbs`. | Paridad 100% Fase 1: beep, paste, GPU CUDA/CPU, autostart funcional. | medium |
| 1.4 | `wispr/platform/linux.py` | `LinuxPlatform`: `beep`/fallback, Ctrl+V, systemd + `run.sh`. | Beep funcional. Genera `run.sh` y servicio en `~/.config/systemd/user/`. | medium |
| 1.5 | `wispr/platform/macos.py` | `MacPlatform`: `osascript`/fallback, Cmd+V, launchd + `run.sh`, MPS. | Beep funcional. Genera `run.sh` y plist en `~/Library/LaunchAgents/`. GPU retorna `("mps","float16")` cuando aplica. | medium |

## Phase 2: Refactor módulos existentes

| # | Archivo(s) | Descripción | Criterio de aceptación | Esfuerzo |
|---|------------|-------------|------------------------|----------|
| 2.1 | `wispr/sounds.py` | Delegar `_beep()` a `platform.play_beep()`. | Sin imports directos a `winsound`. Mismo comportamiento en Windows; fallback automático en Linux/macOS. | small |
| 2.2 | `wispr/injection.py` | Usar `platform.get_paste_shortcut()`; mapear strings a `kb.Key`. | Devuelve `("ctrl","v")` o `("command","v")`. Sin hardcode de teclas. | small |
| 2.3 | `wispr/config.py` | `detect_optimal_model()` usa `platform.detect_gpu()`; acepta `"mps"`. | VRAM: CUDA vía `torch.cuda`, MPS vía `psutil`, CPU vía `psutil.virtual_memory()`. | medium |
| 2.4 | `install.py` | Delegar paths, GPU, autostart, venv a plataforma. | Un entry point para los 3 OS. Genera artefactos correctos sin lógica dispersa. | medium |
| 2.5 | `wispr/tray.py` | Wrap `icon.run()` en `try/except`; modo headless si falla. | Si falla tray, la app sigue transcribiendo. Log warning claro. | small |
| 2.6 | `wispr/hotkeys.py` | Detectar `XDG_SESSION_TYPE==wayland`; log warning. | Warning visible en logs en Wayland. No bloquea arranque. | small |
| 2.7 | `wispr/__main__.py` | Si macOS + primer arranque, log warning Accessibility. | Detecta primer arranque. Mensaje instructivo una sola vez. | small |

## Notas de orden

1. Completar **Phase 1** antes de iniciar Phase 2: los refactors dependen de la plataforma ya existente.
2. Dentro de Phase 1, el orden es: `base.py` → `__init__.py` → implementaciones OS (`windows` → `linux` → `macos`).
3. Dentro de Phase 2, los refactors son independientes entre sí y pueden ejecutarse en paralelo.
