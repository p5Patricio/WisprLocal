# Exploration: WisprLocal Fase 2 — Cross-Platform (Windows / Linux / macOS)

## Estado Actual

WisprLocal v1 (Fase 1) es una aplicación Python 3.12+ que corre exclusivamente en Windows. Está compuesta por 11 módulos principales y un instalador (`install.py`). El architecture es modular y thread-safe, lo cual facilita la portabilidad. Los únicos módulos realmente acoplados a Windows son:

- `sounds.py` — usa `winsound.Beep()` (builtin Windows-only)
- `install.py` — genera `.vbs`, usa `pythonw.exe`, y escribe en `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`
- `config.py` — detección de hardware solo contempla `torch.cuda` (NVIDIA)
- `injection.py` — hardcodea `keyboard.Key.ctrl` + `"v"` (asume Ctrl+V en todos lados)

El resto de dependencias (`pystray`, `pynput`, `pyperclip`, `sounddevice`, `tkinter`) ya son cross-platform por diseño, aunque con caveats por plataforma.

---

## Áreas Afectadas

| Archivo | Por qué está afectado |
|---------|----------------------|
| `wispr/sounds.py` | `winsound` no existe en Linux/macOS |
| `wispr/config.py` | `detect_optimal_model()` solo detecta VRAM NVIDIA (`torch.cuda`) |
| `wispr/injection.py` | `Ctrl+V` no funciona en macOS; en Linux pynput.Controller funciona pero con caveats en Wayland |
| `wispr/hotkeys.py` | pynput funciona en Linux (X11) y macOS, pero requiere permisos especiales en macOS y falla en Wayland |
| `wispr/tray.py` | pystray es cross-platform pero requiere backends distintos en Linux (AppIndicator vs GTK vs Xorg) |
| `wispr/overlay.py` | tkinter es cross-platform, pero en macOS hay problemas de linking con Tcl/Tk según cómo se instaló Python |
| `install.py` | Windows-only: `pythonw.exe`, VBS, Startup folder |
| `requirements.txt` | No incluye dependencias de plataforma (torch index-url, etc.) |

---

## Análisis por API / Módulo

### 1. Audio feedback (winsound → cross-platform)

**Enfoque actual:** `winsound.Beep(freq, duration)` — builtin de Windows, sincrónico, bloqueante. Se envuelve en thread daemon para no bloquear.

**Alternativas investigadas:**

| Opción | Pros | Contras | Complejidad |
|--------|------|---------|-------------|
| `print('\a')` | Sin dependencias, universal | Muchos terminales lo silencian o usan visual bell; no controla frecuencia/duración | Baja |
| `simpleaudio` | Cross-platform, reproduce WAV | Requiere archivo WAV embebido; añade dependencia compilada | Media |
| `pygame.mixer` | Muy robusto | Pesado (dependencia enorme para solo un beep) | Alta |
| `beepy` | Wrapper simple de simpleaudio | Añade dependencia, no da control de frecuencia exacta | Media |
| `os.system('beep -f F -l D')` (Linux) | Control total de frecuencia/duración | Requiere instalar `beep` (paquete del sistema) | Baja |
| `osascript` / `afplay` (macOS) | Usa sonidos del sistema | No controla frecuencia exacta, requiere archivos de sonido | Baja |
| `sounddevice` output | Ya está en requirements, puede generar tone | Requiere código para sintetizar onda senoidal; overkill | Media |

**Recomendación:** Implementar un backend por plataforma:
- **Windows:** conservar `winsound.Beep()`
- **Linux:** intentar `winsound`-like vía `os.system('beep ...')` con fallback a `print('\a')` si no está instalado
- **macOS:** usar `osascript -e 'beep'` o `AppKit.NSBeep()` (si se tiene `pyobjc`), con fallback a `print('\a')`

