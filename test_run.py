"""Test rápido de import y carga de modelo."""

import sys
sys.path.insert(0, ".")

# Test 1: Imports principales
print("=== Test de imports ===")
from wispr.state import AppState
from wispr import config as config_module
from wispr.audio import start_stream, stop_stream
from wispr.transcription import load_model, unload_model, transcription_worker
from wispr.injection import inject_text
print("OK: Todos los imports funcionan")

# Test 2: Estado
print("\n=== Test de AppState ===")
state = AppState()
print(f"  loading: {state.get_loading()}")
print(f"  recording: {state.is_recording()}")
print(f"  model: {state.model}")
print("OK: AppState funciona")

# Test 3: Config
print("\n=== Test de Config ===")
cfg = config_module.load_config("config.toml")
print(f"  modelo: {cfg['model']['name']}")
print(f"  device: {cfg['model']['device']}")
print(f"  ptt: {cfg['hotkeys']['ptt']}")
print(f"  first_run: {cfg['app']['first_run']}")
print("OK: Config funciona")

# Test 4: Carga del modelo
print("\n=== Test de carga de modelo ===")
from faster_whisper import WhisperModel
import torch
print(f"  CUDA disponible: {torch.cuda.is_available()}")
print(f"  GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A'}")
print("  Cargando large-v3 en cuda...")
model = WhisperModel("large-v3", device="cuda", compute_type="int8_float16")
print("OK: Modelo large-v3 cargado en CUDA")

print("\n=== TODOS LOS TESTS PASARON ===")
