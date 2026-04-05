# 🎙️ Wispr Local: Asistente de Dictado Bilingüe (GPU-Powered)

Este proyecto es una herramienta de **Voice-to-Text (STT)** de ultra baja latencia diseñada para desarrolladores. Permite dictar código, notas técnicas y correos en un entorno bilingüe (**Español/Inglés**) sin depender de la nube, procesando todo localmente en la GPU para garantizar privacidad total y rendimiento máximo.

## ✨ Características Principales
- **Bilingüismo Real:** Gracias al modelo `large-v3`, detecta y transcribe "Spanglish" técnico sin errores de traducción.
- **Modo Gaming (Zero VRAM):** Incluye un "kill-switch" en la bandeja del sistema que libera el 100% de la memoria de video para jugar sin interferencias.
- **Doble Modo de Activación:**
  - **Push-to-Talk (PTT):** Usa `Bloq Mayús` para ráfagas rápidas de texto.
  - **Toggle Mode:** Usa `Alt + Shift` para dictado continuo (ideal para pensar en voz alta o caminar).
- **Feedback Auditivo:** Sonidos de sistema (Beeps) para confirmar estados sin necesidad de mirar la pantalla.
- **Icono en System Tray:** Monitoreo visual del estado (Gris = Inactivo, Verde = Escuchando).

## 💻 Requisitos de Hardware
- **GPU:** NVIDIA RTX (Optimizado para arquitectura **Ada Lovelace/RTX 4060**).
- **VRAM:** 8GB (Ocupa ~3GB en uso, 0GB en reposo).
- **RAM:** 16GB+ (Recomendado 32GB).
- **OS:** Windows 10/11.

---

## 🛠️ Guía de Instalación (Paso a Paso)

### 1. Instalación de Python 3.12
Es fundamental usar **Python 3.12** para garantizar la compatibilidad con los binarios de PyTorch y CUDA.
1. Descarga el instalador de [python.org](https://www.python.org/downloads/windows/).
2. **IMPORTANTE:** Durante la instalación, **NO** marques la casilla "Add Python to PATH" si ya tienes otra versión instalada. Al finalizar, selecciona "Disable path length limit".

### 2. Preparación del Entorno (PowerShell)
Abre PowerShell en la carpeta del proyecto y ejecuta los siguientes comandos:

```powershell
# A. Habilitar la ejecución de scripts en Windows (Solo la primera vez)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# B. Crear el entorno virtual con la versión específica
# (Ajusta la ruta si instalaste Python en otro lugar)
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv

# C. Activar el entorno
.\.venv\Scripts\Activate.ps1
```

### 3. Instalación de Dependencias
Con el entorno activo `(.venv)`, instala PyTorch con soporte CUDA y las librerías de IA:

```powershell
# Instalar PyTorch para CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Instalar librerías del ecosistema
pip install faster-whisper sounddevice pynput pyperclip pystray Pillow
```

---

## 🚀 Configuración del Inicio Automático

Para que el asistente se cargue de forma invisible al prender la laptop:

1. **Crear el Lanzador (`lanzador.vbs`):**
   Crea este archivo en la raíz de tu proyecto. **Ajusta las rutas** con tu nombre de usuario real:
   ```vbs
   Set WshShell = CreateObject("WScript.Shell")
   ' Ejemplo de ruta: C:\Users\patri\Documents\WisprLocal\...
   WshShell.Run "C:\RUTA\A\TU\PROYECTO\.venv\Scripts\pythonw.exe C:\RUTA\A\TU\PROYECTO\mvp_local.py", 0
   Set WshShell = Nothing
   ```
2. **Crear Acceso Directo:**
   - Haz clic derecho en `lanzador.vbs` -> *Mostrar más opciones* -> *Crear acceso directo*.
3. **Carpeta de Inicio:**
   - Presiona `Win + R`, escribe `shell:startup` y presiona Enter.
   - Mueve el acceso directo recién creado a esa carpeta.

---

## 🎮 Flujo de Trabajo y Uso

| Estado del Icono | Significado | Acción |
| :--- | :--- | :--- |
| **⚪ Gris** | Modo Gaming / Reposo | VRAM liberada. Haz clic derecho -> **Activar Modelo** para usarlo. |
| **🟢 Verde** | Modelo Cargado | Listo para transcribir en cualquier aplicación. |

### Comandos de Teclado
- **Dictado Rápido:** Mantén `Bloq Mayús` presionado, habla y suelta.
- **Dictado Continuo:** Presiona `Alt + Shift` para iniciar (sonido agudo). Presiona de nuevo para procesar e inyectar (sonido grave).

---

## ⚠️ Solución de Problemas (Troubleshooting)

- **Error `UnauthorizedAccess`:** Si no puedes activar el entorno virtual, recuerda ejecutar `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`.
- **No detecta la GPU:** Asegúrate de tener los drivers de NVIDIA actualizados y haber instalado la versión de `torch` con el index-url de CUDA especificado arriba.
- **Conflicto de teclas:** Si `Alt + Shift` choca con otra app, puedes cambiar la variable `active_modifiers` en el código fuente.

---

## 🧠 Notas Técnicas
- **Modelo:** `large-v3` (Faster-Whisper).
- **Cuantización:** `int8_float16` para optimizar el uso de Tensor Cores.
- **Inyección:** El sistema utiliza una combinación de `pyperclip` y simulación de teclado `Ctrl + V` para asegurar compatibilidad total con caracteres especiales y acentos en español.
