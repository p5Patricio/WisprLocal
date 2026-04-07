# WisprLocal

Dictado por voz local, sin nube, bilingüe español/inglés. Transcribe con Whisper en tu GPU y pega el texto donde estés escribiendo.

![Python](https://img.shields.io/badge/python-3.12+-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

---

## ¿Qué es WisprLocal?

- **Local y privado** — todo corre en tu máquina, ningún audio sale a internet
- **Bilingüe real** — el modelo `large-v3` maneja Spanglish técnico sin problemas
- **Gaming-friendly** — el modelo se puede descargar desde la bandeja liberando VRAM al instante
- **Se pega donde escribís** — inyecta el texto en cualquier app vía clipboard, sin plugins

---

## Instalación en 3 pasos

**Requisitos**: Python 3.12+, Windows 10/11, GPU NVIDIA (opcional pero recomendado)

```powershell
# 1. Clonar el repo
git clone https://github.com/tu-usuario/WisprLocal.git
cd WisprLocal

# 2. Correr el instalador
python install.py

# 3. Abrir WisprLocal
# Doble clic en lanzador.vbs  (sin ventana de consola)
# — o desde terminal:
.venv\Scripts\python.exe -m wispr
```

El instalador detecta tu GPU automáticamente e instala PyTorch con CUDA si corresponde. También pregunta si querés que WisprLocal inicie con Windows.

---

## Configuración

Editá `config.toml` en la raíz del proyecto. Los cambios se aplican al reiniciar.

```toml
[model]
name = "large-v3"          # tiny / base / small / medium / large-v2 / large-v3
device = "cuda"            # cuda | cpu
compute_type = "int8_float16"  # float16 | int8_float16 | int8

[hotkeys]
ptt    = "f9"    # mantener presionada para grabar
toggle = "f10"   # presionar para iniciar, volver a presionar para detener

[transcription]
language = ""    # "" = detección automática (recomendado para Spanglish)
min_duration = 0.3  # segundos mínimos de audio para transcribir

[overlay]
enabled  = true
position = "bottom-right"  # bottom-right | bottom-left | top-right | top-left
```

---

## Teclas por defecto

| Acción | Tecla | Comportamiento |
|--------|-------|---------------|
| Push-to-Talk | `F9` | Mantener presionada mientras hablás, soltar para transcribir |
| Toggle | `F10` | Presionar para iniciar, presionar de nuevo para transcribir |

Ambas teclas son configurables desde `config.toml`. El texto transcripto queda también en el clipboard para pegarlo manualmente si querés.

---

## Troubleshooting

**El modelo no carga / error de CUDA**
Verificá que tenés drivers NVIDIA actualizados (`nvidia-smi` en terminal). Si el problema persiste, cambiá `device = "cpu"` en config.toml.

**No graba cuando presiono la tecla**
El modelo tarda ~10 segundos en cargar al arrancar. Esperá el beep doble (señal de "listo") antes de grabar. Si el ícono en tray es gris, usá clic derecho → "Cargar modelo".

**El texto no se pega en la aplicación**
Algunas apps con foco en ventanas elevadas (admin) bloquean la simulación de teclado. Probá en Notepad primero para confirmar que la transcripción funciona. Si funciona ahí pero no en tu app, el problema es de permisos de la app destino.

**El overlay no aparece**
Verificá que `overlay.enabled = true` en config.toml. El overlay no funciona sobre juegos en pantalla completa exclusiva (fullscreen exclusivo de DirectX).

**Tecla inválida en config.toml**
La app muestra el error al arrancar con las opciones válidas. Teclas soportadas: `caps_lock`, `f1`–`f12`, `scroll_lock`, `pause`, `insert`, `home`, `end`, letras sueltas (`a`–`z`).

---

## Arquitectura

```
wispr/
├── __main__.py      # composition root — orden de init y threading
├── state.py         # AppState compartido entre threads
├── config.py        # carga y validación de config.toml
├── audio.py         # stream de micrófono (PortAudio via sounddevice)
├── hotkeys.py       # listener de teclado (pynput)
├── transcription.py # modelo Whisper y worker de transcripción
├── injection.py     # clipboard + Ctrl+V para inyectar texto
├── overlay.py       # indicador visual (tkinter, siempre encima)
├── tray.py          # ícono en system tray (pystray)
└── sounds.py        # feedback auditivo (winsound)
```

**Modelo de threads**

| Thread | Qué hace |
|--------|----------|
| Main | Corre el system tray (bloquea hasta "Salir") |
| pynput | Escucha teclado, actualiza `AppState` |
| PortAudio | Captura audio, encola chunks en `audio_queue` |
| transcription_worker | Espera sentinel `None`, transcribe, inyecta |
| overlay | Corre `tk.mainloop()`, recibe updates via `root.after()` |
| loader | Carga el modelo al arrancar (daemon) |

Todos los threads se comunican a través de `AppState` y `audio_queue` — sin locks adicionales salvo para la referencia al modelo.

---

## Contribuir

Este proyecto usa [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: descripción de la nueva funcionalidad
fix: descripción del bug corregido
refactor: cambio de código sin nuevo comportamiento
chore: limpieza, dependencias, config
```

Estructura del proyecto:

```
WisprLocal/
├── wispr/           # paquete principal
├── tools/           # scripts de diagnóstico (verificar_gpu.py, etc.)
├── install.py       # instalador automatizado
├── requirements.txt # dependencias (sin torch — install.py lo maneja)
└── config.toml      # configuración local (no commitear)
```

`config.toml` está en `.gitignore` — `install.py` lo genera con defaults si no existe.
