# Spec: wispr-local-v1

## Overview

Transformar `mvp_local.py` (un único archivo de 170 líneas con hotkeys hardcoded) en un proyecto open-source modular con overlay visual, configuración externalizada, instalador automático y documentación profesional — todo sin dependencias extra más allá de las ya requeridas.

---

## Functional Requirements

### FR-01: Arquitectura Modular — Paquete `wispr/`

**Priority**: Must Have
**Module**: Todos los módulos del paquete

**Requirements**:
- MUST existir un directorio `wispr/` con `__init__.py` que lo declare como paquete Python.
- MUST contener exactamente estos módulos: `__main__.py`, `state.py`, `config.py`, `audio.py`, `transcription.py`, `hotkeys.py`, `overlay.py`, `tray.py`, `injection.py`, `sounds.py`.
- SHALL estructurarse según el siguiente árbol:
  ```
  wispr/
  ├── __init__.py
  ├── __main__.py
  ├── state.py
  ├── config.py
  ├── audio.py
  ├── transcription.py
  ├── hotkeys.py
  ├── overlay.py
  ├── tray.py
  ├── injection.py
  └── sounds.py
  config.toml
  install.py
  requirements.txt
  README.md
  tools/
  ├── mvp_original.py
  ├── verificar_gpu.py
  ├── prueba_mic_hotkey.py
  └── test_transcripcion.py
  ```
- MUST que cada módulo tenga UNA sola responsabilidad (Single Responsibility Principle).
- MUST que ningún módulo importe directamente a otro módulo peer excepto a través de parámetros o `AppState`. La única excepción permitida es que `__main__.py` importe a todos los módulos como composition root.
- SHOULD que cada módulo sea importable de forma aislada sin efectos secundarios (no ejecutar código al importar).
- MUST preservar `mvp_local.py` original como `tools/mvp_original.py` hasta que el refactor esté verificado manualmente.
- MUST mover `prueba_mic_hotkey.py`, `test_transcripcion.py`, `verificar_gpu.py` al directorio `tools/`.
- MUST eliminar `lanzador - Shortcut.lnk` del repo (archivo binario sin valor en control de versiones).
- MAY mantener comentarios bilingues (español/inglés) en el código fuente.

**Scenarios**:

#### Scenario: Arranque desde lanzador
- **Given**: El usuario hace doble clic en `lanzador.vbs` generado por `install.py`
- **When**: El sistema ejecuta `pythonw.exe -m wispr`
- **Then**: La aplicación arranca sin ventana de consola, el ícono aparece en system tray, y el sistema queda listo para recibir hotkeys

#### Scenario: Estructura de archivos post-instalación
- **Given**: El instalador ha completado exitosamente
- **When**: Se lista el directorio raíz del proyecto
- **Then**: Existen `wispr/`, `config.toml`, `install.py`, `requirements.txt`, `README.md`, `tools/`, `.venv/` — y NO existe `mvp_local.py` en la raíz (está en `tools/mvp_original.py`)

#### Scenario: Módulo importable sin efectos secundarios
- **Given**: El paquete está instalado en el venv
- **When**: Se ejecuta `python -c "from wispr import config"` en el venv
- **Then**: No ocurre ningún error, no se abre ninguna ventana, no se inicia ningún thread

---

### FR-02: Estado Compartido — `AppState`

**Priority**: Must Have
**Module**: `wispr/state.py`

**Requirements**:
- MUST definir una clase `AppState` usando `@dataclass`.
- MUST contener los siguientes campos con sus tipos y valores por defecto:
  ```python
  ptt_active: bool = False
  toggle_active: bool = False
  model: Any = None          # referencia al WhisperModel cargado, o None
  is_loading: bool = False   # True mientras el modelo se está cargando
  overlay_enabled: bool = True
  audio_queue: queue.Queue = field(default_factory=queue.Queue)
  ```
- SHALL incluir un campo `lock: threading.Lock` para operaciones thread-safe sobre `model` e `is_loading`.
- MUST que `AppState` no tenga dependencias de ningún otro módulo del paquete.
- SHOULD que `AppState` sea el único mecanismo de comunicación de estado entre módulos — NO variables globales de módulo.
- MAY agregar métodos helpers simples como `is_recording() -> bool` que retorne `ptt_active or toggle_active`.

**Scenarios**:

#### Scenario: Estado inicial al arrancar
- **Given**: La aplicación inicia
- **When**: Se instancia `AppState()`
- **Then**: `ptt_active` es `False`, `toggle_active` es `False`, `model` es `None`, `is_loading` es `False`, `overlay_enabled` es `True`

#### Scenario: Acceso thread-safe al modelo
- **Given**: Un thread de hotkeys quiere cambiar `ptt_active` mientras el thread de transcripción lee `model`
- **When**: Ambos acceden al `AppState` compartido simultáneamente
- **Then**: No ocurre race condition — el `lock` protege las escrituras a `model` e `is_loading`

