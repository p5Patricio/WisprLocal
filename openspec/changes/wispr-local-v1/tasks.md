# Tasks: wispr-local-v1

**Change**: wispr-local-v1
**Total tasks**: 30
**Status**: pending

---

## Fase 1: Refactor Estructural

**Objetivo**: Mover el código de `mvp_local.py` a módulos con responsabilidades claras SIN cambiar el comportamiento observable. Al final de esta fase la app funciona exactamente igual que antes, pero desde `python -m wispr`.

**Criterio de éxito**: Ejecutar `python -m wispr` desde el venv produce el mismo comportamiento que el `mvp_local.py` original: ícono en tray, PTT con CapsLock, Toggle con Alt+Shift, transcripción e inyección funcionando.

**Tag de rollback**: `v0.1.0-mvp`

---

### 1.1 Crear tag v0.1.0-mvp antes de tocar nada
- **FR**: FR-01
- **Archivos**: ninguno (operación git)
- **Qué hacer**: Ejecutar `git tag v0.1.0-mvp` en el estado actual del repo. Este es el punto de restauración de emergencia.
- **Criterio**: `git tag` muestra `v0.1.0-mvp`. `git checkout v0.1.0-mvp -- mvp_local.py` funciona sin errores.
- [ ] completado

---

### 1.2 Crear estructura de directorios
- **FR**: FR-01
- **Archivos**: `wispr/__init__.py`, `tools/` (directorio)
- **Qué hacer**: Crear el directorio `wispr/` con `__init__.py` vacío (solo docstring del paquete). Crear el directorio `tools/`. No crear aún los módulos internos.
- **Criterio**: `python -c "import wispr"` desde el venv no lanza error. El directorio `tools/` existe.
- [ ] completado

---

### 1.3 Crear `wispr/state.py` — AppState dataclass
- **FR**: FR-02
- **Archivos**: `wispr/state.py`
- **Qué hacer**: Implementar `AppState` exactamente según el design (campos: `ptt_active`, `toggle_active`, `model`, `is_loading`, `overlay_enabled`, `audio_queue`, `lock`). Incluir métodos `is_recording()`, `set_model()`, `clear_model()`. Sin dependencias de otros módulos del paquete.
- **Criterio**: `python -c "from wispr.state import AppState; s = AppState(); assert not s.is_recording()"` pasa sin error.
- **⚡ Performance**: `audio_queue` es un `queue.Queue` — las operaciones `put()` desde el callback de PortAudio y `get()` desde el transcription worker son thread-safe sin lock adicional. `ptt_active` y `toggle_active` son bools protegidos por el GIL — no requieren lock para reads desde el callback.
- [ ] completado

---

### 1.4 Crear `wispr/sounds.py` — feedback auditivo en threads
- **FR**: FR-09
- **Archivos**: `wispr/sounds.py`
- **Qué hacer**: Implementar `play_start()`, `play_stop()`, `play_ready()`, `play_error()` usando `winsound.Beep`. Cada función lanza un `threading.Thread(daemon=True)` para no bloquear. Valores: START=1200Hz/100ms, STOP=800Hz/100ms, READY=1000Hz/80ms+1200Hz/80ms, ERROR=400Hz/300ms.
- **Criterio**: Llamar `from wispr import sounds; sounds.play_start()` produce un beep sin bloquear el thread llamante (retorna en < 10ms).
- **⚡ Performance**: CRÍTICO — cada `play_*()` debe retornar inmediatamente. `winsound.Beep()` bloquea su thread, por eso corre en daemon thread. El thread de hotkeys (pynput) nunca espera el beep.
- [ ] completado

---

### 1.5 Crear `wispr/injection.py` — inyección de texto
- **FR**: FR-08
- **Archivos**: `wispr/injection.py`
- **Qué hacer**: Implementar `inject_text(text: str, delay_ms: int = 100) -> None`. Lógica: (1) no-op si texto vacío, (2) guardar clipboard previo, (3) `pyperclip.copy(text)`, (4) `time.sleep(delay_ms/1000)`, (5) simular Ctrl+V con `pynput.keyboard.Controller`, (6) restaurar clipboard previo. Manejar excepciones de pyperclip con log.
- **Criterio**: Abrir Notepad, enfocar en el área de texto, ejecutar `inject_text("hola mundo")` desde el venv — aparece "hola mundo" en Notepad.
- [ ] completado

---

