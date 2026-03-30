import torch

print("--- REPORTE DE HARDWARE ---")
# 1. ¿Está CUDA vivo?
disponible = torch.cuda.is_available()
print(f"¿CUDA detectado?: {'✅ SÍ' if disponible else '❌ NO'}")

if disponible:
    # 2. Detalles de tu RTX 4060
    nombre = torch.cuda.get_device_name(0)
    propiedades = torch.cuda.get_device_properties(0)
    vram_gb = propiedades.total_memory / (1024**3)
    
    print(f"GPU: {nombre}")
    print(f"VRAM Total: {vram_gb:.2f} GB")
    print(f"Arquitectura (Compute Capability): {propiedades.major}.{propiedades.minor}")

    # 3. Prueba de fuego: mover un tensor a la GPU
    x = torch.rand(1000, 1000).to("cuda")
    y = torch.rand(1000, 1000).to("cuda")
    z = torch.matmul(x, y)
    
    print("\n--- RESULTADO DE LA PRUEBA ---")
    print("✅ Prueba de cálculo en GPU exitosa. ¡Todo listo!")
else:
    print("\n❌ ALERTA: PyTorch no está usando la GPU. Revisa los drivers.")