---

### FR-03: Configuración — `config.toml` y `wispr/config.py`

**Priority**: Must Have
**Module**: `wispr/config.py`

**Requirements**:
- MUST usar `tomllib` (stdlib Python 3.12) para parsear la configuración — no PyYAML ni dependencias externas.
- MUST que `config.toml` exista en el directorio raíz del proyecto (junto a `wispr/`).
- MUST que `wispr/config.py` exporte una función `load_config(path: str = "config.toml") -> dict` que retorne la configuración mergeada con defaults.
- MUST aplicar el siguiente schema con defaults:
  ```toml
  [model]
  name = "large-v3"          # nombre del modelo faster-whisper
  device = "cuda"            # "cuda" o "cpu"
  compute_type = "float16"   # "float16", "int8", "float32"

  [audio]
  sample_rate = 16000        # Hz — requerido por Whisper
  channels = 1               # mono
  dtype = "float32"

  [hotkeys]
  ptt = "caps_lock"          # tecla push-to-talk
  toggle = ["alt", "shift"]  # combo para toggle mode (lista de teclas)
  load_model = []            # tecla/combo para cargar/descargar modelo (vacío = desactivado)

  [overlay]
  enabled = true
  position = "bottom-right"  # "bottom-right", "bottom-left", "top-right", "top-left"
  opacity = 0.85             # 0.0 a 1.0

  [transcription]
  language = null            # null = autodetección, o "es", "en", etc.
  prompt = "Hola, transcribí lo que digo en el idioma en que hablo, ya sea español o inglés."
  ```
- MUST que si `config.toml` no existe, `load_config()` cree el archivo con los valores default y retorne el dict de defaults (NO lanzar excepción).
- MUST que si un campo obligatorio tiene un valor inválido (ej: `device = "tpu"`), `load_config()` lance `ValueError` con un mensaje descriptivo que indique el campo y los valores aceptados.
- SHOULD que valores faltantes en un `config.toml` parcial sean completados con defaults (merge profundo).
- MUST que `config.py` valide los siguientes invariantes:
  - `device` ∈ `{"cuda", "cpu"}`
  - `compute_type` ∈ `{"float16", "int8", "float32"}`
  - `overlay.position` ∈ `{"bottom-right", "bottom-left", "top-right", "top-left"}`
  - `overlay.opacity` ∈ `[0.0, 1.0]`
  - `audio.sample_rate` ∈ `{8000, 16000, 22050, 44100, 48000}`
- MUST que `config.py` emita un `logging.warning` (no excepción) si detecta que `hotkeys.ptt` o `hotkeys.toggle` usan combinaciones reservadas de Windows (`win+l`, `ctrl+alt+del`).

**Scenarios**:

#### Scenario: Primera ejecución sin config.toml
- **Given**: No existe `config.toml` en el directorio de trabajo
- **When**: Se llama `load_config()`
- **Then**: Se crea `config.toml` con todos los valores default, la función retorna el dict de defaults, y no se lanza ninguna excepción

#### Scenario: Config parcial — solo hotkeys definidas
- **Given**: `config.toml` contiene solo la sección `[hotkeys]` con `ptt = "f9"`
- **When**: Se llama `load_config()`
- **Then**: Retorna un dict donde `hotkeys.ptt = "f9"` y todos los demás campos tienen sus valores default

#### Scenario: Valor inválido en device
- **Given**: `config.toml` contiene `[model]` con `device = "tpu"`
- **When**: Se llama `load_config()`
- **Then**: Se lanza `ValueError` con mensaje que incluya "device" y los valores aceptados `["cuda", "cpu"]`

#### Scenario: Recarga en caliente (futuro — documentar como no soportado en v1)
- **Given**: El usuario edita `config.toml` mientras la app está corriendo
- **When**: El usuario reinicia la app (cierra y abre desde tray o relanza `lanzador.vbs`)
- **Then**: La nueva configuración es aplicada — en v1 NO se soporta recarga sin reinicio

---

### FR-04: Overlay Visual — `wispr/overlay.py`

**Priority**: Must Have
**Module**: `wispr/overlay.py`

**Requirements**:
- MUST implementar la clase `RecordingOverlay` usando `tkinter.Toplevel`.
- MUST que la ventana sea siempre-encima (`wm_attributes('-topmost', True)`), sin bordes (`overrideredirect(True)`), y con transparencia configurable (`wm_attributes('-alpha', opacity)`).
- MUST soportar los siguientes estados visuales:
  - **idle**: overlay oculto (no visible)
  - **ptt**: overlay visible con fondo rojo (`#FF3333`) y texto "● REC PTT"
  - **toggle**: overlay visible con fondo naranja (`#FF8C00`) y texto "● REC TOGGLE"
  - **loading**: overlay visible con fondo gris (`#888888`) y texto "⏳ Cargando..."