### 1.6 Crear `wispr/audio.py` — stream de audio
- **FR**: FR-06
- **Archivos**: `wispr/audio.py`
- **Qué hacer**: Implementar `start_stream(state: AppState, config: dict) -> sd.InputStream` y `stop_stream(stream)`. El callback encola chunks en `state.audio_queue` SOLO si `state.ptt_active or state.toggle_active`. Manejar `PortAudioError` con `RuntimeError` descriptivo. El stream se abre una sola vez y queda siempre activo.
- **Criterio**: Ejecutar `start_stream` sin micrófono conectado lanza `RuntimeError` con mensaje claro. Con micrófono, el stream se inicia sin error.
- **⚡ Performance**: CRÍTICO — el callback de PortAudio corre cada ~20ms en el thread interno de PortAudio. El callback debe ser O(1): solo `if state.ptt_active or state.toggle_active: queue.put(indata.copy())`. NUNCA llamar funciones de transcripción, overlay, ni logging desde el callback.
- [ ] completado

---

### 1.7 Crear `wispr/transcription.py` — modelo y worker
- **FR**: FR-07
- **Archivos**: `wispr/transcription.py`
- **Qué hacer**: Implementar `load_model(state, config, sounds)`, `unload_model(state)`, y `transcription_worker(state, config, injection_fn, sounds)`. El worker hace loop infinito bloqueando en `state.audio_queue.get()`. Al recibir sentinel `None`: concatenar buffer, verificar mínimo 0.3s, transcribir, inyectar. Si modelo no disponible: descartar y loguear. Capturar todas las excepciones de faster_whisper. `unload_model` debe llamar `gc.collect()` + `torch.cuda.empty_cache()` + `torch.cuda.synchronize()`.
- **Criterio**: Con modelo cargado, poner chunks de audio en `state.audio_queue` + `None` sentinel → el worker transcribe e inyecta texto. Con audio de 0.1s → descarta y loguea "Audio demasiado corto".
- **⚡ Performance**: CRÍTICO — el worker corre en daemon thread SEPARADO. `transcription_worker` NUNCA corre en el main thread ni en el thread de hotkeys. La llamada a `model.transcribe()` puede tomar 1-5 segundos — esto es aceptable porque corre en su propio thread y no bloquea ninguna otra operación. El main thread y el thread de pynput siempre responden en < 50ms.
- [ ] completado

---

### 1.8 Crear `wispr/hotkeys.py` — listener de teclado (hardcoded por ahora)
- **FR**: FR-05
- **Archivos**: `wispr/hotkeys.py`
- **Qué hacer**: Extraer la lógica de `on_press` / `on_release` de `mvp_local.py` a `hotkeys.py`. En esta fase las teclas siguen hardcodeadas (CapsLock y Alt+Shift) — la configuración desde config viene en Fase 4. Implementar `start_listener(state, config, overlay, sounds) -> pynput.keyboard.Listener`. Al presionar PTT: `state.ptt_active = True`, llamar `sounds.play_start()`. Al soltar: `state.ptt_active = False`, poner sentinel en `state.audio_queue`, llamar `sounds.play_stop()`. Si `state.model is None`: `sounds.play_error()`, no grabar.
- **Criterio**: Con el listener iniciado, presionar CapsLock activa grabación (`state.ptt_active = True`). Soltar CapsLock pone `None` en la queue. Alt+Shift togglea `state.toggle_active`.
- **⚡ Performance**: Los callbacks de pynput corren en el thread de pynput. Las operaciones deben ser O(1): set bool, call sounds (retorna inmediato por ser daemon thread), put sentinel en queue. NUNCA esperar ni hacer I/O en los callbacks.
- [ ] completado

---

### 1.9 Crear `wispr/tray.py` — system tray (funcionalidad MVP)
- **FR**: FR-10
- **Archivos**: `wispr/tray.py`
- **Qué hacer**: Extraer la lógica de tray de `mvp_local.py`. Implementar `start_tray(state, config, on_load, on_unload, on_quit) -> None` (bloquea). Crear ícono programáticamente con Pillow (círculo verde = modelo cargado, gris = sin modelo). Menú: "Cargar modelo", "Descargar modelo", "Abrir config.toml" (implementar en Fase 2), "Salir". `update_tray_icon(icon, state)` helper para actualizar desde callbacks. Tooltip básico.
- **Criterio**: `start_tray` arranca sin error, el ícono aparece en el system tray, el menú tiene las opciones descritas. "Salir" cierra la app limpiamente.
- [ ] completado

---

