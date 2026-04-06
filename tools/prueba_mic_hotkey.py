import sounddevice as sd
import numpy as np
from pynput import keyboard
import queue

# Configuración básica
SAMPLE_RATE = 16000
audio_queue = queue.Queue()
hotkey_pressed = False

def audio_callback(indata, frames, time, status):
    """Esta función se ejecuta cada vez que el mic recibe audio"""
    if hotkey_pressed:
        # Solo metemos audio a la cola si estamos presionando la tecla
        audio_queue.put(indata.copy())

def on_press(key):
    global hotkey_pressed
    try:
        # Detectar Alt + S
        if key.char == 's' and any(k in [keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r] for k in current_keys):
            if not hotkey_pressed:
                hotkey_pressed = True
                print("\n🎙️ [GRABANDO] Suelta 'S' para detener...")
    except AttributeError:
        pass

def on_release(key):
    global hotkey_pressed
    try:
        if key.char == 's':
            if hotkey_pressed:
                hotkey_pressed = False
                print("🛑 [DETENIDO] Audio capturado.")
                # Aquí es donde en el futuro llamaremos a Whisper
                print(f"Tamaño del buffer capturado: {audio_queue.qsize()} chunks")
                while not audio_queue.empty(): audio_queue.get() # Limpiar cola
    except AttributeError:
        pass

# Rastrear teclas presionadas para combinaciones
current_keys = set()

def signal_press(key):
    current_keys.add(key)
    on_press(key)

def signal_release(key):
    if key in current_keys:
        current_keys.remove(key)
    on_release(key)

print("--- PRUEBA DE CAPTURA (Alt + S) ---")
print("Mantén presionado Alt y luego presiona S para empezar a grabar.")
print("Presiona Ctrl+C para cerrar este test.")

# Iniciar el flujo del micrófono en segundo plano
with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, callback=audio_callback):
    with keyboard.Listener(on_press=signal_press, on_release=signal_release) as listener:
        listener.join()