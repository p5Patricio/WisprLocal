# Design: WisprLocal Fase 2 — Cross-Platform

## Technical Approach

Crear `wispr/platform/` con factory OOP que aisla hacks OS-specific. Los módulos existentes importan `get_platform()` y delegan. Paridad 100% Windows respecto a Fase 1.

## Architecture Decisions

| Decision | Chosen | Rejected | Rationale |
|----------|--------|----------|-----------|
| Abstraction style | Factory OOP (ABC + 3 impls) | `if/elif` disperso | 11 módulos; centralizar reduce deuda técnica y facilita nuevas plataformas |
| Beep Linux | `os.system("beep -f F -l D")` → fallback `print('''\a''')` | `simpleaudio` (nueva dep) | Cero dependencias nuevas; acceptable para feedback simple |
| Beep macOS | `osascript -e ''"'"'beep'"'"'` → fallback `print('''\a''')` | `pyobjc` (nueva dep) | Cero dependencias nuevas |
| GPU detection | Jerarquía centralizada en plataforma | Lógica inline en `config.py` | Un solo lugar de verdad; fácil extender a ROCm |
| Install refactor | `install.py` delega a métodos de plataforma | 3 scripts de install separados | Un entry point; comportamiento encapsulado |
| Paste shortcut | Strings resueltas por `injection.py` | Retornar objetos `pynput.Key` | Evita acoplar `platform/` a `pynput` |

## Data Flow

```
wispr/__main__.py ──► get_platform() ──► WindowsPlatform | LinuxPlatform | MacPlatform
     │
     ▼
sounds.py     ──► platform.play_beep(freq, duration)
injection.py  ──► platform.get_paste_shortcut() ──► ("ctrl","v") | ("command","v")
config.py     ──► platform.detect_gpu()          ──► (device, compute_type)
install.py    ──► platform.setup_autostart()
                ──► platform.get_venv_python() / get_project_root()
tray.py       ──► try/except icon.run() ──► modo headless si falla
hotkeys.py    ──► detecta Wayland ──► warning log
```

## GPU Detection Hierarchy

1. **macOS + MPS** → `("mps", "float16")` — MPS no soporta `int8` en todas las ops
2. **CUDA disponible** → `("cuda", "int8_float16")` — incluye ROCm en Linux (expuesto como CUDA por PyTorch)
3. **Fallback** → `("cpu", "int8")`

En `config.py`, `detect_optimal_model()` lee el device del platform y ajusta VRAM: CUDA vía `torch.cuda`, MPS vía `psutil` (unified memory), CPU vía `psutil.virtual_memory()`.

## Installation Artifacts

| OS | Archivos generados | Ubicación |
|----|-------------------|-----------|
| Windows | `lanzador.vbs` | `./lanzador.vbs` (existente, sin cambios de formato) |
| Linux | `run.sh` + `wisprlocal.service` | `./run.sh` + `~/.config/systemd/user/wisprlocal.service` |
| macOS | `run.sh` + `com.wisprlocal.plist` | `./run.sh` + `~/Library/LaunchAgents/com.wisprlocal.plist` |

Scripts `run.sh` usan `nohup` para background; servicios usan `ExecStart` con `.venv/bin/python -m wispr`.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `wispr/platform/__init__.py` | Create | Exporta `get_platform()` factory |
| `wispr/platform/base.py` | Create | `BasePlatform(ABC)` — 6 métodos abstractos |
| `wispr/platform/windows.py` | Create | `WindowsPlatform` — winsound, Ctrl+V, nvidia-smi, .vbs |
| `wispr/platform/linux.py` | Create | `LinuxPlatform` — beep, Ctrl+V, systemd service + run.sh |
| `wispr/platform/macos.py` | Create | `MacPlatform` — osascript, Cmd+V, launchd plist + run.sh |
| `wispr/sounds.py` | Modify | Importa `get_platform()`; delega `_beep()` a `platform.play_beep()` |
| `wispr/injection.py` | Modify | Usa `platform.get_paste_shortcut()`; mapea strings a `kb.Key` |
| `wispr/config.py` | Modify | `detect_optimal_model` usa `platform.detect_gpu()`; validación acepta `"mps"` |
| `install.py` | Modify | Delega paths, GPU detect, autostart, venv path a platform |
| `wispr/tray.py` | Modify | Wrap `icon.run()` en try/except; log warning y continúa sin tray |
| `wispr/hotkeys.py` | Modify | Detecta `XDG_SESSION_TYPE==wayland` → log warning |
| `wispr/__main__.py` | Modify | Si macOS + primer arranque → log warning Accessibility |
| `requirements.txt` | Modify | Notas condicionales de índices PyTorch por OS |

## Interfaces / Contracts

```python
# wispr/platform/base.py
class BasePlatform(ABC):
    @abstractmethod
    def play_beep(self, freq: int, duration: float) -> None: ...
    @abstractmethod
    def get_paste_shortcut(self) -> tuple[str, str]: ...
    @abstractmethod
    def detect_gpu(self) -> tuple[str, str]: ...
    @abstractmethod
    def setup_autostart(self) -> None: ...
    @abstractmethod
    def get_venv_python(self) -> Path: ...
    @abstractmethod
    def get_project_root(self) -> Path: ...

# wispr/platform/__init__.py
def get_platform() -> BasePlatform: ...
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Manual | Windows parity | Comparar Fase 1 vs Fase 2: beep, inyección, tray idénticos |
| Manual | Linux X11 | Beep, Ctrl+V, hotkeys, systemd service funcional |
| Manual | Linux Wayland | Arranca, transcribe, inyecta; hotkeys documentados como no soportados |
| Manual | macOS | Cmd+V, MPS/CPU, Accessibility warning, launchd load |

## Migration / Rollout

- Git tag `pre-fase2` antes del primer commit de refactor.
- Sin breaking changes en `config.toml` existente.
- `install.py` legacy respaldado en git history.

## Open Questions

- [ ] ¿ROCm Linux AMD merece índice de PyTorch propio en `install.py`, o se documenta en README?
- [ ] ¿Wayland: implementar backend `evdev` experimental o dejar para Fase 3?
