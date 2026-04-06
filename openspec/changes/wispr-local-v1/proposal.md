# Proposal: wispr-local-v1

## Intent

WisprLocal es un MVP funcional de Voice-to-Text local que resuelve un problema real: dictado bilingue sin nube, con gestión de VRAM para gaming. Pero su estado actual (un solo archivo de 170 líneas, sin tests, hardcoded hotkeys, sin feedback visual, instalación manual de 15 pasos) lo hace inviable como proyecto público.

El objetivo es transformar el MVP en un proyecto open-source de calidad que cualquier usuario con una GPU NVIDIA pueda instalar y usar en minutos, sin tocar código.

**Por qué ahora**: El repo ya se hizo público (commit `3184263`). Cada día que pasa con la estructura actual es deuda técnica que acumula.

## Scope

### IN (dentro del alcance)

1. **Arquitectura modular**: Descomponer `mvp_local.py` en módulos con responsabilidades claras
2. **Overlay visual**: Indicador en pantalla (siempre visible, sin importar la app activa) que muestre estado de grabación
3. **Hotkeys configurables**: Archivo de configuración (`config.yaml` o `config.toml`) + GUI mínima para editar hotkeys sin tocar código
4. **Instalador automático**: Script `install.py` que detecte GPU, cree venv, instale dependencias, configure lanzador
5. **Documentación profesional**: README con GIF demo, badges, instrucciones de 3 pasos, troubleshooting expandido
6. **Limpieza de repo**: Mover scripts de prueba (`prueba_mic_hotkey.py`, `test_transcripcion.py`, `verificar_gpu.py`) a directorio `tools/` o eliminar

### OUT (fuera del alcance)

- Soporte cross-platform (Linux/macOS) — Windows-only es una decisión de diseño, no una limitación
- Soporte para modelos alternativos (solo faster-whisper con large-v3)
- GUI completa de configuración (solo hotkeys por ahora)
- Auto-update o sistema de releases con binarios empaquetados
- Tests automatizados (el proyecto depende de hardware GPU + audio — verificación manual)
- Internacionalización de la UI (queda en español con comentarios bilingues)

## Approach

### Decisiones arquitectónicas clave

1. **Configuración antes que código**: Toda personalización (hotkeys, modelo, device, compute_type, sample_rate) se mueve a un archivo `config.yaml` que se lee al arrancar. Esto elimina la necesidad de editar código fuente.

2. **Módulos por dominio, no por capa técnica**: En vez de `utils/`, `services/`, `models/` (que no dicen nada), los módulos se nombran por lo que HACEN: `audio`, `transcription`, `hotkeys`, `overlay`, `tray`, `config`.

3. **Overlay con tkinter**: Para el indicador visual usamos `tkinter` (viene con Python, cero dependencias extra). Un `Toplevel` sin bordes, siempre-encima (`-topmost`), con transparencia (`-alpha`), posicionado en esquina. Simple, nativo, sin DLL externas.

4. **Configuración de hotkeys via YAML**: El archivo `config.yaml` define las teclas. Para la GUI mínima, un diálogo tkinter que lea/escriba el YAML. No se necesita framework externo.

5. **Instalador como script Python puro**: `install.py` que use solo stdlib para detectar Python, crear venv, detectar GPU via subprocess (`nvidia-smi`), instalar PyTorch con el índice CUDA correcto, y generar `lanzador.vbs` con las rutas correctas del usuario.

6. **Entry point limpio**: Un `__main__.py` dentro del paquete `wispr/` que orqueste el arranque. El `lanzador.vbs` apunta a `pythonw.exe -m wispr`.

### Patrón de inyección de dependencias ligero

No usamos frameworks DI. Cada módulo expone funciones o clases con dependencias explícitas en el constructor/parámetros. El `__main__.py` es el composition root que conecta todo.

### Gestión de estado

El estado global actual (`ptt_active`, `toggle_active`, `model`, etc.) se encapsula en una clase `AppState` que se pasa por referencia a los módulos que lo necesitan. Esto elimina las variables globales sin agregar complejidad innecesaria.

## Module Decomposition

