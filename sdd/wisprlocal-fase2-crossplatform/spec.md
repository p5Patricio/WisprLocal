# Especificacion Tecnica: WisprLocal Fase 2 - Cross-Platform

---

## 1. platform-abstraction

### Proposito
Proveer una capa de abstraccion OOP que aisle todos los detalles especificos de plataforma (Windows, Linux, macOS) en un unico paquete `wispr/platform/`.

### Requerimientos

#### REQ-PA-001: BasePlatform ABC
El sistema **DEBE** exponer una clase abstracta `BasePlatform` (ABC) que defina la interfaz comun para todas las plataformas.

#### REQ-PA-002: Factory de deteccion
El sistema **DEBE** proveer `get_platform() -> BasePlatform` que detecte el SO en tiempo de ejecucion y retorne la implementacion concreta correspondiente.

#### REQ-PA-003: Cacheo de instancia
El sistema **DEBERIA** cachear la instancia de plataforma para evitar re-deteccion en cada llamada.

#### REQ-PA-004: Extensibilidad
El sistema **DEBE** permitir agregar nuevas plataformas mediante una nueva clase que herede de `BasePlatform` sin modificar la factory.

### Escenarios

#### Scenario: Inicializacion en Windows
- **GIVEN** que el sistema corre en `sys.platform == "win32"`
- **WHEN** se invoca `get_platform()`
- **THEN** retorna una instancia de `WindowsPlatform`
- **AND** la instancia es subclase de `BasePlatform`

#### Scenario: Inicializacion en Linux
- **GIVEN** que el sistema corre en `sys.platform.startswith("linux")`
- **WHEN** se invoca `get_platform()`
- **THEN** retorna una instancia de `LinuxPlatform`

#### Scenario: Inicializacion en macOS
- **GIVEN** que el sistema corre en `sys.platform == "darwin"`
- **WHEN** se invoca `get_platform()`
- **THEN** retorna una instancia de `macOSPlatform`

#### Scenario: Plataforma desconocida
- **GIVEN** que el sistema corre en un `sys.platform` no soportado
- **WHEN** se invoca `get_platform()`
- **THEN** lanza `UnsupportedPlatformError`
- **AND** el mensaje de error incluye el nombre de la plataforma detectada

### Interfaces

```python
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Tuple, Optional

class BasePlatform(ABC):
    @abstractmethod
    def play_beep(self, frequency: int = 800, duration: int = 200) -> None: ...

    @abstractmethod
    def get_paste_shortcut(self) -> Tuple[str, str]: ...

    @abstractmethod
    def detect_gpu(self) -> Tuple[str, str]: ...
    # Retorna (device_name, compute_type)

    @abstractmethod
    def get_venv_python_path(self) -> Path: ...

    @abstractmethod
    def setup_autostart(self, project_root: Path) -> None: ...

    @abstractmethod
    def get_paste_modifiers(self) -> list: ...
    # Retorna lista de keys pynput (ej: [Key.ctrl])

    def has_system_tray(self) -> bool:
        # Default True; Linux puede sobreescribir
        return True

def get_platform() -> BasePlatform: ...
```

### Manejo de Errores

| Error | Condicion | Accion |
|-------|-----------|--------|
| `UnsupportedPlatformError` | `sys.platform` no en {win32, linux, darwin} | Loggear critical; propagar excepcion |

### Notas por Plataforma

- **Windows**: `winsound` solo existe en Windows; la implementacion puede importarlo localmente.
- **Linux**: debe detectar si es headless via `$DISPLAY` o `$WAYLAND_DISPLAY`.
- **macOS**: debe detectar si es Apple Silicon vs Intel para MPS.

---

## 2. cross-platform-sounds

### Proposito
Reemplazar `winsound.Beep()` con un mecanismo de audio feedback que funcione en Windows, Linux y macOS sin bloquear el hilo principal.

### Requerimientos

