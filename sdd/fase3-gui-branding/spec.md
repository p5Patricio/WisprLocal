# Especificación: WisprLocal Fase 3 — GUI, Branding y Auto-Updater

## Alcance
Delta de comportamiento para convertir WisprLocal en app de escritorio profesional: wizard de instalación, settings GUI, onboarding, splash screen, branding, auto-updater y build PyInstaller.

---

## ADDED Requirements

### REQ-01: gui-installer
El wizard de instalación MUST ejecutarse vía installer/gui_installer.py y MUST detectar hardware antes de permitir continuar.

- **Scenario:** Instalación limpia
  - GIVEN que no existe config.toml
  - WHEN el usuario ejecuta installer/gui_installer.py
  - THEN se muestra welcome → hardware detect → model select → install progress → done
  - AND al finalizar se crea config.toml con los valores elegidos

- **Scenario:** Cancelación
  - GIVEN que el wizard está abierto
  - WHEN el usuario presiona Cancelar
  - THEN el proceso termina sin modificar el sistema

### REQ-02: settings-gui
La ventana de configuración MUST leer y escribir config.toml sin corromper comentarios ni secciones no gestionadas.

- **Scenario:** Cambio persistente
  - GIVEN config.toml existente con model.name = "base"
  - WHEN el usuario cambia a "small" en settings-gui y guarda
  - THEN config.toml refleja "small" y el resto de secciones permanecen intactas

### REQ-03: onboarding-wizard
El onboarding MUST ejecutarse solo cuando is_first_run == True y MUST capturar hotkeys vía input directo.

- **Scenario:** Primer run exitoso
  - GIVEN que config.toml no existe
  - WHEN arranca wispr/__main__.py
  - THEN se muestra onboarding antes de cargar el modelo
  - AND el mic test reproduce el nivel de entrada en tiempo real

### REQ-04: splash-screen
La splash screen MUST aparecer durante load_model() y MUST cerrarse automáticamente al completarse.

- **Scenario:** Carga con splash
  - GIVEN que el modelo no está cargado
  - WHEN inicia la carga del modelo
  - THEN se muestra wispr/splash.py con mensaje de progreso
  - AND al terminar la carga la ventana se destruye sola

### REQ-05: icon-generation
El script 	ools/generate_icons.py MUST producir .ico, .icns y PNGs de tray desde un asset base.

- **Scenario:** Generación completa
  - GIVEN ssets/icons/base_icon.svg
  - WHEN se ejecuta generate_icons.py
  - THEN se crean ssets/icons/app.ico, pp.icns y 	ray_*.png

### REQ-06: auto-updater
El auto-updater SHOULD consultar GitHub Releases API al inicio; si hay versión nueva, MUST descargar el installer y pedir reinicio.

- **Scenario:** Update disponible
  - GIVEN que la versión local es 1.0.0 y la última release es 1.1.0
  - WHEN arranca la app
  - THEN se muestra notificación opt-in para descargar
  - AND al aceptar se descarga el installer y se solicita reinicio

- **Scenario:** Sin conexión
  - GIVEN que no hay acceso a internet
  - WHEN se ejecuta el check
  - THEN la app continúa sin bloqueos ni errores visibles

### REQ-07: pyinstaller-build
El script 	ools/build.py MUST producir un directorio dist/WisprLocal/ con onedir y un .exe ejecutable.

- **Scenario:** Build exitoso
  - GIVEN entorno .venv activado
  - WHEN se ejecuta python tools/build.py
  - THEN se genera dist/WisprLocal/WisprLocal.exe
  - AND se incluyen ssets/icons/ y config.toml de ejemplo

---

## MODIFIED Requirements

### REQ-M01: tray-icon
El menú del tray MUST incluir "Configuración" que abra settings-gui como Toplevel.
(Previously: solo tenía Cargar/Descargar/Salir)

- **Scenario:** Abrir settings desde tray
  - GIVEN tray corriendo
  - WHEN el usuario clickea "Configuración"
  - THEN se abre settings-gui sin crear un segundo Tk()

### REQ-M02: config-management
wispr/config.py MUST exponer write_config(path, dict) para escritura controlada.
(Previously: solo lectura con load_config())

- **Scenario:** Escritura segura
  - GIVEN un dict validado
  - WHEN se llama write_config("config.toml", cfg)
  - THEN se persiste TOML con comentarios por defecto preservados

### REQ-M03: entry-point
wispr/__main__.py MUST lanzar onboarding si is_first_run y MUST iniciar pystray en daemon thread.
(Previously: tray bloqueaba main thread)

- **Scenario:** Arranque con splash + onboarding
  - GIVEN primer run
  - WHEN se ejecuta __main__.py
  - THEN main thread corre customtkinter; pystray corre en daemon
  - AND el modelo se carga en background thread

---

## REMOVED Requirements

Ninguno. install.py queda deprecado pero no se elimina en esta fase.