- MUST que el overlay aparezca en la posición configurada en `config.toml`:
  - `bottom-right`: esquina inferior derecha con margen de 20px
  - `bottom-left`: esquina inferior izquierda con margen de 20px
  - `top-right`: esquina superior derecha con margen de 20px
  - `top-left`: esquina superior izquierda con margen de 20px
- MUST que `RecordingOverlay` exponga los métodos: `show_ptt()`, `show_toggle()`, `show_loading()`, `hide()`, `destroy()`.
- MUST que todos los métodos públicos sean thread-safe — usar `self.root.after(0, ...)` para operaciones desde threads externos.
- MUST que si `overlay.enabled = false` en config, `RecordingOverlay` opere en modo no-op (todos los métodos son vacíos, no se crea ventana tkinter).
- SHOULD calcular la posición del overlay en base al tamaño real de la pantalla usando `winfo_screenwidth()` / `winfo_screenheight()`.
- SHALL correr en un thread dedicado (`threading.Thread(daemon=True)`) para no bloquear el event loop principal.
- MAY implementar un efecto de pulsación (fade in/out) en estado PTT, con intervalo de 600ms como valor razonable.
- MUST documentar en comentarios que el overlay NO es visible sobre juegos en fullscreen exclusivo — solo en windowed/borderless.

**Scenarios**:

#### Scenario: Overlay aparece al activar PTT
- **Given**: La app está en estado idle y el overlay está habilitado
- **When**: El usuario presiona la tecla PTT (por defecto CapsLock)
- **Then**: El overlay aparece en la esquina configurada (default bottom-right) con fondo rojo y texto "● REC PTT"

#### Scenario: Overlay cambia al liberar PTT
- **Given**: El overlay está mostrando estado PTT
- **When**: El usuario suelta la tecla PTT
- **Then**: El overlay se oculta (estado idle) — si no hay toggle activo

#### Scenario: Overlay en modo toggle
- **Given**: La app está en estado idle
- **When**: El usuario presiona el combo toggle (por defecto Alt+Shift)
- **Then**: El overlay aparece con fondo naranja y texto "● REC TOGGLE" y permanece visible hasta que se presione toggle nuevamente

#### Scenario: Overlay deshabilitado en config
- **Given**: `config.toml` tiene `[overlay] enabled = false`
- **When**: El usuario presiona PTT
- **Then**: No aparece ninguna ventana overlay — el sistema funciona normalmente pero sin indicador visual

#### Scenario: Overlay durante carga del modelo
- **Given**: El modelo no está cargado y `is_loading = True`
- **When**: `show_loading()` es llamado
- **Then**: El overlay muestra fondo gris con texto "⏳ Cargando..."

---

### FR-05: Hotkeys Configurables — `wispr/hotkeys.py`

**Priority**: Must Have
**Module**: `wispr/hotkeys.py`

**Requirements**:
- MUST usar `pynput.keyboard` para el listener de teclado.
- MUST leer la configuración de hotkeys desde el `AppState` (que la tiene desde `config.toml`) — NO hardcodear teclas.
- MUST soportar los siguientes tipos de binding:
  - **Tecla simple**: string como `"caps_lock"`, `"f9"`, `"f12"` — se mapea a `pynput.keyboard.Key.*` o `pynput.keyboard.KeyCode.from_char()`
  - **Combo**: lista como `["alt", "shift"]` — activa cuando todas las teclas del combo están presionadas simultáneamente
- MUST implementar la siguiente lógica para PTT:
  - `on_press(ptt_key)` → `state.ptt_active = True`, llama `overlay.show_ptt()`, inicia captura de audio
  - `on_release(ptt_key)` → `state.ptt_active = False`, llama `overlay.hide()`, dispara transcripción
- MUST implementar la siguiente lógica para Toggle:
  - Primera presión del combo → `state.toggle_active = True`, llama `overlay.show_toggle()`, inicia captura
  - Segunda presión del combo → `state.toggle_active = False`, llama `overlay.hide()`, dispara transcripción
- MUST que si `state.model is None` y `state.is_loading is False` al momento de presionar PTT o Toggle, se emita un beep de error (via `sounds`) y se registre en log `"Modelo no cargado"` — NO intentar transcribir.
- MUST que si `state.is_loading is True` al presionar una hotkey de grabación, se ignore silenciosamente.
- SHOULD que el listener corra en su propio thread (pynput lo hace por defecto).
- MUST que `hotkeys.py` exponga `start_listener(state, config, overlay, sounds) -> pynput.keyboard.Listener`.
- MAY soportar tecla/combo de carga/descarga de modelo si `config.hotkeys.load_model` no está vacío.
- MUST que si una tecla configurada no es reconocida por pynput, se lance `ValueError` con el nombre de la tecla inválida al iniciar el listener.

**Scenarios**:

#### Scenario: PTT con modelo cargado
- **Given**: `state.model` no es None, `state.ptt_active = False`
- **When**: El usuario presiona CapsLock (configuración default)
- **Then**: `state.ptt_active` pasa a `True`, el overlay muestra estado PTT, el audio empieza a capturarse en `state.audio_queue`

#### Scenario: PTT con modelo no cargado
- **Given**: `state.model is None` y `state.is_loading is False`
- **When**: El usuario presiona CapsLock
- **Then**: Suena un beep de error, se loguea `"Modelo no cargado — presioná PTT cuando el modelo esté listo"`, NO se activa grabación

#### Scenario: Toggle on/off
- **Given**: `state.model` no es None, `state.toggle_active = False`
- **When**: El usuario presiona Alt+Shift (configuración default)
- **Then**: `state.toggle_active` pasa a `True`, overlay muestra toggle, audio empieza a capturarse

#### Scenario: Tecla inválida en config
- **Given**: `config.toml` tiene `ptt = "supr_izq"` (tecla no reconocida por pynput)
- **When**: La app intenta iniciar el listener de teclado
- **Then**: Se lanza `ValueError` con mensaje `"Hotkey no reconocida: 'supr_izq'"` y la app loguea el error claramente

---

### FR-06: Captura de Audio — `wispr/audio.py`

**Priority**: Must Have
**Module**: `wispr/audio.py`

**Requirements**:
- MUST usar `sounddevice.InputStream` para captura de audio.
- MUST configurar el stream con los valores de `config.audio`: `samplerate`, `channels`, `dtype`.
- MUST que el callback del stream encole chunks de audio en `state.audio_queue` SOLAMENTE cuando `state.ptt_active or state.toggle_active` es `True`.
- MUST que `audio.py` exponga `start_stream(state, config) -> sounddevice.InputStream`.
- MUST que al detener la grabación (PTT release o Toggle off), `audio.py` agregue un sentinel (`None`) a `state.audio_queue` para señalizar fin de grabación al thread de transcripción.
- SHOULD que el stream de audio esté siempre activo (abierto) una vez que la app arranca — la selectividad es via la condición en el callback, no abriendo/cerrando el stream en cada grabación.
- MUST manejar `sounddevice.PortAudioError` en el arranque con mensaje claro: `"No se detectó micrófono. Verificá que tenés un micrófono conectado."`.

**Scenarios**:

#### Scenario: Captura durante PTT
- **Given**: El stream de audio está activo, `state.ptt_active = False`
- **When**: `state.ptt_active` pasa a `True` y llegan chunks del micrófono
- **Then**: Los chunks son encolados en `state.audio_queue`

#### Scenario: No captura en idle
- **Given**: El stream de audio está activo, `state.ptt_active = False`, `state.toggle_active = False`
- **When**: Hay audio entrando por el micrófono (ej: sonido ambiental)
- **Then**: Los chunks NO son encolados — `state.audio_queue` permanece vacía

#### Scenario: Señal de fin de grabación
- **Given**: El usuario estaba grabando con PTT y suelta la tecla
- **When**: `state.ptt_active` pasa a `False`
- **Then**: `None` es agregado a `state.audio_queue` para que el thread de transcripción sepa que terminó la grabación

---

### FR-07: Transcripción — `wispr/transcription.py`

**Priority**: Must Have
**Module**: `wispr/transcription.py`

**Requirements**:
- MUST usar `faster_whisper.WhisperModel` para la transcripción.
- MUST exponer `load_model(state, config)` que: cargue el modelo en `state.model`, setee `state.is_loading = True` al empezar y `False` al terminar, use `state.lock` para thread-safety.
- MUST exponer `unload_model(state)` que: libere `state.model`, llame `gc.collect()` y `torch.cuda.empty_cache()`, setee `state.model = None`.
- MUST exponer `transcription_worker(state, config, injection_fn, sounds)` que corra en un thread dedicado, consuma `state.audio_queue`, y para cada grabación completa:
  1. Concatene todos los chunks hasta el sentinel `None`
  2. Verifique que el audio no sea vacío o muy corto (< 0.3 segundos a la sample_rate configurada)
  3. Transcribe con el prompt de `config.transcription.prompt`
  4. Si hay texto, llama `injection_fn(text)`
  5. Llama `sounds.play_ready()`
- MUST que si `state.model is None` cuando llega un sentinel, `transcription_worker` descarte el audio acumulado y loguee `"Modelo no disponible — audio descartado"`.
- MUST que si el audio acumulado tiene menos de `int(0.3 * sample_rate)` frames, se descarte sin transcribir y se loguee `"Audio demasiado corto — descartado"`.
- MUST que si `faster_whisper` lanza una excepción durante la transcripción, se capture, se loguee el error completo, y la app continúe sin crashear.
- MUST usar el prompt bilingüe de config como `initial_prompt` en la llamada a `model.transcribe()`.
- SHOULD que `load_model` corra en un `threading.Thread` para no bloquear el arranque de la app.
- MUST que al cargar el modelo exitosamente, se llame `sounds.play_ready()` para indicar al usuario que está listo.
- SHOULD especificar `language=None` en `transcribe()` cuando `config.transcription.language` es null (autodetección).