Alternativa más simple y robusta: embeber 3-4 archivos WAV minimalistas (start, stop, ready, error) de ~1KB cada uno y reproducirlos con `simpleaudio` en todas las plataformas. Esto unifica el código, elimina dependencias de sistema, y el sonido es consistente. `simpleaudio` tiene wheels precompilados.

**Tradeoffs:**
- Backend por plataforma: cero nuevas dependencias, pero código más complejo y sonido distinto por OS.
- WAV + simpleaudio: dependencia extra (~500KB), pero código unificado y experiencia consistente.

**Confianza:** Alta
**Esforzo:** Pequeño (backend por plataforma) o Pequeño-Medio (WAV + simpleaudio)

---

### 2. System tray (pystray)

**Enfoque actual:** `pystray.Icon` con menú simple (Cargar modelo, Descargar modelo, Salir). Corre en main thread (bloqueante).

**Comportamiento cross-platform de pystray:**
- **Windows:** backend `win32`. Funciona out-of-the-box. Todas las features disponibles.
- **macOS:** backend `darwin`. Todas las features disponibles. El icono aparece en la barra de menú (NSStatusItem).
- **Linux:** tres backends posibles:
  - `appindicator` (preferido): requiere `libappindicator` o `ayatana-appindicator` en el sistema. En GNOME moderno requiere extensión `gnome-shell-extension-appindicator`.
  - `gtk`: requiere GTK3/GObject. En GNOME Shell sin extensión puede no mostrarse.
  - `xorg` (fallback): usa `python-xlib`. No soporta menús (solo default action).

**Caveats Linux:**
- Sin display server (headless/SSH): falla con `DisplayNameError`.
- Wayland: el backend Xorg falla; AppIndicator funciona si el compositor lo soporta (KDE sí, GNOME necesita extensión).
- Se puede forzar backend con env var `PYSTRAY_BACKEND=appindicator`.

**Recomendación:**
- No tocar código de `tray.py` en su mayoría. `pystray` ya abstrae todo.
- Documentar que en Linux GNOME puede requerir `sudo apt install gir1.2-appindicator3-0.1` y la extensión appindicator.
- Agregar graceful degradation: si `icon.run()` lanza `DisplayNameError` u otro error de display, loggear warning y continuar sin tray (modo headless).

**Confianza:** Alta
**Esforzo:** Pequeño

---

### 3. Keyboard listener (pynput)

**Enfoque actual:** `pynput.keyboard.Listener` global (hotkeys PTT y toggle).

**Cross-platform status:**
- **Windows:** funciona perfecto. No requiere permisos especiales (aunque algunas apps elevadas pueden bloquear input).
- **Linux (X11):** funciona si `$DISPLAY` está seteado. Requiere X server.
- **Linux (Wayland):** **NO FUNCIONA** para global hotkeys. Wayland bloquea input monitoring por seguridad. pynput cae a Xwayland y solo recibe eventos de apps X11. Es un problema conocido sin solución simple.
- **macOS:** requiere permiso **Accessibility** (System Settings → Privacy & Security → Accessibility). El proceso que corre Python (Terminal.app, VS Code, o la app bundle) debe estar en la whitelist. Sin esto, el listener arranca pero no recibe eventos globales (`IS_TRUSTED` es `False`).

**Alternativas para Linux Wayland:**
- `evdev`: lee directo de `/dev/input/event*`. Requiere usuario en grupo `input` o root. Muy bajo nivel, hay que mapear keycodes a teclas.
- `ydotool`: herramienta de sistema (como `xdotool` para Wayland). Requiere daemon `ydotoold`.
- `xdotool`: solo X11.
- Cambiar a sesión X11: solución del usuario, no de la app.

**Recomendación:**
- Conservar `pynput` como backend principal en Windows, macOS y Linux X11.
- En Linux Wayland: detectar `XDG_SESSION_TYPE == "wayland"` y mostrar mensaje claro al usuario: "Wayland detectado: los hotkeys globales requieren X11 o configuración adicional. Ver README."
- Opcional: implementar backend `evdev` como fallback experimental para Linux Wayland, pero esto es esfuerzo mediano-alto.
- En macOS: documentar claramente el requisito de permiso Accessibility. En primer arranque, mostrar overlay o log con instrucciones.

