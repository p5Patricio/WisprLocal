[ARCHIVED — WisprLocal Fase 1] Este documento forma parte del histórico archivado. No modificar.

# Tasks: WisprLocal Fase 1

## Phase 1: Infraestructura

### T1 — Crear wispr/errors.py
- [x] **Archivos**: `wispr/errors.py` (nuevo)
- **Descripción**: Jerarquía plana de excepciones propias.
- **Criterios**: `WisprError`, `ModelLoadError`, `TranscriptionError`, `AudioDeviceError`, `InjectionError` heredan correctamente.
- **Esfuerzo**: small

### T2 — Refactorizar wispr/state.py
- [x] **Archivos**: `wispr/state.py`
- **Descripción**: Agregar `threading.Lock`, getters/setters atómicos, `shutdown_event`, `audio_queue` con `maxsize` desde config.
- **Criterios**: `set_ptt/get_ptt`, `set_toggle/get_toggle`, `set_loading/get_loading`, `is_recording()` son thread-safe; `shutdown_event` es `threading.Event`.
- **Esfuerzo**: medium

### T3 — Extender wispr/config.py
- [x] **Archivos**: `wispr/config.py`
- **Descripción**: Nuevos defaults (`name="auto"`, `queue_maxsize=100`, `vad_parameters={}`); función `detect_optimal_model()` con psutil.
- **Criterios**: Valor `"auto"` resuelve a modelo según RAM/GPU; config existente sin `name` usa `"auto"`; config con valor fijo se respeta.
- **Esfuerzo**: medium

### T4 — Actualizar dependencias
- [x] **Archivos**: `requirements.txt`
- **Descripción**: Agregar `psutil>=5.9.0`.
- **Criterios**: `pip install -r requirements.txt` instala psutil sin conflictos.
- **Esfuerzo**: small

## Phase 2: Workers

### T5 — Modificar wispr/audio.py
- [x] **Archivos**: `wispr/audio.py`
- **Descripción**: Callback usa `put_nowait()`; si la cola está llena, descarta el chunk más viejo con `get_nowait()` antes de `put_nowait()`; leer `maxsize` desde config.
- **Criterios**: PTT >10s sin modelo cargado no bloquea el callback ni crece RAM indefinidamente; `queue_maxsize` se carga desde `config.DEFAULTS`.
- **Esfuerzo**: small

### T6 — Modificar wispr/transcription.py
- [x] **Archivos**: `wispr/transcription.py`
- **Descripción**: Integrar `vad_filter` + `vad_parameters` (con fallback try/except); envolver excepciones de inferencia en `TranscriptionError`; leer `shutdown_event` para salida limpia; usar `detect_optimal_model` cuando `name="auto"`.
- **Criterios**: VAD activo con parámetros configurables; si VAD falla, transcribe sin VAD y loguea warning; excepciones propias propagan causa original; worker verifica `shutdown_event.is_set()` en loops.
- **Esfuerzo**: large

### T7 — Modificar wispr/hotkeys.py
- [x] **Archivos**: `wispr/hotkeys.py`
- **Descripción**: Reemplazar acceso directo a atributos de estado por getters/setters atómicos (`set_ptt`, `get_ptt`, etc.); verificar `shutdown_event` si aplica.
- **Criterios**: PTT y toggle funcionan igual que antes; no hay race conditions al leer/escribir estado; nunca accede a `_state.ptt` directamente.
- **Esfuerzo**: small

## Phase 3: UX

### T8 — Modificar wispr/injection.py
- [x] **Archivos**: `wispr/injection.py`
- **Descripción**: Antes de inyectar, guardar contenido actual del clipboard; tras inyección, restaurar si el contenido era texto y <=5MB; envolver fallos en `InjectionError`.
- **Criterios**: Copiar texto, dictar y pegar restaura el texto original al clipboard; contenido binario o >5MB se omite restore sin error; `pyperclip.paste()` + `Ctrl+V` + sleep + `pyperclip.copy(prev)`.
- **Esfuerzo**: medium

### T9 — Modificar wispr/overlay.py
- [x] **Archivos**: `wispr/overlay.py`
- **Descripción**: Agregar estado de error con fondo `#C53030`; método `show_error(message)` que reutiliza `_set_state`.
- **Criterios**: Llamar `show_error("mensaje")` cambia fondo a rojo y muestra texto; no rompe estados existentes (idle, listening, processing).
- **Esfuerzo**: small

### T10 — Modificar wispr/tray.py
- [x] **Archivos**: `wispr/tray.py`
- **Descripción**: `on_quit` debe setear `shutdown_event` y esperar joins de workers antes de detener el icono.
- **Criterios**: Click en "Salir" dispara secuencia ordenada; no deja threads huérfanos; si join excede timeout, loguea warning y continúa.
- **Esfuerzo**: small

## Phase 4: Composición

### T11 — Modificar wispr/__main__.py
- [x] **Archivos**: `wispr/__main__.py`
- **Descripción**: Pasar `shutdown_event` a todos los workers; implementar shutdown sequence completo con joins ordenados y timeouts.
- **Criterios**: Secuencia: set event → stop_stream → listener.stop → queue.put(None) → worker.join(5) → loader.join(5) → unload_model → overlay.destroy → icon.stop; joins con timeout 5s.
- **Esfuerzo**: medium

## Verificación Manual (post-implementación)

- [ ] Thread safety: PTT + toggle rápido; `is_recording()` nunca falla.
- [ ] Shutdown: Salir durante carga de modelo y durante grabación; sin threads huérfanos.
- [ ] Audio backpressure: PTT >10s sin modelo; RAM estable.
- [ ] Clipboard: Copiar texto, dictar, pegar; Ctrl+V posterior pega el original.
- [ ] VAD: Dictar con ruido de fondo; reducción de falsos positivos.
- [ ] Auto-model: Ejecutar en PC con/sin GPU; modelo correcto en logs.
- [ ] Errors: Borrar archivo de modelo; overlay rojo + sonido de error.
