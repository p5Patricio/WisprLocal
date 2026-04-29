[ARCHIVED — WisprLocal Fase 1] Este documento forma parte del histórico archivado. No modificar.

# Design: WisprLocal Fase 1

## Technical Approach

Aplicar 8 mejoras incrementales sin breaking changes: (1) proteger AppState con lock central + getters/setters, (2) senalizar shutdown via threading.Event con join ordenado, (3) limitar audio_queue con drop-oldest, (4) restaurar clipboard post-inyeccion, (5) activar VAD en transcribe con parametros configurables, (6) auto-detectar hardware para sugerir modelo Whisper, (7) agregar estado de error al overlay, (8) crear jerarquia de excepciones propias.

## Architecture Decisions

| Decision | Chosen | Rejected | Rationale |
|----------|--------|----------|-----------|
| State sync | Central threading.Lock en AppState | Lock por campo | Menos objetos, acceso O(1), suficiente para 4 campos |
| Shutdown signal | threading.Event en AppState | Variables bool + lock | Event es el idiom de Python para senalizar salida a multiples threads |
| Audio backpressure | put_nowait() + get_nowait() drop-oldest | maxsize con bloqueo | El callback de PortAudio NUNCA debe bloquear |
| Clipboard restore | Guardar texto previo; omitir si >5MB o binario | Intentar restorear imagenes | pyperclip solo maneja texto confiablemente |
| VAD fallback | Try vad_filter=True; except -> sin VAD + warning | Fallar duro | Compatibilidad con versiones antiguas de faster-whisper |
| Auto-model | Default name = auto en DEFAULTS; detectar al cargar | Parsear TOML raw | Mas simple, no rompe config.toml existentes |
| Overlay error | Reutilizar _set_state con texto dinamico | Widget separado | Minimo cambio en tkinter, consistente con estados actuales |
| Errors | Nuevo errors.py con jerarquia plana | Excepciones por modulo | Facil de importar, suficiente para 5 tipos |

## Data Flow

Audio callback -> put_nowait -> audio_queue(maxsize=100) -> get -> transcription_worker
                                     |                               |
                                     +-- drop-oldest (full)          +-- vad_filter -> inject_text -> clipboard restore

Shutdown flow:
  tray.on_quit -> set shutdown_event -> stop_stream -> listener.stop -> queue.put(None) -> join(worker) -> join(loader) -> unload_model -> overlay.destroy -> icon.stop

## Threading Model

| Thread | Owns | Touches (read/write) | Lock Strategy |
|--------|------|----------------------|---------------|
| Main | tray icon, shutdown coord | shutdown_event.set() | N/A |
| Audio callback (PortAudio) | - | audio_queue.put_nowait() | Queue es thread-safe; no lock adicional |
| Keyboard listener (pynput) | - | AppState via set_ptt/get_ptt | with state.lock: corto |
| Transcription worker | buffer local | audio_queue.get(), state.model, shutdown_event | Lock solo para leer model ref; inference fuera del lock |
| Model loader | - | state.set_model/clear_model, state.is_loading | Lock interno en AppState |
| Overlay (tkinter) | root, label | Solo via root.after(0, ...) | tkinter single-threaded; after() es la sync |
| Sounds (winsound) | - | winsound.Beep en daemon | Stateless |

Regla de oro: Nunca tomar el lock durante I/O (carga de modelo, transcribe, winsound) ni durante sleep del clipboard.

## State Machine: Shutdown Sequence

[Running] --tray Salir--> [Signaling] set shutdown_event
[Signaling] --> stop_stream()
[Signaling] --> listener.stop()
[Signaling] --> audio_queue.put(None)  // despierta worker si bloqueado
[Signaling] --> worker.join(timeout=5s)
[Signaling] --> loader.join(timeout=5s)
[Signaling] --> unload_model()
[Signaling] --> overlay.destroy()
[Signaling] --> icon.stop()
[Exited]