**Confianza:** Alta para Windows/macOS/X11; Baja para Wayland
**Esforzo:** Pequeño (detección + mensajes) a Medio (si se implementa evdev)

---

### 4. Keyboard injection (pynput.Controller)

**Enfoque actual:** `keyboard.Controller()` envía `Ctrl+V` para pegar texto.

**Cross-platform status:**
- **Windows:** `Ctrl+V` funciona perfecto.
- **Linux (X11):** `Ctrl+V` funciona con pynput.Controller.
- **Linux (Wayland):** pynput.Controller falla silenciosamente (mismo problema que listener).
- **macOS:** debe usar **`Cmd+V`** (`keyboard.Key.cmd`), no `Ctrl+V`. Además requiere permiso Accessibility para el Controller.

**Caveats macOS:**
- Accessibility permission aplica tanto para listener como para controller.
- Algunas apps (especialmente las que usan input methods complejos) pueden no recibir el paste simulado.

**Recomendación:**
- En `injection.py`, detectar plataforma:
  - Windows/Linux: `Ctrl+V`
  - macOS: `Cmd+V` (Key.cmd)
- En Linux Wayland: documentar que la inyección requiere X11 o herramientas como `ydotool`/`wl-copy`.

**Confianza:** Alta
**Esforzo:** Pequeño

---

### 5. Clipboard (pyperclip)

**Enfoque actual:** `pyperclip.copy()` / `pyperclip.paste()`.

**Cross-platform status:** Ya es cross-platform. No requiere cambios de código.

**Caveats por plataforma:**
- **Windows:** funciona nativamente (ctypes + Windows API).
- **macOS:** usa `pbcopy`/`pbpaste` (vienen con macOS). Si no, puede usar `pyobjc`. No requiere acción del usuario.
- **Linux (X11):** requiere `xclip` o `xsel` instalado. La mayoría de distros lo tienen, pero no es garantía.
- **Linux (Wayland):** requiere `wl-clipboard` (`wl-copy`/`wl-paste`). pyperclip lo detecta automáticamente vía `$WAYLAND_DISPLAY`.

**Recomendación:**
- Sin cambios de código necesarios.
- En `install.py` / documentación: agregar dependencias del sistema para Linux:
  - X11: `xclip` o `xsel`
  - Wayland: `wl-clipboard`

**Confianza:** Alta
**Esforzo:** Ninguno (solo documentación)

---

### 6. Audio capture (sounddevice)

**Enfoque actual:** `sounddevice.InputStream` (wrapper de PortAudio).

**Cross-platform status:** PortAudio es cross-platform y soporta Windows, macOS y Linux.

**Caveats:**
- **Linux:** requiere que ALSA/PulseAudio/PipeWire esté configurado. Algunas distros mínimas pueden no tener los headers de ALSA para compilar PortAudio, pero el wheel de `sounddevice` incluye bibliotecas precompiladas.
- **macOS:** funciona out-of-the-box. Usa CoreAudio.
- **Windows:** funciona out-of-the-box. Usa DirectSound/WASAPI/MME.

**Recomendación:** Sin cambios de código. Documentar que en Linux puede requerir `libportaudio2` si el wheel no funciona.

**Confianza:** Alta
**Esforzo:** Ninguno

---

### 7. GPU detection para auto-model

**Enfoque actual:** `torch.cuda.is_available()` y `torch.cuda.get_device_properties(0).total_memory`. Fallback a `psutil.virtual_memory()` (RAM) si no hay CUDA.