#### REQ-SND-001: play_beep cross-platform
El sistema **DEBE** proveer `play_beep(frequency: int, duration: int)` a traves de `BasePlatform`.

#### REQ-SND-002: No bloqueante
El sistema **NO DEBE** bloquear el hilo principal durante la reproduccion del beep.

#### REQ-SND-003: Fallback silencioso
El sistema **DEBERIA** tener un fallback silencioso si ningun backend de audio esta disponible.

### Escenarios

#### Scenario: Beep en Windows
- **GIVEN** que la plataforma es Windows
- **WHEN** se invoca `platform.play_beep(800, 200)`
- **THEN** emite un tono de 800 Hz durante 200 ms via `winsound.Beep()`
- **AND** se ejecuta en un thread daemon

#### Scenario: Beep en Linux con `beep` instalado
- **GIVEN** que la plataforma es Linux y el comando `beep` esta disponible
- **WHEN** se invoca `platform.play_beep(800, 200)`
- **THEN** ejecuta `beep -f 800 -l 200` via subprocess

#### Scenario: Beep en Linux sin `beep`
- **GIVEN** que la plataforma es Linux y `beep` no esta instalado
- **WHEN** se invoca `platform.play_beep()`
- **THEN** emite `\a` (bell) o es silencioso
- **AND** logea un warning de fallback

#### Scenario: Beep en macOS
- **GIVEN** que la plataforma es macOS
- **WHEN** se invoca `platform.play_beep()`
- **THEN** ejecuta `osascript -e 'beep'` o usa `AppKit.NSBeep()` si pyobjc esta disponible

### Interfaces

```python
def play_beep(self, frequency: int = 800, duration: int = 200) -> None:
    """Emite un tono o beep del sistema. No bloquea."""
```

### Manejo de Errores

| Error | Condicion | Accion |
|-------|-----------|--------|
| `OSError` (Linux) | `beep` no instalado | Fallback a `print('\a')`; log warning |
| `ImportError` (macOS) | `pyobjc` no instalado | Fallback a `osascript` o silencio |
| Any exception | Backend falla | Silenciar y loggear; no propagar |

### Notas por Plataforma

- **Windows**: `winsound.Beep` requiere una consola en algunas versiones; si falla, usar `MessageBeep` como fallback.
- **Linux headless**: `beep` puede requerir modulo `pcspkr` del kernel.
- **macOS**: `NSBeep()` no permite control de frecuencia/duracion; es un beep estandar del sistema.

---

## 3. cross-platform-injection

### Proposito
Garantizar que el atajo de teclado para pegar texto (`Ctrl+V` vs `Cmd+V`) sea el correcto segun la plataforma.

### Requerimientos

#### REQ-INJ-001: Atajo correcto por plataforma
El sistema **DEBE** enviar `Ctrl+V` en Windows y Linux, y `Cmd+V` en macOS.

#### REQ-INJ-002: Abstraccion via plataforma
El sistema **DEBE** obtener la combinacion de teclas desde `BasePlatform.get_paste_shortcut()` o `get_paste_modifiers()`.

### Escenarios

#### Scenario: Pegar en Windows
- **GIVEN** que la plataforma es Windows
- **WHEN** se invoca `platform.get_paste_shortcut()`
- **THEN** retorna `(Key.ctrl, 'v')`

#### Scenario: Pegar en Linux
- **GIVEN** que la plataforma es Linux
- **WHEN** se invoca `platform.get_paste_shortcut()`
- **THEN** retorna `(Key.ctrl, 'v')`

#### Scenario: Pegar en macOS
- **GIVEN** que la plataforma es macOS
- **WHEN** se invoca `platform.get_paste_shortcut()`
- **THEN** retorna `(Key.cmd, 'v')`

### Interfaces

```python
def get_paste_shortcut(self) -> Tuple[str, str]: ...
# Retorna (modifier_key_name, character)

def get_paste_modifiers(self) -> list:
    # Retorna lista de objetos Key de pynput
    ...
```