### 1.10 Crear `wispr/overlay.py` — RecordingOverlay no-op (stub)
- **FR**: FR-04
- **Archivos**: `wispr/overlay.py`
- **Qué hacer**: Crear `RecordingOverlay` con la interfaz completa (`show_ptt()`, `show_toggle()`, `show_loading()`, `hide()`, `destroy()`) pero todos los métodos en no-op (no crean ventana tkinter aún). La implementación real viene en Fase 3. El stub permite que `__main__.py` compile y funcione.
- **Criterio**: `from wispr.overlay import RecordingOverlay; o = RecordingOverlay({}); o.show_ptt(); o.hide()` no lanza ningún error.
- [ ] completado

---

### 1.11 Crear `wispr/__main__.py` — composition root
- **FR**: FR-11
- **Archivos**: `wispr/__main__.py`
- **Qué hacer**: Implementar `main()` con el orden de inicialización del design: (1) config dummy (dict con defaults hardcodeados por ahora), (2) `AppState()`, (3) `RecordingOverlay(config)`, (4) thread `transcription_worker`, (5) thread `load_model`, (6) `audio.start_stream()`, (7) `hotkeys.start_listener()`, (8) `tray.start_tray()` (bloquea). Configurar logging básico (`INFO`, formato con timestamp). Manejar `KeyboardInterrupt` limpiamente.
- **Criterio**: `python -m wispr` desde el venv arranca la app, aparece el ícono en tray, se puede grabar con CapsLock y el texto se inyecta. Comportamiento idéntico al `mvp_local.py` original.
- **⚡ Performance**: El orden de inicialización es crítico. Los threads de overlay, transcription_worker y load_model se inician ANTES de `start_tray()` para que el main thread no se bloquee antes de lanzarlos. `tray.start_tray()` DEBE ser el último paso (bloquea el main thread hasta que el usuario cierra).
- [ ] completado

---

### 1.12 Mover scripts de diagnóstico a `tools/`
- **FR**: FR-01
- **Archivos**: `tools/mvp_original.py`, `tools/verificar_gpu.py`, `tools/prueba_mic_hotkey.py`, `tools/test_transcripcion.py`
- **Qué hacer**: (1) Copiar `mvp_local.py` → `tools/mvp_original.py`. (2) Mover `verificar_gpu.py`, `prueba_mic_hotkey.py`, `test_transcripcion.py` a `tools/`. (3) `git rm` los archivos originales de la raíz. (4) `git rm "lanzador - Shortcut.lnk"`. (5) NO eliminar aún `mvp_local.py` de la raíz — queda hasta que el refactor esté verificado.
- **Criterio**: `tools/mvp_original.py` existe y es ejecutable. Los scripts de diagnóstico están en `tools/`. `lanzador - Shortcut.lnk` no está en el repo.
- [ ] completado

---

### 1.13 Smoke test manual — Fase 1
- **FR**: FR-01, FR-11
- **Archivos**: ninguno
- **Qué hacer**: Verificar manualmente que la Fase 1 está completa: (1) `python -m wispr` arranca sin errores, (2) ícono en tray aparece, (3) CapsLock graba y el texto se inyecta, (4) Alt+Shift togglea modo continuo, (5) "Salir" desde tray cierra limpiamente. Si algo falla: `git checkout v0.1.0-mvp` restaura el MVP.
- **Criterio**: Todos los escenarios anteriores funcionan. Crear commit: `refactor: extract wispr/ package from mvp_local.py`.
- [ ] completado

---

## Fase 2: Config TOML

**Objetivo**: Externalizar todos los valores hardcodeados a `config.toml`. Al final de esta fase, el usuario puede personalizar modelo, device, sample_rate y hotkeys (parcialmente) editando el TOML sin tocar código.

**Criterio de éxito**: `config.toml` con `device = "cpu"` hace que la app use CPU. Modificar `model.name` cambia qué modelo carga. Los defaults reproducen el comportamiento de Fase 1 exactamente.

**Tag de rollback**: `v0.2.0-config`

---

### 2.1 Crear `config.toml` con schema completo
- **FR**: FR-03
- **Archivos**: `config.toml`
- **Qué hacer**: Crear el archivo `config.toml` con el schema completo del design (secciones: `[model]`, `[audio]`, `[hotkeys]`, `[overlay]`, `[transcription]`). Incluir comentarios descriptivos en español explicando cada opción. Valores default: device=cuda, model=large-v3, compute_type=float16, ptt=caps_lock, toggle=["alt","shift"], overlay.enabled=true, overlay.position=bottom-right.
- **Criterio**: El archivo existe, es un TOML válido (`python -c "import tomllib; tomllib.load(open('config.toml','rb'))"` no lanza error), y contiene todas las secciones.
- [ ] completado