**Cross-platform gaps:**
- Solo detecta NVIDIA (CUDA). No detecta:
  - **Apple Silicon (M1/M2/M3):** usa `torch.backends.mps.is_available()` y device `"mps"`
  - **AMD en Linux:** usa ROCm. PyTorch para ROCm expone `torch.cuda.is_available()` = `True` (usa interfaz compatible CUDA/HIP), pero el nombre del dispositivo es AMD.
  - **Intel Arc / otros aceleradores:** no soportados por faster-whisper de todos modos.

**Recomendación:**
Refactorizar `detect_optimal_model()` y `config.py` para soportar múltiples backends:

```python
def detect_device() -> tuple[str, str]:
    """Retorna (device_name, compute_type)."""
    if sys.platform == "darwin" and torch.backends.mps.is_available():
        return "mps", "float16"  # MPS no soporta int8 en todas las ops
    if torch.cuda.is_available():
        return "cuda", "int8_float16"
    return "cpu", "int8"
```

Y en `transcription.py`, `load_model()` debe usar el device detectado. La VRAM en macOS (unified memory) se puede detectar con `psutil` (la RAM total es la VRAM disponible para MPS).

Para AMD/ROCm en Linux: `torch.cuda.is_available()` ya devuelve `True` si PyTorch fue instalado con índice ROCm, así que la lógica actual *parcialmente* funciona, pero el `install.py` debe instalar `torch` desde el índice ROCm cuando detecta AMD.

**Caveats MPS:**
- faster-whisper con MPS puede tener problemas con algunas operaciones que no están implementadas en MPS. Requiere testing.
- MPS no soporta `int8_float16` ni `int8` en todas las operaciones; `float16` es más seguro.

**Confianza:** Alta para detección; Media para estabilidad de MPS con faster-whisper
**Esforzo:** Medio

---

### 8. Installation / packaging

**Enfoque actual:**
1. Verifica Python 3.12+
2. Detecta GPU NVIDIA (`nvidia-smi`)
3. Crea `.venv`
4. Instala PyTorch desde índice CUDA o CPU
5. Instala `requirements.txt`
6. Genera `lanzador.vbs` (Windows-only)
7. Opcional: copia a Startup folder de Windows

**Linux equivalente:**
- Entorno virtual: `.venv` funciona igual.
- Python path: `.venv/bin/python` en vez de `Scripts/python.exe`.
- PyTorch índices: para Linux necesitamos índices CPU, CUDA, y ROCm.
- Servicio systemd (user-level): crear `~/.config/systemd/user/wisprlocal.service`:
  ```ini
  [Unit]
  Description=WisprLocal
  After=graphical-session.target

  [Service]
  Type=simple
  ExecStart=%h/WisprLocal/.venv/bin/python -m wispr
  WorkingDirectory=%h/WisprLocal
  Restart=on-failure

  [Install]
  WantedBy=default.target
  ```
- .desktop file (para lanzador gráfico): `~/.local/share/applications/wisprlocal.desktop`
- Autostart: `systemctl --user enable wisprlocal`

**macOS equivalente:**
- Entorno virtual: `.venv/bin/python`.
- launchd plist (user-level): `~/Library/LaunchAgents/com.wisprlocal.agent.plist`
- .app bundle: más complejo, requiere `py2app` o similar. Para Fase 2 puede postergarse.
- Sin `pythonw.exe`: en macOS no hay ventana de consola por defecto si se lanza desde .app o launchd.

**Recomendación:**
- Dividir `install.py` en backend por plataforma.
- Unificar lo máximo posible (crear venv, instalar pip, requirements) y delegar la parte específica a funciones `_setup_windows()`, `_setup_linux()`, `_setup_macos()`.
- En Linux/macOS, generar el archivo de servicio (systemd/launchd) y preguntar al usuario si quiere habilitar autostart.
- Documentar que en Linux/macOS también se puede correr simplemente con `python -m wispr` o `./run.sh`.

**Confianza:** Alta
**Esforzo:** Medio

---

### 9. Overlay (tkinter)