### Manejo de Errores

| Error | Condicion | Accion |
|-------|-----------|--------|
| `KeyError` | pynput no reconoce el key name | Loggear error; propagar como `RuntimeError` |

### Notas por Plataforma

- **Linux Wayland**: pynput.Controller puede fallar silenciosamente; documentar como limitacion conocida.
- **macOS**: requiere permiso Accessibility para que pynput.Controller funcione.

---

## 4. multi-gpu-detection

### Proposito
Detectar automaticamente el acelerador de hardware disponible (CUDA, MPS, ROCm) y seleccionar el `device` y `compute_type` optimos para `faster-whisper`.

### Requerimientos

#### REQ-GPU-001: Deteccion CUDA
El sistema **DEBE** detectar NVIDIA CUDA via `torch.cuda.is_available()`.

#### REQ-GPU-002: Deteccion MPS (macOS)
El sistema **DEBE** detectar Apple Silicon MPS via `torch.backends.mps.is_available()` cuando `sys.platform == "darwin"`.

#### REQ-GPU-003: Deteccion ROCm (Linux AMD)
El sistema **DEBERIA** detectar AMD ROCm en Linux. Nota: PyTorch ROCm expone interfaz CUDA-compatible.

#### REQ-GPU-004: Fallback CPU
El sistema **DEBE** usar CPU como fallback si no hay acelerador disponible.

#### REQ-GPU-005: Seleccion de compute_type
El sistema **DEBE** seleccionar el `compute_type` apropiado:
- CUDA -> `int8_float16` (si VRAM >= 4 GB) o `int8`
- MPS -> `float16` (MPS no soporta `int8` en todas las ops)
- CPU -> `int8`

### Escenarios

#### Scenario: NVIDIA CUDA disponible
- **GIVEN** que `torch.cuda.is_available() == True`
- **AND** la VRAM es >= 4 GB
- **WHEN** se invoca `platform.detect_gpu()`
- **THEN** retorna `("cuda", "int8_float16")`

#### Scenario: NVIDIA CUDA con poca VRAM
- **GIVEN** que `torch.cuda.is_available() == True`
- **AND** la VRAM es < 4 GB
- **WHEN** se invoca `platform.detect_gpu()`
- **THEN** retorna `("cuda", "int8")`

#### Scenario: Apple Silicon MPS
- **GIVEN** que `sys.platform == "darwin"`
- **AND** `torch.backends.mps.is_available() == True`
- **WHEN** se invoca `platform.detect_gpu()`
- **THEN** retorna `("mps", "float16")`

#### Scenario: macOS Intel sin MPS
- **GIVEN** que `sys.platform == "darwin"`
- **AND** `torch.backends.mps.is_available() == False`
- **WHEN** se invoca `platform.detect_gpu()`
- **THEN** retorna `("cpu", "int8")`

#### Scenario: Linux AMD ROCm
- **GIVEN** que la plataforma es Linux
- **AND** `torch.cuda.is_available() == True` (ROCm/HIP)
- **AND** el nombre del dispositivo contiene "AMD"
- **WHEN** se invoca `platform.detect_gpu()`
- **THEN** retorna `("cuda", "int8_float16")`

#### Scenario: Sin acelerador
- **GIVEN** que no hay CUDA, MPS ni ROCm
- **WHEN** se invoca `platform.detect_gpu()`
- **THEN** retorna `("cpu", "int8")`

### Interfaces

```python
def detect_gpu(self) -> Tuple[str, str]:
    """
    Retorna (device_name, compute_type).
    device_name: "cuda" | "mps" | "cpu"
    compute_type: "int8_float16" | "float16" | "int8"
    """
```

### Manejo de Errores

| Error | Condicion | Accion |
|-------|-----------|--------|
| `ImportError` | `torch` no instalado | Retornar `("cpu", "int8")`; log warning |
| `RuntimeError` | `torch.cuda` inicializa mal | Fallback a CPU; log error |