---

### 2.2 Implementar `wispr/config.py` — carga, merge y validación
- **FR**: FR-03
- **Archivos**: `wispr/config.py`
- **Qué hacer**: Implementar `load_config(path: str = "config.toml") -> dict`. Lógica: (1) definir `DEFAULTS` dict completo, (2) si el archivo no existe: crearlo con defaults y retornar defaults, (3) leer con `tomllib`, (4) merge profundo con DEFAULTS (los campos faltantes toman el default), (5) validar invariantes (device, compute_type, overlay.position, overlay.opacity, audio.sample_rate), (6) emitir `logging.warning` si hotkeys conflictúan con Win+L o Ctrl+Alt+Del. Lanzar `ValueError` con mensaje descriptivo si hay campo inválido.
- **Criterio**: (1) Sin config.toml → crea el archivo y retorna defaults. (2) Config parcial con solo `[hotkeys]` → retorna dict completo con resto de defaults. (3) `device = "tpu"` → `ValueError` con "device" y valores aceptados en el mensaje. (4) `python -c "from wispr.config import load_config; c = load_config(); print(c)"` muestra el dict sin errores.
- [ ] completado

---

### 2.3 Actualizar `wispr/__main__.py` para usar config real
- **FR**: FR-03, FR-11
- **Archivos**: `wispr/__main__.py`
- **Qué hacer**: Reemplazar el dict de defaults hardcodeado por `config.load_config()`. Manejar `ValueError` de config inválida: loguear el error y `sys.exit(1)`. Loguear al arrancar: `"WisprLocal iniciando... PTT: {ptt_key} | Toggle: {toggle_keys}"`.
- **Criterio**: Con `config.toml` válido la app arranca normal. Con `device = "tpu"` la app loguea el error y sale con código 1 (verificar con `echo $?` o `echo %errorlevel%`).
- [ ] completado

---

### 2.4 Actualizar módulos para leer desde config (audio y transcription)
- **FR**: FR-03, FR-06, FR-07
- **Archivos**: `wispr/audio.py`, `wispr/transcription.py`
- **Qué hacer**: Reemplazar las constantes hardcodeadas por lecturas del dict `config`: `audio.py` lee `config["audio"]["sample_rate"]`, `config["audio"]["channels"]`, `config["audio"]["dtype"]`. `transcription.py` lee `config["model"]["name"]`, `config["model"]["device"]`, `config["model"]["compute_type"]`, `config["transcription"]["language"]`, `config["transcription"]["prompt"]`.
- **Criterio**: Cambiar `compute_type = "int8"` en `config.toml` y reiniciar la app → el modelo carga con int8 (verificar en los logs de faster_whisper).
- [ ] completado

---

### 2.5 Smoke test manual — Fase 2
- **FR**: FR-03
- **Archivos**: ninguno
- **Qué hacer**: Verificar: (1) app arranca con config.toml default y funciona igual que Fase 1, (2) cambiar `model.device = "cpu"` y reiniciar → usa CPU (más lento, pero sin error), (3) `device = "tpu"` → error claro y salida con código 1, (4) eliminar config.toml, reiniciar → se recrea con defaults y la app funciona. Crear commit: `feat: add config.toml with tomllib-based config system`.
- **Criterio**: Todos los escenarios anteriores pasan. Tag: `v0.2.0-config`.
- [ ] completado

---

## Fase 3: Overlay Visual

**Objetivo**: Agregar el indicador visual de grabación — una ventana tkinter transparente, siempre encima, en la esquina de pantalla, que muestra el estado de la app en tiempo real.

**Criterio de éxito**: Al presionar CapsLock aparece un rectángulo rojo con "● REC PTT" en la esquina inferior derecha. Al soltar desaparece. Alt+Shift muestra naranja con "● REC TOGGLE". El overlay no bloquea ni retrasa el audio, el teclado, ni la transcripción.

**Tag de rollback**: `v0.3.0-overlay`

---