Si join() excede timeout -> log warning y continuar. No bloquear indefinidamente.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| wispr/errors.py | Create | WisprError, ModelLoadError, TranscriptionError, AudioDeviceError, InjectionError |
| wispr/state.py | Modify | Agregar getters/setters atomicos; shutdown_event; audio_queue maxsize desde config |
| wispr/__main__.py | Modify | shutdown_event pasado a workers; orden de cierre corregido con joins |
| wispr/audio.py | Modify | Callback con put_nowait + drop-oldest; leer maxsize desde config |
| wispr/hotkeys.py | Modify | Usar set_ptt/get_ptt atomicos; chequear shutdown_event si aplica |
| wispr/transcription.py | Modify | vad_filter + vad_parameters; envolver excepciones en clases propias; leer shutdown_event |
| wispr/injection.py | Modify | Guardar/restaurar clipboard; envolver en InjectionError |
| wispr/overlay.py | Modify | Estado error con bg #C53030; metodo show_error(message) |
| wispr/config.py | Modify | DEFAULTS: model.name=auto; audio.queue_maxsize=100; transcription.vad_parameters={} |
| wispr/tray.py | Modify | on_quit usa shutdown_event y joins |
| requirements.txt | Modify | Agregar psutil>=5.9.0 |

## Interfaces / Contracts

```python
# wispr/errors.py
class WisprError(Exception): ...
class ModelLoadError(WisprError): ...
class TranscriptionError(WisprError): ...
class AudioDeviceError(WisprError): ...
class InjectionError(WisprError): ...

# wispr/state.py -- getters/setters atomicos
class AppState:
    def set_ptt(self, v: bool) -> None: ...
    def get_ptt(self) -> bool: ...
    def set_toggle(self, v: bool) -> None: ...
    def get_toggle(self) -> bool: ...
    def set_loading(self, v: bool) -> None: ...
    def get_loading(self) -> bool: ...
    def is_recording(self) -> bool: ...  # usa lock interno

# wispr/config.py -- deteccion hardware
def detect_optimal_model(config: dict) -> str: ...

# wispr/overlay.py
class RecordingOverlay:
    def show_error(self, message: str) -> None: ...

# wispr/injection.py
def inject_text(text: str, pre_delay_ms: int = 150, post_delay_ms: int = 400) -> None: ...
```

## Config Changes

```toml
[model]
name = "auto"          # "auto" = detectar hardware; string = forzar modelo

[audio]
queue_maxsize = 100     # nuevos chunks descartan los mas viejos cuando se llena

[transcription]
vad_parameters = {}     # ej: { min_silence_duration_ms = 500, speech_pad_ms = 200 }
```

Config existente se respeta: si el usuario ya tiene `name = "large-v3"`, se usa literal.

## Dependency Changes

- **Add**: `psutil>=5.9.0` (deteccion de RAM para auto-modelo)
- **Keep all existing**: faster-whisper, sounddevice, numpy, pynput, pystray, Pillow, pyperclip

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Manual | Thread safety | PTT + toggle rapido desde teclado; verificar `is_recording()` nunca falla |
| Manual | Shutdown | Salir durante carga de modelo y durante grabacion; `tasklist` sin threads huerfanos |
| Manual | Audio backpressure | Mantener PTT >10s sin modelo cargado; RAM estable |
| Manual | Clipboard | Copiar texto, dictar, pegar; verificar Ctrl+V posterior pega el original |
| Manual | VAD | Dictar con ruido de fondo; verificar reduccion de falsos positivos |
| Manual | Auto-model | Ejecutar en PC con GPU y sin GPU; verificar modelo seleccionado en logs |
| Manual | Errors | Borrar archivo de modelo; verificar overlay rojo + sonido de error |

## Open Questions

- [ ] Se necesita un timeout de inactividad para unload_model automatico? (no esta en el spec, pero podria ser util)
- [ ] El VAD de faster-whisper tiene impacto medible en latency? Se asume negligible para modelos locales.