### Notas por Plataforma

- **MPS**: puede tener operaciones no implementadas en `faster-whisper`; requiere testing real.
- **ROCm**: la deteccion por nombre del dispositivo puede ser fragil; usar `torch.cuda.get_device_name()`.
- **VRAM en macOS**: unified memory; usar `psutil.virtual_memory().total` como proxy.

---

## 5. cross-platform-install

### Proposito
Refactorizar `install.py` para que genere scripts, servicios y atajos de autostart correctos segun la plataforma.

### Requerimientos

#### REQ-INST-001: Deteccion de plataforma
El instalador **DEBE** detectar el SO y delegar a `_setup_<platform>()`.

#### REQ-INST-002: Entorno virtual
El instalador **DEBE** crear `.venv` con la version correcta de Python en todas las plataformas.

#### REQ-INST-003: PyTorch por plataforma
El instalador **DEBE** instalar PyTorch desde el indice correcto:
- Windows/Linux NVIDIA -> `cu121` o `cu118`
- Linux AMD -> `rocm5.x`
- macOS -> indice por defecto (CPU/MPS)
- CPU-only -> `--index-url` CPU

#### REQ-INST-004: Scripts de lanzamiento
El instalador **DEBE** generar:
- Windows: `lanzador.vbs` + `.bat` opcional
- Linux: `run.sh` + `wisprlocal.service`
- macOS: `run.sh` + `com.wisprlocal.plist`

#### REQ-INST-005: Autostart opcional
El instalador **DEBERIA** preguntar al usuario antes de habilitar autostart.

### Escenarios

#### Scenario: Instalacion en Windows
- **GIVEN** que el sistema es Windows
- **WHEN** se ejecuta `install.py`
- **THEN** crea `.venv\Scripts\python.exe`
- **AND** genera `lanzador.vbs` en la raiz del proyecto
- **AND** instala PyTorch CUDA si detecta NVIDIA

#### Scenario: Instalacion en Linux
- **GIVEN** que el sistema es Linux
- **WHEN** se ejecuta `install.py`
- **THEN** crea `.venv/bin/python`
- **AND** genera `run.sh` ejecutable
- **AND** genera `wisprlocal.service` en `~/.config/systemd/user/`
- **AND** genera `wisprlocal.desktop` en `~/.local/share/applications/`

#### Scenario: Instalacion en macOS
- **GIVEN** que el sistema es macOS
- **WHEN** se ejecuta `install.py`
- **THEN** crea `.venv/bin/python`
- **AND** genera `run.sh`
- **AND** genera `com.wisprlocal.plist` en `~/Library/LaunchAgents/`

### Interfaces

```python
def setup_autostart(self, project_root: Path) -> None: ...
def get_venv_python_path(self) -> Path: ...
def get_pytorch_install_cmd(self) -> list[str]: ...
```

### Manejo de Errores

| Error | Condicion | Accion |
|-------|-----------|--------|
| `PermissionError` | No puede escribir en `~/.config/systemd/user` | Loggear; instruir al usuario manualmente |
| `subprocess.CalledProcessError` | `pip install` falla | Loggear stdout/stderr; abortar instalacion |
| `RuntimeError` | Python < 3.12 | Mostrar mensaje claro; salir con codigo != 0 |

### Notas por Plataforma

- **Windows**: `pythonw.exe` oculta la consola; preservar este comportamiento.
- **Linux**: `run.sh` debe usar `nohup` o `exec` para background; dar permisos `+x`.
- **macOS**: no hay `pythonw.exe`; launchd redirige stdout/stderr.

---

## 6. linux-service

### Proposito
Generar y opcionalmente registrar un servicio systemd user-level y un archivo `.desktop` para integracion con el escritorio Linux.

### Requerimientos

#### REQ-SVC-001: Generar systemd service
El sistema **DEBE** generar un archivo `wisprlocal.service` valido para systemd user-level.

