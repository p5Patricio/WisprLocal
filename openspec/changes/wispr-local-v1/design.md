# Design: wispr-local-v1

## Threading Model

### El problema crítico: tkinter + pystray en Windows

En Windows, tanto `tkinter` como `pystray` exigen correr en el main thread. Este es el conflicto central que el diseño debe resolver. La solución adoptada es:

**`pystray` corre en el main thread. `tkinter` corre en un thread dedicado propio.**

Justificación: `pystray` en Windows usa la API `win32gui`/`Shell_NotifyIcon` que internamente crea una ventana de mensajes oculta. Esta ventana DEBE estar en el mismo thread que la pump de mensajes de Windows (el main thread). Si se corre en un thread secundario, el menú contextual no responde a clics y los eventos de ícono se pierden.

`tkinter` en Windows tiene una restricción más flexible: DEBE correr en el thread donde se crea la instancia de `Tk()`. No requiere explícitamente el main thread — lo que importa es consistencia interna (todos los widgets del mismo root en el mismo thread). Por lo tanto, se puede crear el `Tk()` root en un thread dedicado y operar exclusivamente ahí.

### Mapa de threads

```
┌─────────────────────────────────────────────────────────────┐
│  MAIN THREAD                                                │
│  pystray.Icon.run() — Windows message pump                  │
│  Bloquea hasta que el usuario cierra la app                 │
│  Gestiona: ícono de tray, menú contextual, eventos de ícono │
└───────────────────┬─────────────────────────────────────────┘
                    │ start() antes de .run()
        ┌───────────┼────────────────────────────────┐
        │           │                                │
        ▼           ▼                                ▼
┌──────────────┐ ┌──────────────────────────────┐ ┌──────────────────────┐
│ OVERLAY      │ │ TRANSCRIPTION WORKER         │ │ MODEL LOADER         │
│ THREAD       │ │ THREAD                       │ │ THREAD               │
│ (daemon)     │ │ (daemon)                     │ │ (daemon)             │
│              │ │                              │ │                      │
│ tk.Tk()      │ │ Consume audio_queue          │ │ WhisperModel(...)    │
│ mainloop()   │ │ Blocks on queue.get()        │ │ Sets state.model     │
│              │ │ Calls faster_whisper         │ │ Signals sounds.ready │
│ Recibe cmds  │ │ Calls injection_fn           │ │                      │
│ via .after() │ │                              │ │                      │
└──────────────┘ └──────────────────────────────┘ └──────────────────────┘
        ▲
        │ root.after(0, fn) — thread-safe
        │
┌──────────────────────────────────────────────────────────────┐
│ PYNPUT LISTENER THREAD (gestionado por pynput internamente)  │
│ on_press / on_release callbacks                              │
│ Modifica state.ptt_active / state.toggle_active              │
│ Llama overlay.show_ptt() → internamente usa root.after()     │
│ Encola sentinel en audio_queue cuando libera tecla           │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ SOUNDDEVICE CALLBACK (thread interno de PortAudio)           │
│ Se activa cada ~20ms con chunks de audio                     │
│ Lee state.ptt_active / state.toggle_active                   │
│ Encola chunks en state.audio_queue (solo si grabando)        │
│ Nunca bloquea — callback debe ser O(1)                       │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ BEEP THREADS (efímeros, daemon)                              │
│ Creados por sounds.play_*()                                  │
│ Ejecutan winsound.Beep() y terminan                          │
│ Evitan bloquear el thread de hotkeys                         │
└──────────────────────────────────────────────────────────────┘
```

### Secuencia de arranque en `__main__.py`

```
1. load_config()                          → hilo main
2. AppState()                             → hilo main
3. RecordingOverlay(root, config)         → crea thread overlay, inicia tk mainloop
4. transcription_worker thread            → daemon thread, bloquea en queue.get()
5. load_model thread                      → daemon thread, carga WhisperModel
6. start_stream(state, config)            → abre PortAudio stream (siempre activo)
7. start_listener(state, config, ...)     → pynput crea su propio thread
8. start_tray(state, config, ...)         → pystray.Icon.run() BLOQUEA main thread
```

Paso 8 es el "join" natural: el main thread queda bloqueado en el event loop de pystray hasta que el usuario cierra la app. Todos los demás threads son `daemon=True`, por lo que terminan automáticamente cuando el main thread termina.

### Comunicación entre threads

| Mecanismo | Usado para |
|-----------|-----------|
| `queue.Queue` (`state.audio_queue`) | Audio chunks: PortAudio callback → transcription worker |
| `threading.Lock` (`state.lock`) | Protege escrituras a `state.model` e `state.is_loading` |
| `root.after(0, fn)` | Overlay updates: cualquier thread → tkinter thread |
| Variables `bool` en `AppState` | `ptt_active`, `toggle_active`: pynput → PortAudio callback (lectura no bloqueante, GIL protege) |
| Callbacks directos | `injection_fn`, `sounds.*`: llamados desde transcription worker thread |

