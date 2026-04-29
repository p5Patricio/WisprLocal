# Diseño: WisprLocal Fase 3 — GUI, Branding y Auto-Updater

## 1. Arquitectura de Threads

Main Thread (customtkinter event loop)
  ├── SplashScreen (Toplevel)  → se destruye al cargar modelo
  ├── OnboardingWizard (Toplevel) → solo first-run
  ├── SettingsGUI (Toplevel) → vía tray
  └── Installer (Tk raíz) → proceso separado, no runtime

Daemon Thread: pystray.Icon
  ├── Menú: Configuración | Cargar | Descargar | Salir
  └── Usa iconos reales desde assets/icons/

Background Threads (daemon=True)
  ├── transcription_worker
  ├── load_model → notifica a SplashScreen vía queue/after
  └── audio_stream

Regla de oro: un solo Tk() en main thread. Todo diálogo es Toplevel.

## 2. Gestión de Ventanas (customtkinter)

| Ventana | Clase | Padre | Cuándo aparece |
|---------|-------|-------|----------------|
| Installer | CTk propio | — | Ejecutado por usuario, no por la app |
| Splash | SplashScreen(CTkToplevel) | root | Durante load_model() |
| Onboarding | OnboardingWizard(CTkToplevel) | root | Si is_first_run |
| Settings | SettingsGUI(CTkToplevel) | root | Desde tray → Configuración |

Protocolo WM_DELETE_WINDOW en Toplevels: si es settings/onboarding → destroy(); si es root → trigger shutdown.

## 3. Cambios de Archivos

| Archivo | Cambio | Detalle |
|---------|--------|---------|
| wispr/tray.py | Modificar | Menú agrega Configuración; usa iconos reales; start_tray ya no bloquea main thread (corre en daemon) |
| wispr/config.py | Modificar | Agregar write_config(path, dict); preservar DEFAULT_TOML_CONTENT como template |
| wispr/__main__.py | Modificar | Main thread lanza customtkinter.CTk(); inicia pystray en Thread(daemon=True); detecta first-run para onboarding |
| wispr/overlay.py | Modificar | Alinear estilos con customtkinter si usa fuentes/colores; sin cambio funcional mayor |
| requirements.txt | Modificar | Agregar customtkinter>=5.2.0, requests>=2.31.0 |
| wispr/splash.py | Nuevo | SplashScreen(CTkToplevel) con label de progreso; expone set_status(text) y close() |
| wispr/settings_gui.py | Nuevo | SettingsGUI(CTkToplevel): tabs Modelo/Audio/Hotkeys/Overlay; lee/escribe config.toml vía config.write_config() |
| wispr/onboarding.py | Nuevo | OnboardingWizard(CTkToplevel): welcome → mic test (usa audio.start_stream preview) → hotkey capture (bloquea input y lee tecla) → tutorial |
| wispr/updater.py | Nuevo | check_update() → GitHub API; download_installer(url) → guarda en temp; notifica vía CTkToplevel |
| installer/gui_installer.py | Nuevo | Wizard standalone: detect hardware → select model → download/copy files → crear config.toml |
| tools/generate_icons.py | Nuevo | Script PIL: carga SVG/PNG base; exporta .ico (multi-res), .icns, tray_16/32/64.png |
| tools/build.py | Nuevo | Script PyInstaller: onedir, --windowed, incluye assets/icons/, config.toml, hooks para torch exclusiones |
| assets/icons/ | Nuevo dir | Contiene base, .ico, .icns, PNGs tray |
| installer/ | Nuevo dir | Contiene gui_installer.py y recursos del wizard |
| README.md | Modificar | Screenshots, badges, tabla comparativa WisprLocal vs alternativas |

## 4. API de Configuración

    def write_config(path: str, config: dict) -> None:
        """Escribe config.toml preservando comentarios de plantilla."""
        ...

    def is_first_run(path: str = ""config.toml"") -> bool:
        """True si el archivo no existe."""
        ...

Implementación: renderizar DEFAULT_TOML_CONTENT como template (p.ej. con string.Template) y reemplazar valores conocidos. Alternativa: usar tomli_w para secciones gestionadas y dejar comentarios como string header.

## 5. Pipeline de Build

1. python tools/generate_icons.py   → assets/icons/
2. python tools/build.py            → dist/WisprLocal/
3. (Opcional) Inno Setup            → WisprLocal-Setup.exe

PyInstaller spec considerations:
- --onedir para evitar startup lento de onefile con torch.
- --exclude-module tests, docs, notebooks.
- Hook para torch que evite empaquetar backends no usados (CPU-only si no hay CUDA en target).

## 6. Decisiones de Diseño

| Decisión | Rationale |
|----------|-----------|
| Installer como script standalone | No requiere que la app principal tenga customtkinter en PATH previo a la instalación |
| pystray en daemon thread | Libera main thread para customtkinter; evita conflicto de event loops |
| Un solo Tk() | customtkinter no tolera múltiples instancias en distintos threads |
| Todos los GUIs heredan CTkToplevel | Consistencia visual y fácil destrucción desde root |
| Updater descarga installer (no patch) | Evita reemplazar binarios en ejecución; reduce complejidad |
| Iconos desde SVG base | Single source of truth para branding |