#### REQ-SVC-002: Generar .desktop
El sistema **DEBE** generar un archivo `.desktop` con `Name`, `Exec`, `Icon` y `Categories`.

#### REQ-SVC-003: Autostart opcional
El sistema **DEBERIA** preguntar al usuario antes de ejecutar `systemctl --user enable wisprlocal`.

### Escenarios

#### Scenario: Generacion de service file
- **GIVEN** que la plataforma es Linux
- **WHEN** se invoca `platform.setup_autostart(project_root)`
- **THEN** crea `~/.config/systemd/user/wisprlocal.service`
- **AND** contiene `ExecStart=%h/WisprLocal/.venv/bin/python -m wispr`
- **AND** contiene `WorkingDirectory=%h/WisprLocal`
- **AND** contiene `Restart=on-failure`

#### Scenario: Generacion de .desktop
- **GIVEN** que la plataforma es Linux
- **WHEN** se completa la instalacion
- **THEN** crea `~/.local/share/applications/wisprlocal.desktop`
- **AND** contiene `Exec=/home/user/WisprLocal/run.sh`
- **AND** contiene `Terminal=false`

#### Scenario: Usuario rechaza autostart
- **GIVEN** que el usuario responde "no" a la pregunta de autostart
- **WHEN** finaliza la instalacion
- **THEN** genera los archivos pero **NO** ejecuta `systemctl --user enable`

### Interfaces

```python
def setup_autostart(self, project_root: Path) -> None:
    """Genera service y .desktop; pregunta por autostart."""
```

### Manejo de Errores

| Error | Condicion | Accion |
|-------|-----------|--------|
| `FileNotFoundError` | `systemctl` no esta instalado | Saltar autostart; log warning |
| `PermissionError` | Sin permiso en `~/.config` | Intentar con `sudo -u $USER`; si falla, instrucciones manuales |

### Notas por Plataforma

- **systemd**: usar `%h` para home directory en vez de hardcodear `/home/user`.
- **GNOME**: puede requerir `gnome-shell-extension-appindicator` para que pystray funcione.
- **Wayland**: `.desktop` funciona igual; el service arranca independientemente del compositor.

---

## 7. macos-launchd

### Proposito
Generar y opcionalmente cargar un `launchd` plist para que WisprLocal arranque con el usuario en macOS.

### Requerimientos

#### REQ-LNC-001: Generar plist valido
El sistema **DEBE** generar un plist XML valido en `~/Library/LaunchAgents/com.wisprlocal.agent.plist`.

#### REQ-LNC-002: Autostart opcional
El sistema **DEBERIA** preguntar al usuario antes de ejecutar `launchctl load`.

#### REQ-LNC-003: RunAtLoad
El plist **DEBE** incluir `<key>RunAtLoad</key><true/>`.

### Escenarios

#### Scenario: Generacion de plist
- **GIVEN** que la plataforma es macOS
- **WHEN** se invoca `platform.setup_autostart(project_root)`
- **THEN** crea `~/Library/LaunchAgents/com.wisprlocal.agent.plist`
- **AND** contiene `ProgramArguments` con el path a `.venv/bin/python -m wispr`
- **AND** contiene `WorkingDirectory` apuntando al proyecto

#### Scenario: Carga de agent
- **GIVEN** que el usuario acepta autostart
- **WHEN** finaliza la instalacion
- **THEN** ejecuta `launchctl load ~/Library/LaunchAgents/com.wisprlocal.agent.plist`

### Interfaces

```python
def setup_autostart(self, project_root: Path) -> None:
    """Genera plist y opcionalmente carga con launchctl."""
```

### Manejo de Errores

| Error | Condicion | Accion |
|-------|-----------|--------|
| `subprocess.CalledProcessError` | `launchctl load` falla | Loggear; mostrar instrucciones manuales |

### Notas por Plataforma