---

## Data Flow

### Flujo completo de una grabación PTT

```
[Usuario presiona CapsLock]
        │
        ▼
[pynput on_press] ─────────────────────────────────────────────┐
        │                                                       │
        ├─→ state.ptt_active = True                            │
        ├─→ sounds.play_start()  [beep thread]                 │
        └─→ overlay.show_ptt()  [→ root.after(0, _show_ptt)]  │
                                                               │
[PortAudio callback, ~20ms interval]                           │
        │                                                       │
        ├─ if state.ptt_active or state.toggle_active:         │
        │       state.audio_queue.put(indata.copy())           │
        └─ else: discard                                        │
                                                               │
[Usuario suelta CapsLock]                                      │
        │                                                       │
[pynput on_release]                                            │
        │                                                       │
        ├─→ state.ptt_active = False                           │
        ├─→ sounds.play_stop()  [beep thread]                  │
        ├─→ overlay.hide()      [→ root.after(0, _hide)]       │
        └─→ state.audio_queue.put(None)  ← SENTINEL            │
                                                               │
[transcription_worker — bloqueado en queue.get()]             │
        │                                                       │
        ├─ chunk = queue.get() → acumula en buffer             │
        ├─ chunk = queue.get() → acumula...                    │
        └─ chunk = None (sentinel) → procesar buffer           │
                │                                              │
                ├─ len(buffer) < 0.3s? → descartar, log       │
                ├─ state.model is None? → descartar, log       │
                │                                              │
                ▼                                              │
        [faster_whisper.transcribe(audio, prompt=...)]        │
                │                                              │
                ▼                                              │
        [injection.inject_text(texto)]                         │
                │                                              │
                ├─ pyperclip.copy(texto)                       │
                ├─ time.sleep(0.1)  ← esperar foco            │
                ├─ keyboard.press(Key.ctrl)                    │
                ├─ keyboard.press('v')                         │
                ├─ keyboard.release('v')                       │
                └─ keyboard.release(Key.ctrl)                  │
                        │                                      │
                        ▼                                      │
                [sounds.play_ready()]  [beep thread]           │
                        │                                      │
                        ▼                                      │
                [Texto aparece en app activa]  ←──────────────┘

Estado lateral:
  overlay ← muestra/oculta según state.ptt_active / state.toggle_active
  tray    ← actualiza ícono según state.model / state.is_loading
  sounds  ← feedback en cada transición de estado
```

---

## Module Interfaces

### Module: `state.py`

```
Exposes:
  - AppState (dataclass)
      Fields: ptt_active, toggle_active, model, is_loading,
              overlay_enabled, audio_queue, lock
      Methods:
        - is_recording() -> bool

Consumes:
  - queue (stdlib)
  - threading (stdlib)
  - dataclasses (stdlib)
```

### Module: `config.py`

```
Exposes:
  - load_config(path: str = "config.toml") -> dict
      Raises: ValueError si hay campo inválido
      Side effect: crea config.toml si no existe

  - DEFAULTS: dict  (constante con defaults completos)

Consumes:
  - tomllib (stdlib Python 3.12)
  - pathlib, logging (stdlib)
```

### Module: `audio.py`

```
Exposes:
  - start_stream(state: AppState, config: dict) -> sd.InputStream
      Raises: RuntimeError si no hay micrófono (wraps PortAudioError)

  - stop_stream(stream: sd.InputStream) -> None

Consumes:
  - AppState.ptt_active (read, en callback — no lock necesario)
  - AppState.toggle_active (read, en callback — no lock necesario)
  - AppState.audio_queue (put chunks + sentinel None)
  - config["audio"]["sample_rate"]
  - config["audio"]["channels"]
  - config["audio"]["dtype"]
  - sounddevice (sd)
  - numpy (np)
```

### Module: `transcription.py`

```
Exposes:
  - load_model(state: AppState, config: dict) -> None
      Runs in caller's thread (should be a daemon thread)
      Sets state.is_loading = True/False via state.lock
      Calls sounds.play_ready() when done

  - unload_model(state: AppState) -> None
      Frees state.model, calls gc.collect() + torch.cuda.empty_cache()
      + torch.cuda.synchronize() if CUDA was used

  - transcription_worker(
        state: AppState,
        config: dict,
        injection_fn: Callable[[str], None],
        sounds: module
    ) -> None
      Infinite loop, blocks on state.audio_queue.get()
      Designed to run in a daemon thread

Consumes:
  - AppState.model (read via state.lock)
  - AppState.is_loading (read)
  - AppState.audio_queue (get)
  - config["model"]["name"]
  - config["model"]["device"]
  - config["model"]["compute_type"]
  - config["audio"]["sample_rate"]
  - config["transcription"]["language"]
  - config["transcription"]["prompt"]
  - faster_whisper.WhisperModel
  - torch, gc
```

