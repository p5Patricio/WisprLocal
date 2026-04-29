[ARCHIVED — WisprLocal Fase 1] Este documento forma parte del histórico archivado. No modificar.

# WisprLocal Fase 1 — Especificacion Tecnica

## 1. app-state-threadsafe

**Req A1:** AppState DEBE proteger ptt_active, toggle_active, is_loading, load_model_requested, unload_model_requested con threading.Lock.

| Id | Escenario | Given | When | Then |
|----|-----------|-------|------|------|
| A1-H | Happy path | Estado limpio | Dos threads modifican ptt_active simultaneamente | No hay RuntimeError ni estado corrupto |
| A1-E | Edge case | is_loading=True | load_model() y unload_model() concurrentes | Solo una operacion ejecuta; la otra espera el lock |

**Req A2:** AppState DEBE exponer getters/setters atomicos: set_ptt(v), get_ptt(), set_toggle(v), get_toggle(), set_loading(v), get_loading().

| Id | Escenario | Given | When | Then |
|----|-----------|-------|------|------|
| A2-H | Happy path | Thread A en set_ptt(True) | Thread B llama get_ptt() | Retorna valor consistente (no medio-escrito) |

**Interfaces:** AppState dataclass con lock: threading.Lock. Metodos atomicos envuelven with self.lock:.
**Error handling:** Ninguno — los locks nunca levantan excepciones por uso correcto.
**Test manual:** Iniciar PTT y toggle desde hotkeys rapidamente; verificar que is_recording() nunca falle.

---

## 2. graceful-shutdown

**Req S1:** __main__.py DEBE senalar shutdown a todos los workers via threading.Event antes de unirse.

| Id | Escenario | Given | When | Then |
|----|-----------|-------|------|------|
| S1-H | Happy path | App corriendo con worker y loader activos | Usuario clickea Salir en tray | Workers reciben shutdown_event, terminan su loop, hacen join() |
| S1-E | Edge case | Audio queue llena al salir | stop_stream() cierra el stream | Worker vacia queue y sale sin bloqueo infinito |

**Req S2:** El orden de cierre DEBE ser: (1) senalar shutdown, (2) stop_stream(), (3) listener.stop(), (4) join() de workers, (5) unload_model(), (6) overlay.destroy(), (7) icon.stop().

| Id | Escenario | Given | When | Then |
|----|-----------|-------|------|------|
| S2-H | Happy path | Grabacion activa al salir | Se ejecuta secuencia de shutdown | No hay dangling threads ni mensajes de daemon kill |

**Interfaces:** AppState.shutdown_event: threading.Event. transcription_worker y load_model leen shutdown_event.is_set().
**Error handling:** Si join() excede timeout (5s), loggear warning y continuar.
**Test manual:** Salir durante carga de modelo y durante grabacion; verificar tasklist sin procesos huerfanos.

---

## 3. audio-backpressure

**Req B1:** audio_queue DEBE crearse con maxsize=100.

| Id | Escenario | Given | When | Then |
|----|-----------|-------|------|------|
| B1-H | Happy path | Queue en 99 items | Callback de audio recibe nuevo chunk | El chunk 100 se encola; el 101 bloquea temporalmente |
| B1-E | Edge case | Queue llena durante burst de audio | El callback sigue produciendo | El callback bloquea en put() hasta que worker consuma |

**Req B2:** audio_queue DEBE descartar chunks cuando maxsize se alcanza (estrategia drop-oldest).

| Id | Escenario | Given | When | Then |
|----|-----------|-------|------|------|
| B2-H | Happy path | Queue llena con chunks antiguos | Nuevo chunk disponible | Se descarta el chunk mas viejo; se encola el nuevo |

**Interfaces:** audio_queue: queue.Queue(maxsize=100). Callback usa put(block=False) + get_nowait() para descartar oldest si esta llena.
**Data model:** AppState.audio_queue con maxsize configurable via config audio queue_maxsize (default 100).
**Error handling:** Ninguno — el drop es silencioso y loggeable a debug.
**Test manual:** Mantener PTT presionado >10s con modelo descargado; verificar memoria RAM estable.

---

## 4. clipboard-restore

**Req C1:** inject_text() DEBE guardar el contenido previo del clipboard antes de copiar el texto transcrito.

| Id | Escenario | Given | When | Then |
|----|-----------|-------|------|------|
| C1-H | Happy path | Clipboard contiene hola | Se inyecta mundo | Despues de Ctrl+V, el clipboard vuelve a hola |
| C1-E | Edge case | Clipboard contiene imagen/binario grande (>5MB) | Se inyecta texto | Se omite restore; se deja el texto inyectado en clipboard |

**Interfaces:** inject_text(text: str, pre_delay_ms: int = 150, post_delay_ms: int = 400) — anadir clipboard_save/restore interno.
**Error handling:** Si pyperclip.paste() falla (clipboard no texto), capturar excepcion y continuar sin restore.
**Test manual:** Copiar texto, dictar, pegar en Notepad — verificar Ctrl+V posterior pega el texto original.

---

## 5. vad-filtering

**Req V1:** transcription_worker DEBE usar vad_filter=True en model.transcribe() con vad_parameters configurable.