- **macOS**: `~/Library/LaunchAgents/` es el lugar correcto para agents por usuario.
- **Unloading**: documentar `launchctl unload` para desinstalar.

---

## 8. tray-graceful-degradation

### Proposito
Permitir que WisprLocal funcione en entornos sin display server (headless, SSH) sin crash por `pystray`.

### Requerimientos

#### REQ-TRAY-001: Catch DisplayNameError
El sistema **DEBE** capturar `pystray._util.X11.DisplayNameError` (o excepciones equivalentes) al iniciar el tray.

#### REQ-TRAY-002: Continuar sin tray
El sistema **DEBE** continuar la ejecucion en modo headless si el tray no puede inicializarse.

#### REQ-TRAY-003: Log de advertencia
El sistema **DEBE** loguear un warning indicando que corre sin tray icon.

### Escenarios

#### Scenario: Linux headless via SSH
- **GIVEN** que no hay `$DISPLAY` ni `$WAYLAND_DISPLAY`
- **WHEN** se inicia `wispr/tray.py`
- **THEN** `pystray.Icon.run()` lanza `DisplayNameError`
- **AND** la excepcion es capturada
- **AND** la aplicacion continua ejecutandose
- **AND** se loguea: "Running without system tray (headless mode)"

#### Scenario: Linux con display
- **GIVEN** que `$DISPLAY` esta seteado
- **WHEN** se inicia `wispr/tray.py`
- **THEN** el tray icon aparece normalmente

### Interfaces

```python
# En wispr/tray.py o __main__.py
try:
    icon.run()
except DisplayNameError:
    logger.warning("Running without system tray (headless mode)")
    run_headless()
```

### Manejo de Errores

| Error | Condicion | Accion |
|-------|-----------|--------|
| `DisplayNameError` | No hay display server | Log warning; continuar headless |
| `ImportError` | `pystray` no instalado | Log warning; continuar headless |

### Notas por Plataforma

- **Linux**: tambien puede fallar por falta de `libappindicator`; capturar excepcion generica como fallback.
- **Windows/macOS**: raramente falla; aun asi, la degradacion debe aplicarse por consistencia.

---

## 9. wayland-detection

### Proposito
Detectar si el usuario corre en Wayland y advertir sobre las limitaciones de global hotkeys.

### Requerimientos

#### REQ-WAY-001: Deteccion de Wayland
El sistema **DEBE** detectar Wayland verificando `os.environ.get("XDG_SESSION_TYPE") == "wayland"`.

#### REQ-WAY-002: Advertencia al usuario
El sistema **DEBE** mostrar un mensaje claro al usuario explicando que los hotkeys globales no funcionan en Wayland.

#### REQ-WAY-003: No bloquear arranque
El sistema **NO DEBE** impedir el arranque de la aplicacion por estar en Wayland.

### Escenarios

#### Scenario: Wayland detectado
- **GIVEN** que `XDG_SESSION_TYPE=wayland`
- **WHEN** arranca WisprLocal
- **THEN** loguea y/o muestra: "Wayland detected: global hotkeys require X11 or additional configuration. See README."
- **AND** la aplicacion continua ejecutandose

#### Scenario: X11 detectado
- **GIVEN** que `XDG_SESSION_TYPE=x11`
- **WHEN** arranca WisprLocal
- **THEN** los hotkeys globales funcionan normalmente

#### Scenario: Variable no seteada
- **GIVEN** que `XDG_SESSION_TYPE` no esta definida
- **WHEN** arranca WisprLocal
- **THEN** asume X11 y no muestra advertencia

### Interfaces

```python
def is_wayland(self) -> bool:
    """True si el entorno grafico es Wayland."""
```

### Manejo de Errores

| Error | Condicion | Accion |
|-------|-----------|--------|
| `KeyError` | `os.environ` no tiene la clave | Retornar `False` (asumir X11) |

### Notas por Plataforma