### Module: `hotkeys.py`

```
Exposes:
  - start_listener(
        state: AppState,
        config: dict,
        overlay: RecordingOverlay,
        sounds: module,
        audio_stop_fn: Callable[[], None]
    ) -> pynput.keyboard.Listener
      Raises: ValueError si una tecla configurada no es reconocida por pynput

  - resolve_key(key_str: str) -> pynput.keyboard.Key | pynput.keyboard.KeyCode
      Helper interno, también útil para validación en arranque

Consumes:
  - AppState.ptt_active (write)
  - AppState.toggle_active (write)
  - AppState.model (read — para validar si puede grabar)
  - AppState.is_loading (read)
  - AppState.audio_queue (put sentinel None al liberar tecla)
  - config["hotkeys"]["ptt"]
  - config["hotkeys"]["toggle"]
  - config["hotkeys"]["load_model"]
  - overlay.show_ptt(), overlay.show_toggle(), overlay.hide()
  - sounds.play_start(), sounds.play_stop(), sounds.play_error()
  - pynput.keyboard
```

### Module: `overlay.py`

```
Exposes:
  - RecordingOverlay (class)
      Constructor: __init__(config: dict) -> None
        Crea el thread dedicado y arranca tk mainloop

      Public methods (all thread-safe via root.after):
        - show_ptt() -> None
        - show_toggle() -> None
        - show_loading() -> None
        - hide() -> None
        - destroy() -> None

      Si config["overlay"]["enabled"] == False:
        Todos los métodos son no-op, no se crea ningún widget tk

Consumes:
  - config["overlay"]["enabled"]
  - config["overlay"]["position"]
  - config["overlay"]["opacity"]
  - tkinter (stdlib)
  - threading (stdlib)
```

### Module: `tray.py`

```
Exposes:
  - start_tray(
        state: AppState,
        config: dict,
        on_load: Callable[[], None],
        on_unload: Callable[[], None],
        on_quit: Callable[[], None]
    ) -> None
      BLOQUEA — llama pystray.Icon.run() internamente
      Diseñado para ser el último call en main()

  - update_tray_icon(icon: pystray.Icon, state: AppState) -> None
      Helper para actualizar ícono/tooltip desde callbacks

Consumes:
  - AppState.model (read)
  - AppState.is_loading (read)
  - AppState.ptt_active (read)
  - config["model"]["name"]
  - config["hotkeys"]["ptt"]
  - config["hotkeys"]["toggle"]
  - pystray
  - PIL (Pillow)
  - subprocess (para abrir config.toml con editor del sistema)
```

### Module: `injection.py`

```
Exposes:
  - inject_text(text: str, delay_ms: int = 100) -> None
      No-op si text.strip() == ""
      Restaura clipboard previo después de pegar

Consumes:
  - pyperclip
  - pynput.keyboard.Controller
  - pynput.keyboard.Key
  - time
```

### Module: `sounds.py`

```
Exposes:
  - play_start() -> None   # 1200 Hz, 100ms — en daemon thread
  - play_stop() -> None    # 800 Hz, 100ms — en daemon thread
  - play_ready() -> None   # 1000 Hz 80ms + 1200 Hz 80ms — en daemon thread
  - play_error() -> None   # 400 Hz, 300ms — en daemon thread

Consumes:
  - winsound (stdlib, Windows-only)
  - threading (stdlib)
```

### Module: `__main__.py`

```
Exposes:
  - main() -> None  (llamado por __main__ guard)

Consumes:
  - Todos los módulos del paquete wispr
  - logging, sys (stdlib)

Orden de inicialización:
  1. config.load_config()
  2. AppState()
  3. RecordingOverlay(config)          → arranca overlay thread
  4. Thread(transcription_worker)      → daemon thread
  5. Thread(load_model)                → daemon thread
  6. audio.start_stream(state, config) → PortAudio stream abierto
  7. hotkeys.start_listener(...)       → pynput thread
  8. tray.start_tray(...)              → BLOQUEA main thread
```

---

## AppState Definition

```python
# wispr/state.py
from __future__ import annotations
import queue
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppState:
    # Estado de grabación (escritura desde pynput thread, lectura desde PortAudio callback)
    ptt_active: bool = False
    toggle_active: bool = False

    # Modelo Whisper (escritura solo con lock adquirido)
    model: Any = None           # WhisperModel | None
    is_loading: bool = False    # True mientras load_model() está corriendo

    # Overlay
    overlay_enabled: bool = True

    # Queue de audio: PortAudio callback → transcription_worker
    # Contiene: np.ndarray chunks | None (sentinel = fin de grabación)
    audio_queue: queue.Queue = field(default_factory=queue.Queue)

    # Lock para model e is_loading — siempre adquirir antes de escribir
    lock: threading.Lock = field(default_factory=threading.Lock)

    def is_recording(self) -> bool:
        """True si hay una grabación activa (PTT o Toggle)."""
        return self.ptt_active or self.toggle_active

    def set_model(self, model: Any) -> None:
        """Thread-safe: asigna el modelo y apaga is_loading."""
        with self.lock:
            self.model = model
            self.is_loading = False

    def clear_model(self) -> None:
        """Thread-safe: descarga el modelo."""
        with self.lock:
            self.model = None
            self.is_loading = False
```

