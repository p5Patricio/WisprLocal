import time
import numpy as np
from faster_whisper import WhisperModel
import torch

def benchmark_whisper():
    print("--- BENCHMARK DE TRANSCRIPCIÓN LOCAL ---")
    
    # Configuración para velocidad extrema en RTX 4060
    model_size = "distil-large-v3" # Versión ultra rápida y precisa
    
    print(f"Cargando modelo '{model_size}' en VRAM...")
    t0 = time.perf_counter()
    
    # Cargamos en INT8 para usar los Tensor Cores de tu serie 40
    model = WhisperModel(
        model_size, 
        device="cuda", 
        compute_type="int8_float16"
    )
    
    t_load = time.perf_counter() - t0
    print(f"✅ Modelo cargado en: {t_load:.2f}s")

    # Creamos 5 segundos de audio "vacío" (silencio) para la prueba
    audio_dummy = np.zeros(16000 * 5, dtype=np.float32)

    print("\nIniciando transcripción de prueba (5 segundos de audio)...")
    t1 = time.perf_counter()
    
    # Transcribir
    segments, _ = model.transcribe(audio_dummy, language="es", beam_size=1)
    list(segments) # Forzamos la ejecución
    
    t_infer = time.perf_counter() - t1
    print(f"🚀 Tiempo de inferencia: {t_infer*1000:.2f}ms")
    print(f"Relación de velocidad: {5 / t_infer:.1f}x veces más rápido que el tiempo real")

if __name__ == "__main__":
    benchmark_whisper()