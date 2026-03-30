import pyperclip
import time
import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
from pynput import keyboard
import queue
import torch
import sys
import threading
import winsound
import gc
from PIL import Image, ImageDraw
import pystray

# --- CONFIGURACIÓN DE HARDWARE ---
SAMPLE_RATE = 16000
MODEL_SIZE = "large-v3"
DEVICE = "cuda"
COMPUTE_TYPE = "int8_float16"

# --- ESTADOS GLOBALES ---
audio_queue = queue.Queue()
ptt_active = False
toggle_active = False
active_modifiers = set()
model = None  # Iniciamos en None para ahorrar VRAM
is_loading = False

# --- FEEDBACK AUDITIVO ---
def play_sound(action):
    if action == "start": winsound.Beep(1000, 100) # Agudo
    if action == "stop": winsound.Beep(600, 100)   # Grave
    if action == "ready": winsound.Beep(1500, 200) # Éxito

# --- GESTIÓN DE VRAM (CARGAR/DESCARGAR) ---
def load_model():
    global model, is_loading
    if model is None and not is_loading:
        is_loading = True
        print(f"🚀 Cargando {MODEL_SIZE} en la RTX 4060...")
        try:
            model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
            play_sound("ready")
            print("✅ Modelo cargado y listo.")
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            is_loading = False
            update_icon()

def unload_model():
    global model
    if model is not None:
        print("🔌 Liberando VRAM para modo Gaming...")
        del model
        model = None
        # Limpieza profunda de CUDA
        gc.collect()
        torch.cuda.empty_cache()
        torch.cuda.synchronize() 
        print("✅ VRAM liberada al 100%.")
        update_icon()

# --- LÓGICA DE TRANSCRIPCIÓN ---
def transcribe_audio(audio_data):
    if model is None:
        print("⚠️ Modelo no cargado. Actívalo desde el icono.")
        return None
        
    audio_np = np.concatenate(audio_data, axis=0).flatten()
    if np.max(np.abs(audio_np)) > 0:
        audio_np = audio_np / np.max(np.abs(audio_np))
    
    prompt_bilingue = "Nota técnica. Testing code, PRs, backend logs. Spanglish mode."
    segments, info = model.transcribe(audio_np, language=None, task="transcribe", beam_size=1, initial_prompt=prompt_bilingue)
    return "".join([segment.text for segment in segments]).strip()

def finalizar_y_inyectar():
    if model is None: return
    play_sound("stop")
    audio_chunks = []
    while not audio_queue.empty(): audio_chunks.append(audio_queue.get())
    
    if audio_chunks:
        texto = transcribe_audio(audio_chunks)
        if texto:
            pyperclip.copy(texto)
            controlador = keyboard.Controller()
            time.sleep(0.1)
            with controlador.pressed(keyboard.Key.ctrl):
                controlador.press('v')
                controlador.release('v')
            print(f"✨: {texto}")

# --- MANEJO DE TECLADO ---
def on_press(key):
    global ptt_active, toggle_active
    if model is None: return # No hacer nada si el modelo no está cargado

    if key == keyboard.Key.caps_lock:
        if not ptt_active:
            ptt_active = True
            play_sound("start")
            
    if key in [keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r]: active_modifiers.add('alt')
    if key in [keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r]: active_modifiers.add('shift')

    if 'alt' in active_modifiers and 'shift' in active_modifiers:
        if not hasattr(on_press, 'toggle_lock'):
            on_press.toggle_lock = True
            toggle_active = not toggle_active
            if toggle_active: 
                play_sound("start")
                print("🟢 Toggle ON")
            else: 
                finalizar_y_inyectar()

def on_release(key):
    global ptt_active
    if key == keyboard.Key.caps_lock and ptt_active:
        ptt_active = False
        finalizar_y_inyectar()
    if key in [keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r]:
        active_modifiers.discard('alt')
        if hasattr(on_press, 'toggle_lock'): del on_press.toggle_lock
    if key in [keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r]:
        active_modifiers.discard('shift')

# --- ICONO DE BANDEJA (SYSTEM TRAY) ---
def create_image(color):
    image = Image.new('RGB', (64, 64), color)
    d = ImageDraw.Draw(image)
    d.rectangle([16, 16, 48, 48], fill='white')
    return image

def update_icon():
    if icon is None: return
    if model is not None:
        icon.icon = create_image('green')
        icon.title = "Wispr Local - Listo"
    else:
        icon.icon = create_image('gray')
        icon.title = "Wispr Local - Gaming Mode (VRAM Libre)"

def on_quit(icon, item):
    unload_model()
    icon.stop()
    sys.exit()

icon = pystray.Icon("Wispr", create_image('gray'), "Wispr Local")
icon.menu = pystray.Menu(
    pystray.MenuItem("Activar Modelo (Cargar VRAM)", lambda: threading.Thread(target=load_model).start()),
    pystray.MenuItem("Modo Gaming (Liberar VRAM)", unload_model),
    pystray.MenuItem("Salir", on_quit)
)

# --- ARRANQUE ---
def run_tray():
    icon.run()

if __name__ == "__main__":
    # Iniciar captura de audio
    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, callback=lambda i, f, t, s: audio_queue.put(i.copy()) if ptt_active or toggle_active else None)
    stream.start()
    
    # Iniciar teclado
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    
    print("🎬 Programa iniciado en segundo plano.")
    run_tray()