**Nota sobre thread-safety de `ptt_active` / `toggle_active`**: estas variables son leídas en el callback de PortAudio (frecuencia ~50Hz) y escritas desde el thread de pynput. No se usa lock porque: (a) son operaciones atómicas sobre `bool` en CPython (GIL protege), (b) una race condition aquí solo causaría encolar/descartar un chunk de ~20ms de audio — consecuencia mínima, no un crash.

---

## Config Schema

El archivo `config.toml` real que se crea en el directorio raíz del proyecto:

```toml
# config.toml — Configuración de WisprLocal
# Editá este archivo para personalizar el comportamiento.
# Los cambios requieren reiniciar la aplicación.

# ─── Modelo de transcripción ───────────────────────────────────────────────────
[model]
# Nombre del modelo faster-whisper. Opciones: tiny, base, small, medium, large-v2, large-v3
name = "large-v3"

# Dispositivo de inferencia. Usa "cuda" para GPU NVIDIA, "cpu" como fallback.
device = "cuda"

# Tipo de cómputo. "float16" es el más rápido en GPU moderna.
# Opciones: "float16" (GPU), "int8" (CPU o GPU con poca VRAM), "float32" (máxima precisión)
compute_type = "float16"


# ─── Audio ─────────────────────────────────────────────────────────────────────
[audio]
# Frecuencia de muestreo en Hz. Whisper requiere 16000 Hz.
# Opciones válidas: 8000, 16000, 22050, 44100, 48000
sample_rate = 16000

# Número de canales. Whisper espera audio mono.
channels = 1

# Tipo de dato del audio. No cambies esto salvo que sepas lo que hacés.
dtype = "float32"


# ─── Hotkeys ───────────────────────────────────────────────────────────────────
[hotkeys]
# Tecla para Push-to-Talk (mantener presionada para grabar).
# Ejemplos: "caps_lock", "f9", "f12", "scroll_lock"
ptt = "caps_lock"

# Combo para Toggle (presionar una vez para iniciar, otra vez para detener).
# Lista de teclas que deben estar presionadas simultáneamente.
# Ejemplos: ["alt", "shift"], ["ctrl", "f10"], ["f11"]
toggle = ["alt", "shift"]

# Tecla/combo para cargar o descargar el modelo manualmente.
# Dejá vacío [] para deshabilitar esta función.
# Ejemplo: ["ctrl", "alt", "w"]
load_model = []


# ─── Overlay visual ────────────────────────────────────────────────────────────
[overlay]
# Mostrar el indicador visual de grabación. Desactivá si causa problemas.
enabled = true

# Posición del indicador en pantalla.
# Opciones: "bottom-right", "bottom-left", "top-right", "top-left"
position = "bottom-right"

# Opacidad del overlay. 0.0 = invisible, 1.0 = completamente opaco.
opacity = 0.85


# ─── Transcripción ─────────────────────────────────────────────────────────────
[transcription]
# Idioma del audio. null = autodetección (recomendado para uso bilingüe).
# Ejemplos: "es" (español), "en" (inglés), "fr" (francés)
language = null  # null activa la autodetección de faster-whisper

# Prompt inicial para guiar al modelo. Afecta el estilo de transcripción.
# Este prompt bilingüe le indica al modelo que puede recibir español o inglés.
prompt = "Hola, transcribí lo que digo en el idioma en que hablo, ya sea español o inglés."
```

---

## Overlay Implementation

### Por qué tkinter y no otras opciones

| Opción | Por qué descartada |
|--------|-------------------|
| `pygame` | Overhead de 10MB+, requiere SDL, pensado para juegos no UIs pequeñas |
| `PyQt6 / PySide6` | Licencia dual (GPL/comercial), 50MB+, excesivo para un indicador |
| `win32api` directo | Demasiado bajo nivel, requiere gestión manual de mensajes Windows, frágil |
| `wxPython` | Dependencia grande, instalación compleja |
| `tkinter` | Stdlib Python, cero dependencias, suficiente para un label coloreado |

### Implementación concreta de `RecordingOverlay`