### 3.1 Implementar `wispr/overlay.py` — RecordingOverlay real
- **FR**: FR-04
- **Archivos**: `wispr/overlay.py`
- **Qué hacer**: Reemplazar el stub de Fase 1 con la implementación real. `RecordingOverlay.__init__(config)` crea un `threading.Thread(daemon=True)` que ejecuta `_run()`. En `_run()`: crear `tk.Tk()`, configurar `overrideredirect(True)`, `wm_attributes('-topmost', True)`, `wm_attributes('-alpha', opacity)`, crear `tk.Label` con texto y color. Implementar `show_ptt()`, `show_toggle()`, `show_loading()`, `hide()` — todos usan `self.root.after(0, fn)` para ser thread-safe. Si `config["overlay"]["enabled"] == False`: todos los métodos son no-op, no crear ningún widget. Posicionar según `config["overlay"]["position"]` usando `winfo_screenwidth()` / `winfo_screenheight()`. Documentar en comentario que NO funciona sobre fullscreen exclusivo.
- **Criterio**: Con `enabled = true`, al llamar `overlay.show_ptt()` desde cualquier thread, aparece la ventana roja en la esquina correcta en < 50ms. `hide()` la oculta. Con `enabled = false`, no se crea ninguna ventana tkinter.
- **⚡ Performance**: CRÍTICO — el thread del overlay corre `tk.mainloop()` que bloquea. Todos los updates al overlay DEBEN ir via `root.after(0, fn)` — es la única forma thread-safe de comunicarse con tkinter desde otros threads. NUNCA llamar métodos tkinter directamente desde el thread de pynput o el callback de PortAudio. El overlay debe aparecer en < 50ms después de que `show_ptt()` es llamado.
- [ ] completado

---

### 3.2 Integrar overlay con hotkeys
- **FR**: FR-04, FR-05
- **Archivos**: `wispr/hotkeys.py`, `wispr/__main__.py`
- **Qué hacer**: Actualizar `hotkeys.py` para que los callbacks de pynput llamen `overlay.show_ptt()`, `overlay.show_toggle()`, y `overlay.hide()` en los momentos correctos. En `__main__.py`, pasar la instancia de `RecordingOverlay` al `start_listener()`. Asegurarse de que `RecordingOverlay` está iniciado (thread corriendo) ANTES de iniciar el listener.
- **Criterio**: Al presionar CapsLock → overlay rojo aparece inmediatamente (< 50ms). Al soltar → overlay desaparece. Al presionar Alt+Shift → overlay naranja. Al volver a presionar Alt+Shift → overlay desaparece.
- **⚡ Performance**: Los callbacks de pynput son sincrónicos. La llamada `overlay.show_ptt()` debe retornar en microsegundos — solo hace `root.after(0, fn)` que es O(1). El update visual real ocurre en el thread de tkinter, sin bloquear pynput.
- [ ] completado

---

### 3.3 Agregar estado "loading" al overlay y tray
- **FR**: FR-04, FR-10
- **Archivos**: `wispr/transcription.py`, `wispr/tray.py`
- **Qué hacer**: En `transcription.py`, al iniciar `load_model()` llamar `overlay.show_loading()` si overlay está disponible. Al terminar, llamar `overlay.hide()`. En `tray.py`, actualizar el ícono y tooltip al gris+puntos durante carga, verde al terminar, gris sólido si no hay modelo. Actualizar tooltip para mostrar `"WisprLocal — Cargando modelo..."`, `"WisprLocal — Modelo: {name} | PTT: {ptt} | Toggle: {toggle}"`, etc.
- **Criterio**: Al arrancar la app, el overlay muestra "⏳ Cargando..." y el tray muestra gris. Cuando el modelo carga, el overlay desaparece, el tray se pone verde y el tooltip cambia. Suena el beep de ready.
- [ ] completado

---

### 3.4 Smoke test manual — Fase 3
- **FR**: FR-04
- **Archivos**: ninguno
- **Qué hacer**: Verificar: (1) overlay aparece en la esquina correcta al grabar, (2) colores correctos para PTT (rojo) y toggle (naranja), (3) overlay de carga (gris) al arrancar y desaparece al cargar modelo, (4) `enabled = false` desactiva el overlay sin errores, (5) app responde al teclado sin retraso visible incluso mientras el overlay está visible, (6) transcripción funciona igual que Fase 2. Crear commit: `feat: add recording overlay with tkinter`.
- **Criterio**: Todos los escenarios anteriores pasan. Tag: `v0.3.0-overlay`.
- [ ] completado

---

## Fase 4: Hotkeys Configurables

**Objetivo**: Que las teclas de PTT y Toggle se lean desde `config.toml` en vez de estar hardcodeadas.

