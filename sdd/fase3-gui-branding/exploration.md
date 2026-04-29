## Exploration: WisprLocal Fase 3 — GUI Installer + Branding

### Current State

WisprLocal es una app de dictado por voz local (Python 3.12) con arquitectura modular:

- **Instalación**: `install.py` basado en terminal. Detecta GPU, crea venv, instala PyTorch+dependencias, genera `lanzador.vbs` y pregunta por autostart.
- **GUI existente**: `overlay.py` usa `tkinter` en un thread daemon para mostrar estados (PTT, toggle, loading, error). `tray.py` usa `pystray` con un ícono generado programáticamente (cuadrado de colores vía PIL).
- **Configuración**: `config.toml` editado manualmente. `config.py` maneja defaults, merge y validación.
- **Entry point**: `wispr/__main__.py` detecta `is_first_run` pero solo loguea un warning en macOS.
- **Cross-platform**: abstracción `wispr/platform/` (Windows/Linux/macOS).
- **Sin assets gráficos**: no hay iconos, imágenes, ni splash screen.
- **Sin auto-updater**.
- **README**: profesional pero sin screenshots, GIFs, ni comparativas visuales.

### Affected Areas

| Archivo / Directorio | Por qué se ve afectado |
|----------------------|------------------------|
| `install.py` | Se reemplaza o complementa con instalador visual |
| `wispr/tray.py` | Agregar menú "Configuración", iconos reales, estados visuales |
| `wispr/config.py` | Leer/escribir config desde GUI; validar nuevos campos |
| `wispr/overlay.py` | Ya usa tkinter; alineable con customtkinter para consistencia visual |
| `wispr/__main__.py` | Extender `is_first_run` para lanzar onboarding wizard |
| `requirements.txt` | Posible agregado de `customtkinter`, `pyinstaller` (dev), `requests` |
| `README.md` | Marketing polish: screenshots, GIFs, badges, tabla de comparación |
| `tools/` | Nuevos scripts: `generate_icons.py`, `build_installer.py` |
| Nuevo: `assets/icons/` | Iconos de app y tray en múltiples resoluciones y estados |
| Nuevo: `installer/` | Scripts/specs de PyInstaller, Inno Setup, etc. |

---

### Approaches

#### 1. GUI Installer

**A. tkinter nativo wizard**
- Pros: built-in en Python, cero dependencias, `overlay.py` ya lo usa.
- Cons: look "dated" de Windows 95, difícil de hacer que se vea profesional.
- Effort: small | Confidence: high

**B. customtkinter wizard (Recomendado)**
- Pros: look moderno y "dark mode", API casi idéntica a tkinter, pesa ~1MB, MIT license, fácil de integrar con `overlay.py` existente.
- Cons: requiere instalar una dependencia extra; no es "nativo" del OS pero se ve bien.
- Effort: small-medium | Confidence: high

**C. PyQt6 / PySide6 wizard**
- Pros: framework profesional completo, nativo estilizado.
- Cons: pesado (~50MB+ extra), curva de aprendizaje, licencia LGPL implica consideraciones de distribución (dinámico vs estático), overkill para un wizard simple.
- Effort: medium | Confidence: medium

**D. flet wizard**
- Pros: look Flutter moderno, cross-platform mobile+desktop.
- Cons: engine Flutter agrega ~20-30MB, requiere segundo proceso/thread cuidadoso, no encaja bien con arquitectura tray+overlay existente.
- Effort: medium | Confidence: low

**E. Platform-native installers (Inno Setup / .pkg / .deb)**
- Pros: experiencia 100% nativa, sin Python visible al usuario.
- Cons: desacoplados del código Python; requieren mantener 3 pipelines separados; no pueden reusar la lógica de detección de hardware ya escrita en Python sin duplicarla.
- Effort: large | Confidence: medium

**Recomendación**: **B (customtkinter)** para el wizard de instalación escrito en Python, que reutiliza la lógica de `install.py` existente. Para Windows, envolver el output de PyInstaller con **Inno Setup** (ver área 2) para el " último mile" de instalación nativa.

---

#### 2. App Bundles / Packaging

**A. PyInstaller (onedir) — Recomendado**
- Pros: estándar de facto, muchos hooks para torch/numpy/PIL, soporta Windows/Linux/macOS, `--noconsole` para GUI.
- Cons: el binario final será masivo por torch (~2-3GB), onedir produce carpetas grandes pero startup más rápido que onefile.
- Effort: medium | Confidence: high

**B. PyInstaller (onefile)**
- Pros: un solo .exe para distribuir.
- Cons: startup lento (descompresión en temp), con torch el tamaño puede ser 3GB+, riesgo de timeout/descompresión.
- Effort: small | Confidence: low

**C. Nuitka**
- Pros: compila a C++, mejor rendimiento y algo de ofuscación.
- Cons: build extremadamente lento con torch, requiere toolchain C++, mucho más difícil de debuggear.
- Effort: large | Confidence: low

**D. cx_Freeze**
- Pros: alternativa madura.
- Cons: menos hooks comunitarios que PyInstaller para el ecosistema ML; más trabajo manual.
- Effort: medium | Confidence: medium