```python
# wispr/overlay.py — estructura conceptual

class RecordingOverlay:
    def __init__(self, config: dict):
        self._enabled = config["overlay"]["enabled"]
        self._position = config["overlay"]["position"]
        self._opacity = config["overlay"]["opacity"]
        self._root = None

        if self._enabled:
            # Crear thread dedicado — tkinter corre AQUÍ, no en main thread
            self._thread = threading.Thread(
                target=self._run_tk,
                daemon=True,
                name="overlay-tk"
            )
            self._thread.start()

    def _run_tk(self):
        """Corre en el overlay thread. Crea root y entra en mainloop."""
        self._root = tk.Tk()
        self._root.withdraw()  # Ocultar root window (usamos Toplevel)

        self._window = tk.Toplevel(self._root)
        self._window.overrideredirect(True)           # Sin bordes
        self._window.wm_attributes('-topmost', True)  # Siempre encima
        self._window.wm_attributes('-alpha', self._opacity)
        self._window.withdraw()  # Empieza oculto

        self._label = tk.Label(
            self._window,
            font=("Segoe UI", 12, "bold"),
            padx=12, pady=6
        )
        self._label.pack()
        self._update_position()

        self._root.mainloop()  # BLOQUEA este thread hasta destroy()

    def _update_position(self):
        """Calcula coordenadas según config. Llamar desde overlay thread."""
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        w, h = 160, 40
        margin = 20
        positions = {
            "bottom-right": (sw - w - margin, sh - h - margin - 40),
            "bottom-left":  (margin, sh - h - margin - 40),
            "top-right":    (sw - w - margin, margin),
            "top-left":     (margin, margin),
        }
        x, y = positions[self._position]
        self._window.geometry(f"{w}x{h}+{x}+{y}")

    # ── Métodos públicos: thread-safe via root.after ──────────────────────

    def show_ptt(self):
        if self._root:
            self._root.after(0, self._do_show_ptt)

    def _do_show_ptt(self):
        """Corre en overlay thread."""
        self._label.config(text="● REC PTT", bg="#FF3333", fg="white")
        self._window.deiconify()

    def show_toggle(self):
        if self._root:
            self._root.after(0, self._do_show_toggle)

    def show_loading(self):
        if self._root:
            self._root.after(0, self._do_show_loading)

    def hide(self):
        if self._root:
            self._root.after(0, self._window.withdraw)

    def destroy(self):
        if self._root:
            self._root.after(0, self._root.destroy)
```

### Por qué `root.after(0, fn)` es thread-safe

`tkinter.after()` no ejecuta `fn` inmediatamente — la encola en el event loop de Tk. La próxima iteración del `mainloop()` en el overlay thread la ejecuta. Esto evita condiciones de carrera porque tkinter no es thread-safe para llamadas directas a widgets desde otros threads, pero `after()` sí está diseñado para esto.

### Manejo de los 3 estados visuales

| Estado | Método | Color BG | Texto | Visibilidad |
|--------|--------|----------|-------|-------------|
| idle | `hide()` | N/A | N/A | `window.withdraw()` |
| ptt | `show_ptt()` | `#FF3333` | `● REC PTT` | `window.deiconify()` |
| toggle | `show_toggle()` | `#FF8C00` | `● REC TOGGLE` | `window.deiconify()` |
| loading | `show_loading()` | `#888888` | `⏳ Cargando...` | `window.deiconify()` |

### Limitación documentada

```python
# NOTA: El overlay NO es visible sobre juegos en modo fullscreen exclusivo
# (DirectX exclusive fullscreen). Solo funciona en:
# - Modo ventana (windowed)
# - Modo borderless windowed
# - El escritorio de Windows
# Para uso en juegos, recomendamos desactivar el overlay en config.toml
# y confiar únicamente en el feedback auditivo (beeps).
```

---

## Installer Flow

### Diagrama de pasos