**Scenarios**:

#### Scenario: Transcripción exitosa bilingüe
- **Given**: El modelo está cargado, el usuario dictó "Hello, this is a test"
- **When**: El sentinel `None` llega a la queue y `transcription_worker` procesa el audio
- **Then**: El texto transcripto es inyectado en la aplicación activa, suena beep de listo

#### Scenario: Audio demasiado corto
- **Given**: El modelo está cargado, el usuario presionó y soltó PTT muy rápido (< 0.3 segundos)
- **When**: `transcription_worker` procesa el audio
- **Then**: El audio es descartado sin transcribir, se loguea "Audio demasiado corto — descartado", NO se inyecta texto

#### Scenario: Modelo no disponible al transcribir
- **Given**: `state.model is None` (modelo no cargado o descargado)
- **When**: El sentinel `None` llega a `state.audio_queue`
- **Then**: El audio acumulado es descartado, se loguea el error, la app sigue corriendo

#### Scenario: Carga del modelo con feedback auditivo
- **Given**: La app inicia y el modelo empieza a cargar
- **When**: El modelo termina de cargar exitosamente
- **Then**: Suena el beep de listo (`sounds.play_ready()`), `state.model` apunta al `WhisperModel` cargado, `state.is_loading = False`

---

### FR-08: Inyección de Texto — `wispr/injection.py`

**Priority**: Must Have
**Module**: `wispr/injection.py`

**Requirements**:
- MUST usar `pyperclip` para copiar el texto al clipboard.
- MUST simular `Ctrl+V` usando `pynput.keyboard.Controller` para pegar el texto en la aplicación activa.
- MUST exponer `inject_text(text: str, delay_ms: int = 100) -> None`.
- MUST que si `text` es una cadena vacía o solo espacios, `inject_text` retorne sin hacer nada (no paste vacío).
- MUST aplicar un delay de `delay_ms` milisegundos ANTES de simular `Ctrl+V` — esto permite que la app destino tenga foco. Default: 100ms.
- SHOULD restaurar el contenido previo del clipboard después de pegar — leer clipboard antes, pegar, restaurar.
- MUST manejar excepciones de `pyperclip` (ej: clipboard no disponible) con log de error y sin crashear la app.
- MAY agregar un segundo delay de 50ms entre `Ctrl down` y `V` para aplicaciones lentas, y 50ms entre `V` y `Ctrl up`.

**Scenarios**:

#### Scenario: Inyección exitosa con caracteres especiales
- **Given**: El texto transcripto es "Buenos días, ¿cómo estás?"
- **When**: `inject_text("Buenos días, ¿cómo estás?")` es llamado
- **Then**: El texto aparece en la aplicación activa con los caracteres especiales correctos (tilde, ñ, ¿)

#### Scenario: Texto vacío no inyecta
- **Given**: La transcripción retornó una cadena vacía `""`
- **When**: `inject_text("")` es llamado
- **Then**: No se modifica el clipboard, no se simula Ctrl+V, la función retorna silenciosamente

#### Scenario: Clipboard restaurado post-inyección
- **Given**: El clipboard tiene "texto previo importante" antes de la transcripción
- **When**: `inject_text("nuevo texto")` es llamado y completa
- **Then**: El clipboard contiene "texto previo importante" (restaurado), y "nuevo texto" fue pegado en la app activa

---

### FR-09: Feedback Auditivo — `wispr/sounds.py`

**Priority**: Should Have
**Module**: `wispr/sounds.py`

**Requirements**:
- MUST usar `winsound.Beep(frequency, duration)` — no archivos de audio externos, no dependencias.
- MUST exponer:
  - `play_start()` → beep de inicio de grabación (frecuencia alta, corto)
  - `play_stop()` → beep de fin de grabación (frecuencia media, corto)
  - `play_ready()` → beep de modelo listo / transcripción exitosa (frecuencia alta, doble beep)
  - `play_error()` → beep de error (frecuencia baja, largo)
- SHOULD usar los siguientes valores por defecto:
  ```python
  BEEP_START  = (1200, 100)  # Hz, ms
  BEEP_STOP   = (800,  100)
  BEEP_READY  = (1000, 80) seguido de (1200, 80)
  BEEP_ERROR  = (400,  300)
  ```
- MUST que cada función ejecute el beep en un thread separado para no bloquear el thread de hotkeys.
- MAY ser desactivado en el futuro via config (para v1, siempre activo).

**Scenarios**:

#### Scenario: Beep al iniciar grabación PTT
- **Given**: El usuario presiona la tecla PTT
- **When**: `hotkeys.py` procesa el evento on_press
- **Then**: Se escucha un beep agudo corto (1200 Hz, 100ms) indicando inicio de grabación