- **Wayland**: la limitacion es arquitectonica (seguridad del input); no hay workaround simple sin `evdev`.
- **XWayland**: pynput cae a XWayland pero solo recibe eventos de apps X11, no globales.
- **Recomendacion**: sugerir al usuario iniciar sesion en X11 si necesita hotkeys.

---

## 10. macos-accessibility-warning

### Proposito
Informar al usuario de macOS sobre el requisito de permiso "Accessibility" para que los hotkeys y la inyeccion funcionen.

### Requerimientos

#### REQ-ACC-001: Informar en primer arranque
El sistema **DEBE** detectar si `pynput` no tiene permisos de Accessibility e informar al usuario.

#### REQ-ACC-002: Instrucciones paso a paso
El mensaje **DEBE** incluir instrucciones claras: "System Settings > Privacy & Security > Accessibility > Add Python/Terminal.app".

#### REQ-ACC-003: No bloquear indefinidamente
El sistema **NO DEBE** bloquear el arranque esperando que el usuario otorgue el permiso.

#### REQ-ACC-004: Recordar que ya aviso
El sistema **DEBERIA** no mostrar la advertencia repetidamente si ya se mostro antes (ej: archivo flag `~/.wisprlocal/.accessibility_warned`).

### Escenarios

#### Scenario: Primer arranque sin permisos
- **GIVEN** que es la primera vez que corre en macOS
- **AND** `pynput` no tiene permisos de Accessibility
- **WHEN** arranca WisprLocal
- **THEN** muestra un mensaje/aviso con instrucciones
- **AND** crea el flag para no repetir

#### Scenario: Permisos ya otorgados
- **GIVEN** que Python/Terminal.app esta en la lista de Accessibility
- **WHEN** arranca WisprLocal
- **THEN** no muestra advertencia

#### Scenario: Segundo arranque sin permisos
- **GIVEN** que ya se mostro la advertencia anteriormente
- **WHEN** arranca WisprLocal
- **THEN** loguea un reminder breve
- **AND** no muestra el dialogo completo de nuevo

### Interfaces

```python
def check_accessibility_permission(self) -> bool:
    """Retorna True si Accessibility esta permitido."""

def show_accessibility_warning(self) -> None:
    """Muestra advertencia e instrucciones. Idempotente."""
```

### Manejo de Errores

| Error | Condicion | Accion |
|-------|-----------|--------|
| `OSError` | No puede crear flag file | Ignorar; mostrar advertencia cada vez |

### Notas por Plataforma

- **Deteccion**: pynput no expone directamente el estado de permisos. Un heuristico es intentar crear un `Listener` y verificar si recibe eventos globales.
- **.app bundle**: si Fase 3 distribuye como `.app`, el bundle entero debe estar en la whitelist.
- **UX**: usar `tkinter.messagebox` o `subprocess` con `osascript -e 'display alert ...'` para que sea nativo.

---

## Matriz de Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigacion en Spec |
|--------|-------------|---------|--------------------|
| Wayland sin hotkeys | Alta | Medio | REQ-WAY-001/002/003 |
| MPS inestable | Media | Medio | REQ-GPU-005 (float16) |
| tkinter roto macOS | Media | Medio | Documentar Python oficial |
| ROCm complejo | Media | Bajo | REQ-GPU-003 (fallback CPU) |
| Permisos Accessibility | Alta | Medio | REQ-ACC-001/002/003 |
| pystray headless | Media | Bajo | REQ-TRAY-001/002 |

---

## Glosario

- **ABC**: Abstract Base Class
- **CUDA**: Compute Unified Device Architecture (NVIDIA)
- **MPS**: Metal Performance Shaders (Apple Silicon)
- **ROCm**: Radeon Open Compute (AMD Linux)
- **systemd**: System and Service Manager (Linux)
- **launchd**: Service management framework (macOS)
- **Wayland**: Protocolo de servidor grafico (Linux)
- **X11**: X Window System (Linux/Unix)
- **headless**: Sin servidor grafico/display