**Criterio de éxito**: Cambiar `ptt = "f9"` en `config.toml`, reiniciar → F9 activa grabación. Cambiar `toggle = ["ctrl", "f10"]` → ese combo activa toggle. Una tecla inválida en config produce un error claro al arrancar.

**Tag de rollback**: `v0.4.0-hotkeys`

---

### 4.1 Implementar `resolve_key()` — string a pynput Key
- **FR**: FR-05
- **Archivos**: `wispr/hotkeys.py`
- **Qué hacer**: Implementar `resolve_key(key_str: str) -> pynput.keyboard.Key | pynput.keyboard.KeyCode`. Lógica: (1) intentar `pynput.keyboard.Key[key_str]` para teclas especiales (caps_lock, f9, alt, shift, ctrl, etc.), (2) si falla `KeyError`, intentar `pynput.keyboard.KeyCode.from_char(key_str)` para caracteres simples, (3) si ambos fallan, lanzar `ValueError(f"Hotkey no reconocida: '{key_str}'")`. Cubrir al menos: caps_lock, f1-f12, alt, shift, ctrl, scroll_lock, pause, insert, home, end, page_up, page_down.
- **Criterio**: `resolve_key("caps_lock")` retorna `Key.caps_lock`. `resolve_key("f9")` retorna `Key.f9`. `resolve_key("a")` retorna `KeyCode.from_char("a")`. `resolve_key("supr_izq")` lanza `ValueError`.
- [ ] completado

---

### 4.2 Actualizar `hotkeys.py` para leer teclas desde config
- **FR**: FR-05
- **Archivos**: `wispr/hotkeys.py`
- **Qué hacer**: En `start_listener()`, leer `config["hotkeys"]["ptt"]`, `config["hotkeys"]["toggle"]`, `config["hotkeys"]["load_model"]`. Llamar `resolve_key()` al iniciar (falla rápido si la config es inválida). Reemplazar las comparaciones hardcodeadas (`key == keyboard.Key.caps_lock`, `'alt' in modifiers`, etc.) por comparaciones dinámicas usando las teclas resueltas. Para combos (lista de teclas), trackear qué teclas del combo están presionadas simultáneamente via un `set` de keys activas. Si `load_model` no está vacío, implementar ese binding también.
- **Criterio**: Cambiar `ptt = "f12"` en config.toml → F12 activa PTT. Cambiar `toggle = ["ctrl", "f10"]` → ese combo activa toggle. Tecla inválida en config → `ValueError` con mensaje claro al intentar iniciar el listener (la app no arranca).
- [ ] completado

---

### 4.3 Agregar validación de hotkeys en `config.py`
- **FR**: FR-03, FR-05
- **Archivos**: `wispr/config.py`
- **Qué hacer**: En `load_config()`, después de cargar y mergear el TOML, verificar que `hotkeys.ptt` sea un string no vacío y que `hotkeys.toggle` sea una lista de strings. Emitir `logging.warning` si detecta Win+L (`["win", "l"]`) o Ctrl+Alt+Del equivalente. No lanzar excepción por hotkeys — el error detallado viene de `resolve_key()` al iniciar el listener.
- **Criterio**: `load_config()` con `hotkeys.ptt = 123` (número) lanza `ValueError`. Con combo `["win", "l"]` emite warning en log pero no falla.
- [ ] completado

---

### 4.4 Smoke test manual — Fase 4
- **FR**: FR-05
- **Archivos**: ninguno
- **Qué hacer**: Verificar: (1) config default (caps_lock / alt+shift) funciona igual que antes, (2) cambiar a `ptt = "f9"` y `toggle = ["ctrl", "f10"]` → ambos funcionan correctamente, (3) tecla inválida en config → error claro al arrancar (no crash silencioso), (4) overlay y sonidos siguen funcionando con las nuevas teclas. Crear commit: `feat: configurable hotkeys from config.toml`.
- **Criterio**: Todos los escenarios pasan. Tag: `v0.4.0-hotkeys`.
- [ ] completado

---

## Fase 5: Instalador

**Objetivo**: Crear `install.py` que automatice el setup completo para un usuario nuevo con Python 3.12 pero sin venv ni dependencias.

**Criterio de éxito**: En una máquina con Python 3.12 y GPU NVIDIA, ejecutar `python install.py` completa todo el setup sin errores y genera un `lanzador.vbs` funcional que arranca WisprLocal.

**Tag de rollback**: `v0.5.0-installer`

---