#### Scenario: Beep de error con modelo no cargado
- **Given**: `state.model is None`
- **When**: El usuario presiona PTT
- **Then**: Se escucha un beep grave (400 Hz, 300ms) — sin grabación activada

---

### FR-10: System Tray — `wispr/tray.py`

**Priority**: Must Have
**Module**: `wispr/tray.py`

**Requirements**:
- MUST usar `pystray` para el ícono en system tray.
- MUST crear el ícono programáticamente usando `Pillow` (PIL) — no archivos de imagen externos.
- MUST soportar los siguientes estados del ícono:
  - **idle / modelo cargado**: círculo verde sólido
  - **grabando (PTT o Toggle)**: círculo rojo sólido
  - **cargando modelo**: círculo gris con animación de puntos en tooltip
  - **sin modelo**: círculo gris sólido
- MUST que el tooltip del ícono muestre:
  - `"WisprLocal — Modelo: large-v3 | PTT: CapsLock | Toggle: Alt+Shift"` cuando el modelo está cargado
  - `"WisprLocal — Cargando modelo..."` durante la carga
  - `"WisprLocal — Modelo no cargado"` cuando no hay modelo
- MUST incluir las siguientes opciones en el menú contextual (clic derecho):
  - `"Cargar modelo"` (visible solo si `state.model is None`)
  - `"Descargar modelo"` (visible solo si `state.model is not None`)
  - separador
  - `"Abrir config.toml"` → abre el archivo con el editor por defecto del sistema
  - separador
  - `"Salir"` → cierra la aplicación limpiamente
- MUST que `"Salir"` llame a `unload_model()` antes de cerrar para liberar VRAM.
- MUST que `tray.py` exponga `start_tray(state, config, on_load, on_unload) -> pystray.Icon`.
- SHOULD actualizar el ícono y tooltip cada vez que `state.model`, `state.is_loading`, o `state.ptt_active` cambien.
- SHALL correr en su propio thread (pystray lo requiere).

**Scenarios**:

#### Scenario: Ícono gris sin modelo al arrancar
- **Given**: La app inicia y el modelo aún no cargó
- **When**: El usuario ve el system tray
- **Then**: El ícono es un círculo gris y el tooltip dice "WisprLocal — Modelo no cargado"

#### Scenario: Ícono verde con modelo listo
- **Given**: El modelo terminó de cargar
- **When**: El usuario mira el system tray
- **Then**: El ícono cambia a círculo verde y el tooltip muestra modelo, PTT key y Toggle key

#### Scenario: Abrir config desde tray
- **Given**: La app está corriendo
- **When**: El usuario hace clic derecho > "Abrir config.toml"
- **Then**: El archivo `config.toml` se abre en el editor de texto por defecto de Windows (Notepad u otro)

#### Scenario: Salir limpia VRAM
- **Given**: El modelo está cargado (`state.model is not None`)
- **When**: El usuario hace clic derecho > "Salir"
- **Then**: Se llama `unload_model()` (que hace `gc.collect()` + `torch.cuda.empty_cache()`), luego la app termina

---

### FR-11: Entry Point — `wispr/__main__.py`

**Priority**: Must Have
**Module**: `wispr/__main__.py`

**Requirements**:
- MUST ser el único composition root: crea `AppState`, carga config, instancia y conecta todos los módulos.
- MUST iniciar los siguientes componentes en orden:
  1. Cargar config via `config.load_config()`
  2. Instanciar `AppState`
  3. Iniciar `overlay.RecordingOverlay` en thread dedicado
  4. Iniciar `tray.start_tray()` en thread dedicado
  5. Iniciar `audio.start_stream()` (stream siempre activo)
  6. Iniciar `transcription.transcription_worker()` en thread dedicado
  7. Iniciar `transcription.load_model()` en thread dedicado (no bloquea)
  8. Iniciar `hotkeys.start_listener()` (bloquea el thread principal o usa `join()`)
- MUST configurar `logging` básico a nivel `INFO` con formato `"%(asctime)s [%(levelname)s] %(name)s: %(message)s"`.
- MUST manejar `KeyboardInterrupt` (Ctrl+C en consola) limpiamente: descargar modelo, cerrar stream, salir.
- SHOULD imprimir en log al arrancar: `"WisprLocal iniciando... PTT: {ptt_key} | Toggle: {toggle_keys}"`.
- MUST que si `config.load_config()` lanza `ValueError` (config inválida), se loguee el error y la app termine con código de salida 1 (no crashear silenciosamente).

**Scenarios**:

#### Scenario: Arranque exitoso
- **Given**: `config.toml` es válido, micrófono conectado, Python 3.12 en venv
- **When**: Se ejecuta `python -m wispr`
- **Then**: En ≤ 5 segundos aparece el ícono en tray, el overlay está listo, el log muestra "WisprLocal iniciando..."