```
python install.py
        │
        ▼
┌─────────────────────────────────────────────────────┐
│ [1/6] Verificando Python...                         │
│   sys.version_info >= (3, 12)?                      │
│   NO → print error + URL + sys.exit(1)              │
│   SÍ → continuar                                    │
└──────────────────────┬──────────────────────────────┘
                       │
        ▼
┌─────────────────────────────────────────────────────┐
│ [2/6] Detectando GPU NVIDIA...                      │
│   subprocess.run(['nvidia-smi',                     │
│     '--query-gpu=name', '--format=csv,noheader'])   │
│   Falla o output vacío → gpu_detected = False       │
│   Tiene output → gpu_detected = True, print nombre  │
└──────────────────────┬──────────────────────────────┘
                       │
        ▼
┌─────────────────────────────────────────────────────┐
│ [3/6] Creando entorno virtual...                    │
│   venv.create('.venv', with_pip=True)               │
│   Ya existe → preguntar si recrear o reutilizar     │
│   Verificar: .venv/Scripts/python.exe existe        │
└──────────────────────┬──────────────────────────────┘
                       │
        ▼
┌─────────────────────────────────────────────────────┐
│ [4/6] Instalando PyTorch...                         │
│   Si gpu_detected:                                  │
│     pip install torch                               │
│       --index-url https://download.pytorch.org/     │
│       whl/cu121                                     │
│   Si NO gpu_detected:                               │
│     pip install torch                               │
│     (PyPI default = CPU build)                      │
└──────────────────────┬──────────────────────────────┘
                       │
        ▼
┌─────────────────────────────────────────────────────┐
│ [5/6] Instalando dependencias...                    │
│   pip install -r requirements.txt                   │
│   (faster-whisper, sounddevice, numpy,              │
│    pynput, pystray, Pillow, pyperclip)              │
└──────────────────────┬──────────────────────────────┘
                       │
        ▼
┌─────────────────────────────────────────────────────┐
│ [6/6] Generando archivos de configuración...        │
│   a) Si no existe config.toml → crear con defaults  │
│      (llamando a wispr.config.load_config()         │
│       desde el venv recién creado, O copiando       │
│       template hardcodeado en install.py)           │
│   b) Generar lanzador.vbs con rutas absolutas:      │
│      project_dir = Path(__file__).parent.resolve()  │
│      pythonw = project_dir / ".venv/Scripts/        │
│                pythonw.exe"                         │
│   c) Preguntar startup automático [s/N]             │
│      Si 's': copiar lanzador.vbs a                  │
│      %APPDATA%\Microsoft\Windows\Start Menu\        │
│      Programs\Startup\                              │
└──────────────────────┬──────────────────────────────┘
                       │
        ▼
┌─────────────────────────────────────────────────────┐
│ RESUMEN FINAL                                       │
│ ✓ Python 3.12.x detectado                          │
│ ✓ GPU: NVIDIA GeForce RTX 3070 (o "CPU only")      │
│ ✓ Entorno virtual: C:\...\WisprLocal\.venv\         │
│ ✓ Dependencias instaladas                           │
│ ✓ Startup automático: SÍ / NO                       │
│                                                     │
│ Para iniciar WisprLocal:                            │
│   Doble clic en lanzador.vbs                        │
│   O ejecutar: .venv\Scripts\pythonw.exe -m wispr    │
└─────────────────────────────────────────────────────┘
```

### Template de `lanzador.vbs` generado

```vbscript
' lanzador.vbs — Generado por install.py
' Lanza WisprLocal sin ventana de consola
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """C:\Users\Usuario\Documents\WisprLocal\.venv\Scripts\pythonw.exe"" -m wispr", 0, False
```

Las rutas se generan dinámicamente con `Path(__file__).parent.resolve()` en `install.py` — nunca hardcodeadas.

---

## Architecture Decision Records

#### ADR-01: pystray en main thread, tkinter en thread dedicado

**Decisión**: `pystray.Icon.run()` bloquea el main thread. `tkinter` corre en su propio thread daemon.

**Razón**: `pystray` en Windows usa `win32gui` para la ventana de mensajes del tray. Esta ventana DEBE existir en el thread que crea el message pump (main thread). Correrlo en un thread secundario produce menús no-funcionales y pérdida de eventos. `tkinter` no requiere el main thread específicamente — solo requiere que todos los widgets de una instancia `Tk()` se manejen desde el thread donde fue creada. Crear `Tk()` en un thread dedicado satisface esta restricción.

**Alternativas descartadas**: 
- Tkinter en main thread: imposible, pystray necesita el main thread en Windows
- pystray en thread secundario: probado en MVP, los eventos de ícono se pierden esporádicamente
- Eliminar pystray, usar solo tkinter: perdemos el tray icon nativo de Windows

**Consecuencias**: Los updates del overlay DEBEN ir via `root.after(0, fn)` — nunca llamadas directas a widgets desde otros threads.

#### ADR-02: tomllib (stdlib) en lugar de PyYAML

**Decisión**: Configuración en TOML parseada con `tomllib` (stdlib Python 3.12).

**Razón**: `tomllib` está disponible sin instalación en Python 3.12+. Elimina una dependencia del proyecto. TOML tiene mejor soporte de tipos (arrays, inline tables) que YAML para este caso de uso.

**Alternativas descartadas**:
- PyYAML: dependencia extra, conocido por comportamientos sorpresivos con tipos (YAML 1.1 vs 1.2)
- JSON: sin soporte de comentarios (crítico para un archivo de config editable por el usuario)
- INI/configparser: tipos de datos limitados, no soporta listas nativas

**Consecuencias**: Requiere Python 3.12+. El instalador debe verificar la versión antes de proceder.

#### ADR-03: tkinter para overlay en lugar de pygame/PyQt/win32api

**Decisión**: Usar `tkinter` (stdlib) para el indicador visual.

**Razón**: Cero dependencias extra, viene con Python, suficiente para un label coloreado en una ventana pequeña.

**Alternativas descartadas**:
- `pygame`: 10MB+, overhead de SDL, pensado para juegos no para overlays de UI
- `PyQt6`: licencia GPL/comercial, 50MB+, excesivo para este caso
- `win32api` directo: requiere `pywin32` (dependencia extra), extremadamente verboso para algo simple
- `wxPython`: dependencia grande, instalación compleja en algunos setups Windows