| Id | Escenario | Given | When | Then |
|----|-----------|-------|------|------|
| V1-H | Happy path | Buffer con silencio + voz | Se envia a transcribir | vad_filter=True elimina segmentos sin voz; solo transcribe voz |
| V1-E | Edge case | Todo el buffer es silencio | Se envia a transcribir | No se inyecta texto vacio; no hay error |

**Req V2:** config.toml DEBE permitir override de vad_parameters (ej. min_silence_duration_ms, speech_pad_ms).

| Id | Escenario | Given | When | Then |
|----|-----------|-------|------|------|
| V2-H | Happy path | Usuario configura speech_pad_ms=100 | Se carga config | model.transcribe() recibe esos parametros |

**Interfaces:** model.transcribe(..., vad_filter=True, vad_parameters=config transcription vad_parameters default vacio).
**Data model:** Config opcional transcription vad_parameters con dict de parametros de faster-whisper VAD.
**Error handling:** Si vad_filter lanza excepcion (version incompatible), capturar y reintentar sin VAD loggeando warning.
**Test manual:** Dictar en ambiente con ruido de fondo; verificar reduccion de falsos positivos (>50%).

---

## 6. hardware-auto-model

**Req H1:** Al iniciar, si config.model.name NO esta sobreescrito explicitamente por el usuario, el sistema DEBE detectar VRAM (GPU) o RAM (CPU) y sugerir modelo: tiny (<4GB), base (4-6GB), small (6-10GB), medium (10-16GB), large-v3 (>16GB).

| Id | Escenario | Given | When | Then |
|----|-----------|-------|------|------|
| H1-H | Happy path | GPU con 8GB VRAM | Config no especifica modelo | Se selecciona small; se loggea eleccion |
| H1-E | Edge case | torch.cuda no disponible; 32GB RAM | Config no especifica modelo | Se selecciona medium (CPU); se loggea fallback |

**Req H2:** El usuario DEBE poder forzar modelo manual en config.toml; en ese caso la deteccion automatica se omite.

| Id | Escenario | Given | When | Then |
|----|-----------|-------|------|------|
| H2-H | Happy path | config.toml tiene name=large-v3 | Arranque de app | Se respeta la eleccion; no se ejecuta deteccion |

**Interfaces:** detect_optimal_model(config: dict) -> str. Usa torch.cuda.get_device_properties(0).total_memory y psutil.virtual_memory().total.
**Error handling:** Si torch.cuda falla y psutil no esta disponible, default a base y loggear warning.
**Test manual:** Ejecutar en PC con GPU y sin GPU; verificar modelo seleccionado en logs.

---

## 7. overlay-polish

**Req O1:** El overlay DEBE mostrar estado de error con fondo rojo oscuro (#C53030) y texto descriptivo.

| Id | Escenario | Given | When | Then |
|----|-----------|-------|------|------|
| O1-H | Happy path | Error de transcripcion | overlay.show_error(Mic no detectado) | Overlay muestra error en rojo oscuro |
| O1-E | Edge case | Overlay deshabilitado en config | show_error() llamado | No se crea ventana; no hay excepcion |

**Req O2:** El overlay DEBE tener estados visuales distintos: ptt (rojo), toggle (naranja), loading (gris), error (rojo oscuro), hidden.

| Id | Escenario | Given | When | Then |
|----|-----------|-------|------|------|
| O2-H | Happy path | Transicion de grabacion a error | show_ptt() -> show_error() | Color y texto cambian sin recrear ventana |

**Interfaces:** RecordingOverlay.show_error(message: str) -> None. STATES error = text con warning, bg #C53030, fg white.
**Error handling:** Si root.after() falla (tkinter destruido), capturar y loggear warning.
**Test manual:** Forzar error de modelo inexistente; verificar overlay rojo oscuro con mensaje legible.

---

## 8. structured-errors

**Req E1:** El sistema DEBE definir clases de error: WisprError (base), ModelLoadError, TranscriptionError, AudioDeviceError, InjectionError.

| Id | Escenario | Given | When | Then |
|----|-----------|-------|------|------|
| E1-H | Happy path | load_model() lanza OSError | Se envuelve en ModelLoadError | El caller recibe ModelLoadError con mensaje amigable |
| E1-E | Edge case | Excepcion desconocida | Se envuelve en WisprError | No se pierde traceback original |

**Req E2:** Las excepciones capturadas DEBEN mostrarse en overlay y/o log con mensaje en espanol entendible para el usuario.

| Id | Escenario | Given | When | Then |
|----|-----------|-------|------|------|
| E2-H | Happy path | TranscriptionError durante dictado | Worker la captura | Overlay muestra error de transcripcion |
| E2-E | Edge case | Error fuera del thread de overlay | No hay overlay disponible | Solo se loggea; no hay RuntimeError por tkinter |

**Interfaces:** class WisprError(Exception), ModelLoadError, TranscriptionError, AudioDeviceError, InjectionError.
**Error handling:** Cada modulo envuelve excepciones propias en su clase y las propaga hacia __main__.py o overlay.
**Test manual:** Borrar archivo de modelo para forzar ModelLoadError; verificar mensaje en overlay y sonido de error.