**Enfoque actual:** `tkinter.Tk()` con `overrideredirect`, `-topmost`, y posicionamiento absoluto.

**Cross-platform status:**
- **Windows:** funciona bien. `-topmost` funciona. Nota conocida: no aparece sobre fullscreen exclusivo DirectX.
- **Linux (X11):** `overrideredirect` + `wm_attributes("-topmost", True)` funciona en la mayoría de WMs. Puede requerir `wm_attributes("-type", "splash")` o `"dock"` en algunos WMs.
- **Linux (Wayland):** tkinter corre bajo XWayland. `-topmost` puede no funcionar igual; algunos compositores ignoran la hint. El overlay podría no quedar "siempre encima".
- **macOS:** tkinter funciona, pero con problemas de Tcl/Tk si Python no fue compilado con la versión correcta. Los instaladores de python.org traen Tcl/Tk bundled y funcionan bien. pyenv puede tener problemas (requiere `brew install tcl-tk` y flags de compilación). El atributo `-topmost` funciona. `overrideredirect` funciona pero la ventana puede no recibir ciertos eventos.

**Recomendación:**
- Sin cambios mayores necesarios.
- En macOS: documentar que se recomienda usar Python del instalador oficial (python.org) o Homebrew con `tcl-tk` instalado.
- En Linux Wayland: testear; si `-topmost` no funciona, documentar como limitación conocida.

**Confianza:** Alta (X11/Windows); Media (macOS, depende del Python); Media-Baja (Wayland)
**Esforzo:** Pequeño

---

### 10. Process lifecycle / startup (headless/daemon)

**Enfoque actual:** `pythonw.exe` + VBS para ocultar consola. Tray bloquea main thread.

**Linux:**
- No hay `pythonw.exe`. Para correr sin consola, se puede usar `nohup python -m wispr &` o un script `.sh` con `&`.
- El approach "correcto" es systemd user service (`Type=simple`, no fork necesario porque el tray ya bloquea).
- Alternativa simple: script `run.sh`:
  ```bash
  #!/bin/bash
  cd "$(dirname "$0")"
  nohup .venv/bin/python -m wispr >/dev/null 2>&1 &
  ```

**macOS:**
- No hay `pythonw.exe` tampoco.
- launchd Agent (`LaunchAgents/`) es el equivalente a systemd. Se carga con `launchctl load`.
- Si se corre desde Terminal, la consola es visible a menos que se redirija stdout/stderr.
- Para "sin ventana", launchd o .app bundle son las opciones.

**Recomendación:**
- Generar scripts de lanzamiento por plataforma:
  - Windows: `lanzador.vbs` (existente) + opcional `.bat` para consola
  - Linux: `run.sh` (background) + `wisprlocal.service` (systemd)
  - macOS: `run.sh` + `com.wisprlocal.plist` (launchd)
- El módulo `__main__.py` ya funciona bien como entry point (`python -m wispr`) en todas las plataformas.

**Confianza:** Alta
**Esforzo:** Pequeño-Medio

---

## Arquitectura Recomendada: Plataforma Abstraction Layer

Para mantener el código limpio y no llenar cada módulo de `if sys.platform == ...`, se propone crear un paquete `wispr/platform/`:

```
wispr/
├── platform/
│   ├── __init__.py      # factory + detección
│   ├── base.py          # AbstractPlatform (ABC)
│   ├── windows.py       # WindowsPlatform
│   ├── linux.py         # LinuxPlatform
│   ├── macos.py         # macOSPlatform
│   └── _factory.py      # get_platform() -> BasePlatform
```

Cada clase implementa métodos como:
- `play_beep(freq, duration)`
- `get_paste_shortcut()` -> `(modifier_key, 'v')`  # (ctrl, v) o (cmd, v)
- `get_venv_python_path()` -> `Path`
- `get_installer_script()` -> genera launcher
- `setup_autostart()` -> crea servicio/shortcut
- `detect_gpu()` -> (device_type, compute_type)
- `has_system_tray()` -> bool (por si el display no está disponible)
- `get_overlay_topmost_hint()` -> dict de wm_attributes extras