```
wispr/
├── __init__.py          # Package marker
├── __main__.py          # Entry point: composition root, arranque
├── state.py             # AppState dataclass: ptt_active, toggle_active, model ref, etc.
├── config.py            # Carga/valida config.yaml, defaults, schema
├── audio.py             # InputStream setup, audio_queue management, callback
├── transcription.py     # WhisperModel load/unload, transcribe, VRAM cleanup
├── hotkeys.py           # Keyboard listener, key mapping from config, press/release logic
├── overlay.py           # Tkinter overlay: show/hide recording indicator
├── tray.py              # System tray icon: menu, state display, actions
├── injection.py         # Clipboard copy + Ctrl+V simulation
└── sounds.py            # Feedback auditivo (winsound.Beep wrappers)

config.yaml              # User configuration (hotkeys, model, device, etc.)
install.py               # Automated installer script
tools/
├── verificar_gpu.py     # GPU diagnostic (movido desde raíz)
├── prueba_mic_hotkey.py # Mic test (movido desde raíz)
└── test_transcripcion.py # Transcription test (movido desde raíz)
```

### Responsabilidades por módulo

| Módulo | Responsabilidad | Dependencias |
|--------|----------------|-------------|
| `state.py` | Dataclass con estado compartido de la app | ninguna |
| `config.py` | Leer `config.yaml`, merge con defaults, validar | `pyyaml` |
| `audio.py` | Crear/gestionar InputStream, encolar audio | `sounddevice`, `numpy`, `state` |
| `transcription.py` | Load/unload modelo, transcribir audio | `faster_whisper`, `torch`, `state` |
| `hotkeys.py` | Listener de teclado, mapeo configurable de teclas | `pynput`, `config`, `state` |
| `overlay.py` | Ventana transparente siempre-encima como indicador | `tkinter` (stdlib) |
| `tray.py` | Icono en system tray con menú contextual | `pystray`, `Pillow`, `state` |
| `injection.py` | Copiar texto al clipboard e inyectar via Ctrl+V | `pyperclip`, `pynput` |
| `sounds.py` | Beeps de feedback (start/stop/ready) | `winsound` (stdlib) |
| `__main__.py` | Composición: crea state, carga config, conecta módulos, arranca threads | todos los anteriores |

## UX Changes

### Para el usuario final

1. **Overlay visual de grabación**: Indicador circular/barra en esquina de pantalla (configurable) que se muestra cuando está grabando. Colores: rojo pulsante = grabando PTT, naranja = toggle activo, sin overlay = idle. Visible sobre cualquier aplicación (juegos en ventana, editores, browsers).

2. **Hotkeys personalizables**: En vez de hardcoded `CapsLock` y `Alt+Shift`, el usuario edita `config.yaml` o usa click-derecho en tray > "Configurar Teclas" para un diálogo simple donde asigna:
   - Tecla PTT (push-to-talk)
   - Combo Toggle (dictado continuo)
   - (Opcional) tecla para cargar/descargar modelo

3. **Instalación de 3 pasos**:
   ```
   1. Instalar Python 3.12
   2. Ejecutar: python install.py
   3. Reiniciar (o ejecutar el acceso directo)
   ```

4. **Tray mejorado**: Tooltip con info útil (modelo cargado, VRAM usada, hotkeys activas). Icono con estados más claros.

### Para el desarrollador/contribuidor

1. Estructura de módulos clara — cada archivo hace UNA cosa
2. Config externalizada — no hay que tocar código para personalizar
3. README con sección de contribución y arquitectura

## Risks

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| **Overlay interfiere con juegos fullscreen** | Alta | Media | Overlay solo aparece en modo ventana/windowed. Documentar limitación. Opción en config para desactivar overlay y usar solo beeps. |
| **tkinter event loop conflicta con pystray** | Media | Alta | tkinter corre en su propio thread. pystray ya corre en thread separado. Comunicación via `state` compartido + `tkinter.after()` para updates thread-safe. Probar exhaustivamente. |
| **Hotkeys configurables rompen combinaciones del sistema** | Media | Media | Validar en `config.py` que las teclas elegidas no sean combinaciones reservadas de Windows (Win+L, Ctrl+Alt+Del, etc.). Warning en logs si se detecta conflicto. |
| **Instalador falla en configuraciones exóticas de Python** | Media | Media | Detección robusta: buscar Python en PATH, `py` launcher, rutas comunes. Mensajes de error claros con instrucciones de fallback manual. |
| **PyYAML como nueva dependencia** | Baja | Baja | Es una dependencia estable y mínima. Alternativa: usar `tomllib` (stdlib en 3.11+) con TOML en vez de YAML — elimina dependencia extra. **Decisión pendiente en Open Questions.** |
| **Refactor rompe funcionalidad existente** | Media | Alta | Refactor incremental: primero extraer módulos sin cambiar comportamiento, verificar manualmente que funciona, luego agregar features nuevas. |