### 5.1 Crear `requirements.txt`
- **FR**: FR-12
- **Archivos**: `requirements.txt`
- **Qué hacer**: Crear `requirements.txt` con versiones mínimas: `faster-whisper>=1.0.0`, `sounddevice>=0.4.6`, `numpy>=1.24.0`, `pynput>=1.7.6`, `pystray>=0.19.4`, `Pillow>=10.0.0`, `pyperclip>=1.8.2`. NO incluir torch (se instala separado por `install.py` con el índice CUDA correcto).
- **Criterio**: El archivo existe y es un requirements.txt válido. `pip install -r requirements.txt` (en un venv limpio sin torch) instala todas las dependencias sin error.
- [ ] completado

---

### 5.2 Crear `install.py` — verificación y venv
- **FR**: FR-12
- **Archivos**: `install.py`
- **Qué hacer**: Implementar las primeras 3 etapas del instalador usando solo stdlib: (1) `[1/5] Verificando Python...` — verificar `sys.version_info >= (3, 12)`, si falla mostrar mensaje con URL de descarga Python y `sys.exit(1)`, (2) `[2/5] Detectando GPU...` — `subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'])`, capturar output y fallo, (3) `[3/5] Creando entorno virtual...` — `venv.create('.venv', with_pip=True)`. Mostrar progreso con prefijo `[N/5]`.
- **Criterio**: En Python 3.11: muestra error claro y sale. En Python 3.12 sin GPU: detecta CPU-only y continúa. Crea `.venv/` correctamente.
- [ ] completado

---

### 5.3 Completar `install.py` — instalación de dependencias y lanzador
- **FR**: FR-12
- **Archivos**: `install.py`
- **Qué hacer**: Continuar el instalador: (4) `[4/5] Instalando dependencias...` — si GPU detectada: instalar PyTorch con `https://download.pytorch.org/whl/cu121`, luego `pip install -r requirements.txt` (5) `[5/5] Generando lanzador...` — generar `lanzador.vbs` con rutas absolutas al `.venv/Scripts/pythonw.exe` y al directorio del proyecto usando `pathlib.Path(__file__).parent.resolve()`. Preguntar si desea startup automático. Si responde `s`/`S`, copiar a `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`. Mostrar resumen final con todas las rutas y pasos para lanzar manualmente.
- **Criterio**: El `lanzador.vbs` generado tiene rutas absolutas correctas. `cscript lanzador.vbs` arranca WisprLocal. Si el usuario elige startup, el archivo aparece en la carpeta Startup de Windows.
- [ ] completado

---

### 5.4 Smoke test manual — Fase 5
- **FR**: FR-12
- **Archivos**: ninguno
- **Qué hacer**: En un directorio fresco (sin `.venv/`), ejecutar `python install.py`. Verificar: (1) todas las etapas muestran progreso, (2) `.venv/` se crea con las dependencias instaladas, (3) `lanzador.vbs` se genera con rutas correctas, (4) doble clic en `lanzador.vbs` arranca WisprLocal sin ventana de consola, (5) el ícono aparece en tray. Crear commit: `feat: add automated installer with GPU detection`.
- **Criterio**: Setup completo en < 10 minutos de instalación manual. Tag: `v0.5.0-installer`.
- [ ] completado

---

## Fase 6: Documentación y Limpieza

**Objetivo**: Dejar el repo en estado production-ready para ser público: README profesional, limpieza de archivos residuales, `.gitignore` actualizado.

**Criterio de éxito**: Un usuario que llega al repo por primera vez puede instalar y usar WisprLocal siguiendo solo el README, sin buscar ayuda adicional.

**Tag de rollback**: `v1.0.0`

---

### 6.1 Actualizar `.gitignore`
- **FR**: FR-01
- **Archivos**: `.gitignore`
- **Qué hacer**: Agregar entradas: `.venv/`, `__pycache__/`, `*.pyc`, `*.pyo`, `openspec/` (artefactos SDD), `.atl/`, `*.lnk` (evitar shortcuts binarios futuros), `lanzador.vbs` (se genera por install.py, no pertenece en el repo), `config.toml` (config local del usuario — documentar que install.py lo genera).
- **Criterio**: `git status` no muestra `.venv/`, `__pycache__/`, ni `lanzador.vbs` como untracked. Un `git add .` no agrega accidentalmente el venv.
- [ ] completado

---