**Consecuencias**: El overlay no funciona sobre juegos en fullscreen exclusivo. Documentar claramente.

#### ADR-04: PortAudio stream siempre activo

**Decisión**: El `sounddevice.InputStream` se abre al arrancar y permanece abierto siempre. El callback descarta audio cuando no se está grabando.

**Razón**: Abrir/cerrar el stream en cada grabación introduce latencia perceptible (~200-500ms de inicialización de PortAudio). Un stream siempre activo añade ~2-5MB de RAM pero elimina la latencia de inicio.

**Alternativas descartadas**: Abrir stream on-demand al presionar PTT: latencia de inicio, riesgo de que el stream no esté listo cuando el usuario ya empezó a hablar.

**Consecuencias**: El callback de PortAudio se ejecuta cada ~20ms siempre. Debe ser extremadamente liviano (O(1), sin locks, sin allocaciones).

#### ADR-05: Inyección via pyperclip + Ctrl+V

**Decisión**: Copiar texto al clipboard con `pyperclip` y simular Ctrl+V con `pynput`.

**Razón**: Es el único método que maneja correctamente caracteres especiales del español (tildes, ñ, ¿, ¡) en cualquier aplicación Windows. La alternativa (`pynput.keyboard.type()`) simula teclas individuales y falla con caracteres fuera del layout activo del teclado.

**Alternativas descartadas**:
- `pynput.keyboard.type()`: falla con caracteres especiales si el layout de teclado no los tiene directamente
- `win32api.SendMessage(WM_CHAR)`: requiere handle de ventana, no funciona en todos los contextos
- Portapapeles sin restaurar: el usuario pierde lo que tenía copiado

**Consecuencias**: Se restaura el clipboard previo después de pegar. Un delay de 100ms antes de Ctrl+V es necesario para dar tiempo al foco.

#### ADR-06: requirements.txt en lugar de pyproject.toml

**Decisión**: Usar `requirements.txt` simple para dependencias.

**Razón**: El público objetivo no son desarrolladores Python. `requirements.txt` es universalmente conocido y el instalador puede hacer `pip install -r requirements.txt` directamente sin conocer packaging Python.

**Alternativas descartadas**:
- `pyproject.toml`: mejor práctica moderna, pero el instalador necesitaría llamar `pip install -e .` en lugar del flujo actual, confundiendo a usuarios no-técnicos

**Consecuencias**: Sin gestión de dependencias de desarrollo separada. Agregar `pyproject.toml` como mejora futura.

#### ADR-07: Sentinel None en audio_queue para señalizar fin de grabación

**Decisión**: Cuando PTT se suelta (o Toggle se desactiva), se encola `None` en `audio_queue`. El `transcription_worker` usa este sentinel para saber que la grabación terminó y debe procesar el buffer.

**Razón**: Alternativas como un `threading.Event` o una segunda queue complicarían el diseño. La convención de sentinel `None` en queues es un patrón Python estándar y explícito.

**Consecuencias**: El `transcription_worker` NUNCA debe hacer `queue.get()` después de ver `None` sin primero limpiar el buffer acumulado — de lo contrario el siguiente `None` pertenecería a otra grabación.

---

## Implementation Phases

### Fase 1: Refactor estructural (commit: `refactor: modularize mvp into wispr/ package`)

**Objetivo**: Crear la estructura de módulos sin cambiar comportamiento. Al final de esta fase, `python -m wispr` debe funcionar IGUAL que `python mvp_local.py`.

**Pasos**:
1. Crear `v0.1.0-mvp` git tag (proteger el MVP)
2. Crear directorio `wispr/` con `__init__.py`
3. Crear `wispr/state.py` — extraer variables globales en `AppState`
4. Crear `wispr/sounds.py` — extraer los `winsound.Beep` hardcodeados
5. Crear `wispr/injection.py` — extraer la lógica de pyperclip + Ctrl+V
6. Crear `wispr/audio.py` — extraer InputStream y callback
7. Crear `wispr/transcription.py` — extraer load_model, unload, transcription_worker
8. Crear `wispr/hotkeys.py` — extraer listener (hotkeys aún hardcodeadas)
9. Crear `wispr/tray.py` — extraer pystray setup
10. Crear `wispr/overlay.py` — overlay mínimo (sin config aún)
11. Crear `wispr/__main__.py` — composition root que conecta todo
12. Mover `mvp_local.py` → `tools/mvp_original.py`
13. Mover scripts de prueba a `tools/`
14. Verificar manualmente que la app funciona igual que antes

**Criterio de éxito**: PTT funciona, Toggle funciona, transcripción funciona, tray funciona.

### Fase 2: Config TOML (commit: `feat: add config.toml and wispr/config.py`)

**Objetivo**: Externalizar toda configuración hardcodeada.