**Recomendación**: **PyInstaller en modo onedir** + un script `build.py` que automatice el build. Para Windows, generar un instalador con **Inno Setup** que copie la carpeta `_internal` + `.exe` a `Program Files`. Para Linux/macOS, distribuir como `.zip` portable o script de instalación.

---

#### 3. Branding / Icons

**A. Generar iconos programáticamente con PIL**
- Pros: zero assets binarios manuales, fácil de regenerar, versionable.
- Cons: diseño limitado a primitivas (rectángulos, elipses); difícil hacer algo visualmente atractivo.
- Effort: small | Confidence: high

**B. Crear assets SVG/PNG estáticos con herramienta externa (Figma/Inkscape)**
- Pros: diseño profesional posible.
- Cons: requiere trabajo de diseño manual, assets binarios en git.
- Effort: small | Confidence: high

**C. Iconos + Splash screen con customtkinter/tkinter**
- Pros: splash puede ser una ventana flotante con logo y progress bar indeterminada; fácil de implementar.
- Cons: no es un verdadero splash de Windows (aparece después de que el proceso arranca).
- Effort: small | Confidence: high

**Recomendación**: **Híbrido A+B**: diseñar un icono base simple (silueta de micrófono) como SVG, y usar un script `tools/generate_icons.py` con Pillow para generar `.ico` (16-256px), `.icns`, y PNGs de tray (64px) en estados: `idle`, `loading`, `recording`, `error`. El splash se implementa como **ventana customtkinter** que se muestra en `__main__.py` mientras el thread `loader` carga el modelo.

---

#### 4. Auto-updater

**A. GitHub Releases API simple — Recomendado**
- Pros: sin dependencias pesadas, opt-in, el usuario decide actualizar, fácil de auditar.
- Cons: requiere manejar permisos de reemplazo de archivos en ejecución (en Windows hay que renombrar/mover y dejar un updater helper o pedir reinicio).
- Effort: small | Confidence: high

**B. pyupdater**
- Cons: deprecado/abandonado, no usar.

**C. TUF / python-tuf**
- Cons: overkill de seguridad para un proyecto open-source individual, complejidad enorme.

**Recomendación**: **A**. Implementar `wispr/updater.py` que haga `GET https://api.github.com/repos/p5Patricio/WisprLocal/releases/latest`, compare `tag_name` con una constante `VERSION` local, y si hay update, pregunte al usuario (ventana customtkinter) y descargue el asset correspondiente. Dejar la actualización como "descargar el instalador y ejecutarlo al cerrar la app" para evitar problemas de archivos en uso.

---

#### 5. Settings GUI

**A. customtkinter settings window — Recomendado**
- Pros: consistente con el installer y splash, API familiar si ya se usa tkinter, lightweight.
- Cons: ventana adicional que debe convivir con el tray icon (tkinter puede tener problemas con múltiples instancias de `Tk` en threads distintos; `customtkinter.CTk` hereda de `tkinter.Tk`).
- Effort: medium | Confidence: high

**B. PyQt6 settings dialog**
- Pros: más widgets nativos (sliders, combos, etc.).
- Cons: agrega toda Qt solo por una ventana de settings, licencia LGPL, inconsistencia visual con overlay tkinter.
- Effort: medium | Confidence: medium

**C. flet settings page**
- Cons: requiere correr un app flutter separada; demasiado para un simple formulario.

**Recomendación**: **A (customtkinter)**. Implementar `wispr/settings_gui.py` con una ventana modal (o top-level) lanzada desde el menú del tray. Campos:
- Modelo: dropdown (tiny/base/small/medium/large-v3/auto)
- Dispositivo: dropdown (auto/CUDA/CPU/MPS)
- Hotkeys: botón "Capturar tecla" que use `pynput` para escuchar la próxima tecla
- Overlay: checkbox + dropdown posición + slider opacidad
- Guardar escribe `config.toml` y muestra mensaje "Reiniciar para aplicar".