### 6.2 Eliminar archivos residuales del repo
- **FR**: FR-01
- **Archivos**: `mvp_local.py` (raíz)
- **Qué hacer**: Verificar que `tools/mvp_original.py` existe y es idéntico a `mvp_local.py`. Si está confirmado, `git rm mvp_local.py`. Verificar también que `lanzador - Shortcut.lnk` ya fue eliminado en Fase 1 (task 1.12). Si quedó algún archivo residual de prueba en la raíz, moverlo a `tools/` o eliminarlo.
- **Criterio**: La raíz del proyecto contiene exactamente: `wispr/`, `tools/`, `install.py`, `requirements.txt`, `README.md`, `.gitignore`, `config.toml.example` (opcional), `lanzador.vbs` (si no está en .gitignore). No hay `mvp_local.py` ni `.lnk` files.
- [ ] completado

---

### 6.3 Reescribir README.md completo
- **FR**: propuesta — Documentación profesional
- **Archivos**: `README.md`
- **Qué hacer**: Reescribir el README con: (1) título + descripción de 2 líneas que explica qué hace el proyecto, (2) badges de Python version, Windows-only, license, (3) sección "¿Qué es WisprLocal?" — 3-4 bullets con los beneficios clave (local, sin nube, bilingüe, gaming-friendly), (4) sección "Instalación en 3 pasos" con código copiable, (5) sección "Configuración" con los campos más importantes de config.toml y ejemplos, (6) sección "Teclas por defecto" con tabla PTT/Toggle, (7) sección "Troubleshooting" con los 5 errores más comunes (GPU no detectada, micrófono no encontrado, CapsLock no responde, overlay no visible, modelo no carga), (8) sección "Arquitectura" con el diagrama de módulos y threading model (resumen del design), (9) sección "Contribuir" con convenciones de commits y estructura del proyecto.
- **Criterio**: Un usuario sin conocimiento previo puede instalar y usar WisprLocal leyendo solo el README. La sección de troubleshooting cubre los errores reales que puede encontrar.
- [ ] completado

---

### 6.4 Verificación final end-to-end
- **FR**: todos
- **Archivos**: ninguno
- **Qué hacer**: Simular la experiencia de un usuario nuevo: (1) clonar el repo en un directorio fresco, (2) ejecutar `python install.py` y seguir las instrucciones, (3) doble clic en `lanzador.vbs`, (4) esperar que el modelo cargue (beep de ready), (5) dictar texto con CapsLock en inglés y en español, (6) verificar que el texto se inyecta correctamente en Notepad, (7) cerrar desde tray ("Salir"), (8) verificar que no quedan procesos zombie (`tasklist | grep pythonw`). Documentar cualquier problema encontrado y resolverlo.
- **Criterio**: El flujo completo funciona sin errores ni intervención manual más allá de los 3 pasos del README. Crear commit final: `chore: cleanup and finalize for public release`. Tag: `v1.0.0`.
- [ ] completado

---

## Resumen

| Fase | Tasks | Tag |
|------|-------|-----|
| Fase 1: Refactor Estructural | 1.1 – 1.13 (13 tasks) | `v0.1.0-mvp` → `v1.1-refactor` |
| Fase 2: Config TOML | 2.1 – 2.5 (5 tasks) | `v0.2.0-config` |
| Fase 3: Overlay Visual | 3.1 – 3.4 (4 tasks) | `v0.3.0-overlay` |
| Fase 4: Hotkeys Configurables | 4.1 – 4.4 (4 tasks) | `v0.4.0-hotkeys` |
| Fase 5: Instalador | 5.1 – 5.4 (4 tasks) | `v0.5.0-installer` |
| Fase 6: Documentación y Limpieza | 6.1 – 6.4 (4 tasks) | `v1.0.0` |
| **Total** | **30 tasks** | |

### Tasks con ⚡ Performance (threading/latencia)

| Task | Riesgo |
|------|--------|
| 1.3 `state.py` | audio_queue sin lock adicional — el GIL es suficiente para bools |
| 1.4 `sounds.py` | cada beep en daemon thread — retorno inmediato del caller |
| 1.6 `audio.py` | callback de PortAudio debe ser O(1) — sin I/O, sin logging |
| 1.7 `transcription.py` | transcription_worker en daemon thread separado — nunca bloquea hotkeys ni overlay |
| 1.8 `hotkeys.py` | callbacks de pynput deben ser O(1) — sin esperas |
| 1.11 `__main__.py` | orden de inicialización crítico — todos los threads antes de `start_tray()` |
| 3.1 `overlay.py` | updates via `root.after(0, fn)` — única forma thread-safe con tkinter |
| 3.2 integración overlay | `show_ptt()` retorna en microsegundos — el update visual es asíncrono |