#### Scenario: Config inválida al arrancar
- **Given**: `config.toml` tiene `device = "tpu"`
- **When**: Se ejecuta `python -m wispr`
- **Then**: El log muestra el error de validación, la app termina con código 1, NO queda un proceso zombie

---

### FR-12: Instalador — `install.py`

**Priority**: Must Have
**Module**: `install.py` (raíz del proyecto)

**Requirements**:
- MUST ser ejecutable con el Python del sistema (no requiere venv previo) usando solo stdlib.
- MUST verificar que Python 3.12+ está disponible. Si no, mostrar mensaje de error claro con URL de descarga y terminar.
- MUST crear un venv en `.venv/` dentro del directorio del proyecto usando `venv.create('.venv', with_pip=True)`.
- MUST detectar GPU NVIDIA via subprocess: `subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'])`. Si falla o no hay output, asumir CPU-only.
- MUST instalar dependencias en este orden:
  1. Si GPU detectada: `pip install torch --index-url https://download.pytorch.org/whl/cu121`
  2. `pip install -r requirements.txt`
- MUST que `requirements.txt` contenga:
  ```
  faster-whisper>=1.0.0
  sounddevice>=0.4.6
  numpy>=1.24.0
  pynput>=1.7.6
  pystray>=0.19.4
  Pillow>=10.0.0
  pyperclip>=1.8.2
  ```
- MUST generar `lanzador.vbs` con rutas dinámicas absolutas al venv y al directorio del proyecto:
  ```vbscript
  Set WshShell = CreateObject("WScript.Shell")
  WshShell.Run """C:\ruta\absoluta\.venv\Scripts\pythonw.exe"" -m wispr", 0, False
  ```