Los módulos existentes (`sounds.py`, `injection.py`, `install.py`) importan `get_platform()` y usan la abstracción.

**Pros:**
- Código limpio, testeable, extensible.
- Cada plataforma aísla sus hacks.
- Fácil agregar nuevas plataformas.

**Contras:**
- Añade una capa de indirección.
- Requiere refactor inicial de varios módulos.

**Alternativa más simple (para Fase 2):** en vez de full OOP, usar funciones con `if/elif` en cada módulo afectado. Menos elegante pero menos código nuevo. Dado el tamaño del proyecto (11 módulos), la factory OOP es preferible para mantenibilidad.

---

## Resumen de Decisiones

| API | Recomendación | Esfuerzo | Confianza |
|-----|--------------|----------|-----------|
| Sonidos | Backend por plataforma (winsound / os beep / NSBeep) o WAV+simpleaudio | Pequeño | Alta |
| Tray | pystray sin cambios; graceful fallback si no hay display | Pequeño | Alta |
| Hotkeys | pynput + detección Wayland + mensaje de error claro | Pequeño | Alta (X11/Win/Mac) |
| Inyección | `Ctrl+V` (Win/Linux) / `Cmd+V` (macOS) | Pequeño | Alta |
| Clipboard | Sin cambios; doc de dependencias Linux | Ninguno | Alta |
| Audio | Sin cambios; doc de ALSA/portaudio Linux | Ninguno | Alta |
| GPU | Detectar MPS (macOS), ROCm (Linux AMD), CUDA (NVIDIA) | Medio | Alta |
| Overlay | Sin cambios mayores; doc de tkinter en macOS | Pequeño | Alta |
| Install | Refactor a plataformas: vbs (Win), systemd (Linux), launchd (macOS) | Medio | Alta |
| Lifecycle | Generar scripts .sh/.plist/.service por plataforma | Pequeño-Medio | Alta |

---

## Riesgos

1. **Wayland en Linux:** pynput no soporta global hotkeys en Wayland. Esto es una limitación arquitectónica de seguridad de Wayland, no un bug. La única solución robusta es evdev (requiere permisos) o pedir al usuario que use X11. Riesgo: mala UX en distros modernas (Ubuntu 22.04+ default Wayland).

2. **MPS en macOS:** faster-whisper no está testeado extensivamente en MPS. Puede haber ops no soportadas. Riesgo: la transcripción falle en macOS Apple Silicon.

3. **tkinter en macOS:** dependiendo de cómo el usuario instaló Python, tkinter puede no funcionar (gris/negro/crash). Riesgo: soporte difícil; requiere documentación clara de "usá python.org installer".

4. **ROCm en Linux AMD:** instalar PyTorch con ROCm es más complejo que CUDA. Hay versiones específicas de ROCm por GPU. Riesgo: experiencia de instalación frustrante para usuarios AMD.

5. **Permisos macOS Accessibility:** pynput requiere permisos que muchos usuarios no entienden. Si la app se distribuye como .app bundle, el bundle entero debe estar whitelisted. Riesgo: soporte al usuario.

6. **pystray en Linux headless/SSH:** si no hay display, pystray crashea. Riesgo: la app no puede correr en servidores headless. Mitigación: graceful degradation (continuar sin tray).

---

## Listo para Propuesta

**Sí.** La exploración identificó todos los puntos de fricción, las alternativas, y una arquitectura clara. El riesgo más grande es Wayland (hotkeys), pero es aceptable documentarlo como limitación conocida para Fase 2. El resto son cambios mecánicos bien acotados.

**Próximo paso recomendado:** `sdd-propose` — definir el scope exacto de Fase 2, el approach de la capa de abstracción `wispr/platform/`, y qué se deja para Fase 3.