**Nota técnica**: como `tray.py` bloquea el main thread con `icon.run()`, la ventana de settings debe crearse en otro thread (o usar `pystray`'s callback para lanzarla en el main thread si hay un event loop alternativo). La forma más simple: que `start_tray` corra en un thread daemon y el main thread corra un loop de tkinter/customtkinter, o viceversa. Dado que actualmente el tray BLOQUEA el main thread, hay que reestructurar ligeramente: correr `pystray` en un thread y el main thread quedar libre (como ya lo está haciendo con `state.shutdown_event.wait()` cuando falla el tray). Esto es un cambio de arquitectura menor.

---

#### 6. Marketing / README Polish

**A. Screenshots/GIFs estáticos — Recomendado**
- Pros: alta conversión, fácil de mantener.
- Cons: requiere capturar pantalla manualmente en cada release mayor.
- Effort: small | Confidence: high

**B. Feature comparison table vs competidores**
- Pros: posiciona claramente el valor (local, gratis, Spanglish).
- Cons: puede quedar desactualizado.
- Effort: small | Confidence: high

**C. Testimonials / Badges adicionales**
- Pros: confianza social.
- Cons: placeholder obvio si no hay usuarios reales aún.
- Effort: small | Confidence: medium

**Recomendación**: **A+B**. Crear carpeta `docs/screenshots/` con 3-4 imágenes: tray menú, overlay grabando, settings GUI (una vez implementada), y wizard de instalación. Agregar sección "¿Por qué WisprLocal?" con tabla comparativa contra Whisper Desktop, Otter.ai, etc. Badges de GitHub release y downloads.

---

#### 7. Onboarding Flow

**A. First-run wizard con customtkinter — Recomendado**
- Pros: guía al usuario paso a paso, detecta hardware visualmente, reduce support burden.
- Cons: agrega código que solo corre una vez.
- Effort: medium | Confidence: high

**B. Solo mensaje de log + README**
- Pros: zero código.
- Cons: muchos usuarios no leen logs ni README.

**Recomendación**: **A**. Extender `is_first_run` en `__main__.py` para lanzar un wizard multi-paso:
1. Bienvenida (texto + logo)
2. Hardware detectado (muestra GPU/RAM y sugiere modelo, como ya hace `detect_optimal_model`)
3. Test de micrófono (grabar 3s, mostrar waveform simple o solo volumen RMS, reproducir beep)
4. Test de hotkeys ("Presiona tu tecla PTT ahora" — captura con `pynput`)
5. Tutorial rápido ("Mantén F9 presionado mientras hablás...")

El wizard escribe un flag `first_run = false` en `config.toml` al finalizar.

---

### Recommendation (Visión Cohesiva Fase 3)

| Componente | Tecnología elegida | Justificación |
|------------|-------------------|---------------|
| **GUI Installer** | `customtkinter` wizard en Python | Reutiliza conocimiento tkinter del proyecto, look moderno, 1MB extra, MIT license |
| **Settings GUI** | `customtkinter` top-level window | Misma dependencia que el installer, consistente visualmente |
| **Onboarding** | `customtkinter` wizard reutilizable | Se integra con `is_first_run`, reusa widgets del installer |
| **Splash screen** | `customtkinter` / `tkinter` ventana | Se muestra mientras carga el modelo en el thread loader |
| **Icons / Assets** | Script `tools/generate_icons.py` con Pillow | Genera ICO/ICNS/PNG desde un diseño base simple; versionable |
| **Packaging** | PyInstaller (onedir) + Inno Setup (Win) | PyInstaller tiene los hooks para torch; onedir evita startup lento; Inno Setup da look profesional de instalador Windows |
| **Auto-updater** | GitHub Releases API + download manual | Opt-in, simple, sin dependencias externas |
| **README** | Screenshots + tabla comparativa + badges | Mejora conversión sin código |

**Estrategia de dependencias**: solo agregar **`customtkinter`** y opcionalmente **`requests`** (para updater) al runtime. PyInstaller como dev-dependency. Mantener la app liviana: el peso sigue dominado por torch/Whisper, no por la GUI.

**Arquitectura de threads**:
- Hoy: tray bloquea main thread. Para soportar settings GUI y splash sin deadlocks, mover `pystray` a un thread daemon y dejar el main thread disponible para crear ventanas `customtkinter` (o usar un event loop híbrido). Esto es el cambio estructural más significativo de Fase 3.

---

### Risks

| Riesgo | Severidad | Mitigación |
|--------|-----------|------------|
| **PyInstaller + torch produce build masivo y lento** | Medium | Usar onedir, excluir tests/docs de torch vía hooks, no usar onefile |
| **Múltiples instancias de Tk() en threads distintas** | Medium | Unificar en un solo thread de UI; customtkinter hereda de tkinter, mismas reglas |
| **Windows SmartScreen sin firma de código** | Medium | Considerar certificado barato (Sectigo/DigiCert ~$70/año) o instruir a usuarios en README |
| **Linux/macOS packaging menos maduro que Windows** | Low | Para Fase 3 enfocar en Windows como primary; dejar Linux/macOS como .zip portable |
| **Overlay tkinter + ventanas customtkinter pueden colisionar** | Low | Usar `Toplevel` en vez de segunda instancia de `Tk`; ambos usan el mismo mainloop si están en el mismo thread |
| **Auto-updater reemplaza binarios en ejecución** | Medium | Descargar el instalador nuevo y pedir reinicio; no reemplazar archivos en caliente |
| **Splash screen bloquea si el modelo tarda mucho** | Low | Usar `root.after()` para polling del estado del loader; no bloquear el mainloop |

---

### Ready for Proposal

**Yes**. El scope de Fase 3 está claro: branding visual, GUI installer/settings/onboarding, packaging profesional, y auto-updater opt-in. La tecnología recomendada (`customtkinter` + PyInstaller + Inno Setup) balancea profesionalismo con complejidad manejable y mantiene la app open-source y liviana.

**Next recommended phase**: `sdd-propose` para definir los cambios concretos, scope por milestone, y rollback plan.