- MUST preguntar interactivamente al usuario si desea configurar inicio automático: `"¿Querés que WisprLocal inicie automáticamente con Windows? [s/N]: "`.
- MUST que si el usuario responde `s` o `S`, copie `lanzador.vbs` al directorio de Startup de Windows: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`.
- MUST mostrar un resumen al finalizar con: rutas instaladas, si GPU fue detectada, si startup fue configurado, instrucciones para lanzar manualmente.
- MUST que cada paso muestre progreso: `"[1/5] Verificando Python..."`, `"[2/5] Creando entorno virtual..."`, etc.
- MUST manejar errores de cada paso con mensaje descriptivo y opción de continuar o abortar.
- SHOULD verificar que `pip` funciona en el venv recién creado antes de instalar dependencias.

**Scenarios**:

#### Scenario: Instalación exitosa con GPU NVIDIA
- **Given**: Python 3.12 instalado, nvidia-smi disponible en PATH, GPU NVIDIA detectada
- **When**: El usuario ejecuta `python install.py` desde el directorio del proyecto
- **Then**: Se crea `.venv/`, se instala PyTorch con CUDA, se instalan el resto de dependencias, se genera `lanzador.vbs` con rutas correctas, el instalador muestra resumen de éxito

#### Scenario: Instalación en máquina sin GPU
- **Given**: Python 3.12 instalado, nvidia-smi NO disponible o no retorna output
- **When**: El usuario ejecuta `python install.py`
- **Then**: El instalador muestra `"GPU NVIDIA no detectada — instalando versión CPU (transcripción más lenta)"`, instala PyTorch sin CUDA, continúa normalmente

#### Scenario: Python versión incorrecta
- **Given**: El sistema tiene Python 3.9 instalado
- **When**: El usuario ejecuta `python install.py`
- **Then**: El instalador muestra `"Error: Se requiere Python 3.12 o superior. Descargá Python 3.12 en https://python.org"` y termina sin crear nada

#### Scenario: Configurar startup automático
- **Given**: La instalación base fue exitosa
- **When**: El instalador pregunta por startup y el usuario responde `s`
- **Then**: `lanzador.vbs` es copiado a `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\` y el instalador confirma `"Startup configurado. WisprLocal iniciará con Windows."`

---

### FR-13: Documentación — `README.md`

**Priority**: Must Have
**Module**: `README.md` (raíz)

**Requirements**:
- MUST contener las siguientes secciones en orden:
  1. Título y descripción de una línea
  2. Badges: Python version, Windows only, license, GPU required
  3. Demo GIF o screenshot del overlay en acción
  4. Sección "Instalación" con exactamente 3 pasos
  5. Sección "Uso" con hotkeys por defecto y explicación PTT vs Toggle
  6. Sección "Configuración" con el schema completo de `config.toml` comentado
  7. Sección "Arquitectura" con el árbol de módulos y una línea por módulo
  8. Sección "Troubleshooting" con al menos 5 problemas comunes y sus soluciones
  9. Sección "Contribuir" con instrucciones de setup para desarrollo
  10. Sección "Licencia"
- MUST que la sección "Instalación" sea exactamente:
  ```
  1. Instalar Python 3.12 desde https://python.org
  2. Ejecutar: python install.py
  3. Doble clic en lanzador.vbs (o reiniciar si configuraste startup)
  ```
- MUST incluir en "Troubleshooting" al menos estos casos:
  - La app no detecta GPU (verificar nvidia-smi, versión de CUDA)
  - El overlay no aparece (verificar que no está en fullscreen exclusivo)
  - Las hotkeys no funcionan (verificar que no hay conflicto con el sistema)
  - El micrófono no es detectado (verificar dispositivo por defecto en Windows)
  - La transcripción es lenta o imprecisa (verificar modelo y compute_type)
- SHOULD incluir el badge "Windows only" de forma prominente para evitar issues de usuarios Linux/macOS.
- MAY incluir una sección "Roadmap" con features planeadas (GUI de config, soporte multi-idioma, etc.).

**Scenarios**:

#### Scenario: Usuario nuevo sigue README
- **Given**: Un usuario con Python 3.12 y GPU NVIDIA lee el README
- **When**: Sigue los 3 pasos de instalación
- **Then**: Puede usar WisprLocal sin leer más documentación ni tocar código

#### Scenario: Troubleshooting de GPU no detectada
- **Given**: Un usuario reporta que la GPU no es detectada
- **When**: Consulta la sección "Troubleshooting"
- **Then**: Encuentra instrucciones para ejecutar `nvidia-smi` manualmente y verificar la versión de CUDA compatible

---

## Non-Functional Requirements

### NFR-01: Compatibilidad de Plataforma
- MUST funcionar EXCLUSIVAMENTE en Windows 10/11 — no se requiere ni se soporta Linux/macOS.
- MUST usar APIs Windows-específicas donde sea necesario: `winsound`, `pynput`, `pystray`.
- MUST que `install.py` asuma Windows y use paths de Windows.

### NFR-02: Rendimiento
- MUST que el tiempo entre soltar PTT y escuchar el beep de listo sea ≤ 8 segundos para audio de 10 segundos en GPU NVIDIA RTX 3070 o superior.
- SHOULD que el uso de RAM de la app (sin el modelo cargado) sea ≤ 100 MB.
- MUST liberar VRAM completamente al descargar el modelo via `gc.collect()` + `torch.cuda.empty_cache()`.

### NFR-03: Estabilidad
- MUST que la app corra indefinidamente sin memory leaks — una grabación completa (PTT press → release → transcripción → inyección) no debe aumentar el uso de memoria en el tiempo.
- MUST que un error en transcripción (excepción de faster_whisper) no crashee la app — se loguea y continúa.

### NFR-04: Logging
- MUST usar el módulo `logging` de stdlib — no `print()` para mensajes de diagnóstico.
- SHOULD configurar un `FileHandler` que escriba a `wispr.log` en el directorio del proyecto para debugging.
- MAY rotar el log a 1 MB máximo con `RotatingFileHandler`.

### NFR-05: Versionado y Git
- MUST crear tag `v0.1.0-mvp` ANTES de comenzar el refactor (proteger el MVP funcional).
- MUST que cada fase del refactor sea un commit atómico con mensaje convencional (`feat:`, `refactor:`, `docs:`, etc.).
- MUST que no haya atribución de IA en los commits.
- MUST que `.gitignore` incluya: `.venv/`, `*.log`, `__pycache__/`, `openspec/`, `.atl/`.

---

## Implementation Phases

El refactor se ejecuta en 6 fases atómicas. Cada fase es un commit independiente y verificable manualmente:

| Fase | Commit | Descripción |
|------|--------|-------------|
| 1 | `refactor: extract wispr package from mvp_local.py` | Crear estructura de módulos, mover código sin cambiar comportamiento |
| 2 | `feat: add config.toml and config module` | Externalizar configuración, eliminar hardcoding |
| 3 | `feat: add tkinter recording overlay` | Indicador visual de grabación |
| 4 | `feat: add configurable hotkeys` | Hotkeys desde config.toml |
| 5 | `feat: add automated installer` | install.py con detección GPU y generación de lanzador |
| 6 | `docs: rewrite README with full documentation` | README profesional con 3-step install |

Cada fase DEBE ser verificada manualmente antes de continuar a la siguiente.

---

## Constraints

- NO agregar dependencias no listadas en `requirements.txt` sin actualizar este spec.
- NO usar `PyYAML` — toda configuración es TOML via `tomllib` (stdlib).
- NO modificar la lógica de transcripción del MVP (faster-whisper large-v3) — solo refactorizar encapsulamiento.
- NO agregar GUI de edición de hotkeys en v1 — solo edición manual de `config.toml`.
- NO cruzar responsabilidades: `hotkeys.py` no hace transcripción, `transcription.py` no hace audio capture, etc.
- ALWAYS usar `.venv/Scripts/python.exe` — nunca el Python del sistema para ejecutar la app.