**Pasos**:
1. Crear `wispr/config.py` con `load_config()`, schema completo, validaciones
2. Crear `config.toml` con todos los defaults y comentarios
3. Actualizar `__main__.py` para cargar config al arrancar
4. Actualizar `hotkeys.py` para leer teclas desde config (eliminar hardcoding)
5. Actualizar `audio.py` para leer sample_rate/channels/dtype desde config
6. Actualizar `transcription.py` para leer model/device/compute_type desde config
7. Crear `requirements.txt` con dependencias exactas
8. Verificar: cambiar `ptt = "f9"` en config.toml y confirmar que funciona

**Criterio de éxito**: Toda personalización posible sin tocar código Python.

### Fase 3: Overlay visual (commit: `feat: add recording overlay (tkinter)`)

**Objetivo**: Indicador visual de grabación siempre-encima.

**Pasos**:
1. Implementar `RecordingOverlay` completo con los 4 estados (idle/ptt/toggle/loading)
2. Thread dedicado para tkinter, `root.after()` para updates thread-safe
3. Posicionamiento configurable via config.toml
4. Integrar con hotkeys.py (llamar show_ptt/hide en on_press/on_release)
5. Integrar con transcription.py (llamar show_loading durante carga del modelo)
6. Verificar: overlay aparece al grabar, desaparece al soltar, no bloquea la app

**Criterio de éxito**: Indicador visible sobre navegadores y editores en windowed mode. No visible en fullscreen exclusivo (documentar).

### Fase 4: Hotkeys configurables (commit: `feat: configurable hotkeys via config.toml`)

**Objetivo**: El usuario puede cambiar cualquier tecla sin tocar código.

**Pasos**:
1. Implementar `resolve_key()` en `hotkeys.py` — mapear strings de config a objetos pynput
2. Validar teclas al arrancar (lanzar `ValueError` si no reconocida)
3. Soporte para combos (lista de teclas)
4. Soporte para tecla de carga/descarga de modelo (si `load_model` no vacío)
5. Warning en log si hotkeys conflictan con Windows (Win+L, Ctrl+Alt+Del)
6. Verificar con configuraciones no-default (F9, Ctrl+F10, etc.)

**Criterio de éxito**: Cambiar `ptt = "f9"` en config.toml y funciona correctamente.

### Fase 5: Instalador (commit: `feat: add install.py automated installer`)

**Objetivo**: Instalación de 3 pasos sin tocar código.

**Pasos**:
1. Implementar `install.py` completo (solo stdlib)
2. Verificación de Python 3.12+
3. Detección de GPU via nvidia-smi
4. Creación de venv + instalación de dependencias
5. Generación dinámica de `lanzador.vbs` con rutas absolutas
6. Pregunta de startup automático
7. Resumen final con instrucciones
8. Eliminar `lanzador - Shortcut.lnk` del repo
9. Actualizar `.gitignore` (`.venv/`, `*.log`, `__pycache__/`, `openspec/`, `.atl/`)
10. Probar instalación limpia desde cero en una máquina de prueba

**Criterio de éxito**: `python install.py` → doble clic en lanzador.vbs → funciona. Sin tocar más nada.

### Fase 6: Documentación + limpieza (commit: `docs: rewrite README with full documentation`)

**Objetivo**: Proyecto listo para uso público.

**Pasos**:
1. Reescribir `README.md` completo (badges, instalación 3 pasos, arquitectura, troubleshooting)
2. Agregar sección de Configuración con schema comentado
3. Agregar sección de Troubleshooting (5+ casos)
4. Agregar sección de Arquitectura con árbol de módulos
5. Agregar sección de Contribuir (setup de desarrollo)
6. Revisar y limpiar docstrings en todos los módulos
7. Verificar que `.gitignore` es correcto
8. Tag `v1.0.0` al finalizar

**Criterio de éxito**: Un usuario nuevo con Python 3.12 y GPU NVIDIA puede instalar y usar WisprLocal siguiendo solo el README.

---

## Risks y Mitigaciones

| Riesgo | Fase | Mitigación |
|--------|------|-----------|
| tkinter root.after() no ejecuta si mainloop no corrió aún | 3 | Iniciar overlay thread antes de cualquier llamada a show_*(). Agregar guard: if self._root is None: return |
| pystray no responde en thread secundario | 1 | pystray.Icon.run() SIEMPRE en main thread. Verificar en fase 1 antes de continuar |
| PortAudio callback hace GIL-blocking call | 4 | Callback solo hace queue.put_nowait() y lectura de bool — O(1), nunca bloquea |
| Sentinel None perdido si PTT doble-click rápido | 4 | state.audio_queue es una Queue FIFO — los sentinels llegan en orden correcto |
| install.py falla en Python 3.12 con venv ya existente | 5 | Detectar .venv/ existente, preguntar al usuario si sobrescribir o reutilizar |
| Overlay thread zombie si tkinter lanza excepción | 3 | try/except en _run_tk(), log del error, self._root = None para desactivar métodos |