## Rollback Plan

1. **Git tags**: Crear tag `v0.1.0-mvp` ANTES de empezar el refactor. Si algo se rompe irreparablemente, `git checkout v0.1.0-mvp` restaura el MVP funcional.

2. **Refactor incremental**: Cada fase es un commit atómico:
   - Fase 1: Crear estructura de módulos + mover código (sin cambiar comportamiento)
   - Fase 2: Agregar config.yaml
   - Fase 3: Agregar overlay
   - Fase 4: Agregar hotkeys configurables
   - Fase 5: Crear instalador
   - Fase 6: Documentación

   Si una fase falla, revertimos solo esa fase. Las anteriores quedan estables.

3. **MVP preserved**: `mvp_local.py` original se mantiene en el repo (movido a `tools/mvp_original.py`) como referencia y fallback de emergencia hasta que el refactor esté verificado.

## Affected Files

### Archivos CREADOS

| Archivo | Propósito |
|---------|-----------|
| `wispr/__init__.py` | Package marker |
| `wispr/__main__.py` | Entry point y composition root |
| `wispr/state.py` | Estado compartido de la aplicación |
| `wispr/config.py` | Carga y validación de configuración |
| `wispr/audio.py` | Gestión de stream de audio |
| `wispr/transcription.py` | Carga de modelo y transcripción |
| `wispr/hotkeys.py` | Listener de teclado configurable |
| `wispr/overlay.py` | Indicador visual de grabación |
| `wispr/tray.py` | System tray icon y menú |
| `wispr/injection.py` | Inyección de texto via clipboard |
| `wispr/sounds.py` | Feedback auditivo |
| `config.yaml` | Configuración del usuario |
| `install.py` | Script de instalación automática |
| `tools/` | Directorio para scripts de diagnóstico |

### Archivos MODIFICADOS

| Archivo | Cambio |
|---------|--------|
| `README.md` | Reescritura completa: badges, GIF, instalación simplificada, arquitectura |
| `.gitignore` | Agregar entradas para openspec/, .atl/ si no están |
| `lanzador.vbs` | Template dinámico generado por install.py (o documentar cómo generarlo) |

### Archivos MOVIDOS

| Origen | Destino |
|--------|---------|
| `prueba_mic_hotkey.py` | `tools/prueba_mic_hotkey.py` |
| `test_transcripcion.py` | `tools/test_transcripcion.py` |
| `verificar_gpu.py` | `tools/verificar_gpu.py` |
| `mvp_local.py` | `tools/mvp_original.py` (preservado como referencia) |

### Archivos ELIMINADOS

| Archivo | Razón |
|---------|-------|
| `lanzador - Shortcut.lnk` | Archivo binario de acceso directo — no pertenece en un repo público. El instalador lo genera automáticamente. |

## Open Questions

1. **YAML vs TOML para configuración**: `tomllib` es stdlib desde Python 3.11+ (eliminando PyYAML como dependencia), pero TOML es menos familiar para usuarios no-técnicos. YAML es más legible pero agrega una dependencia. **Recomendación**: TOML — una dependencia menos, Python 3.12 lo incluye.

2. **Posición del overlay**: Esquina fija (ej: bottom-right) o configurable? Agregar a config.yaml como `overlay.position: bottom-right`? **Recomendación**: configurable con default bottom-right.

3. **GUI de hotkeys**: Diálogo tkinter propio vs solo editar config file? La GUI agrega complejidad. **Recomendación**: v1 solo config file + documentación clara. GUI de hotkeys como mejora futura.

4. **Alcance del instalador**: Solo instalar dependencias, o también configurar inicio automático (startup)? **Recomendación**: el instalador ofrece ambas opciones — instalación base obligatoria, startup automático opcional (pregunta al usuario).

5. **Nombre del paquete**: `wispr/` como nombre de paquete o algo más descriptivo como `wispr_local/`? **Recomendación**: `wispr/` — corto, claro, no hay conflicto con PyPI (no se publica).

6. **requirements.txt o pyproject.toml**: Para gestión de dependencias del proyecto. **Recomendación**: `requirements.txt` por simplicidad — el público objetivo no son desarrolladores Python avanzados. Agregar `pyproject.toml` como mejora futura.
