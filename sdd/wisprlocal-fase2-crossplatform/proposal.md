# Proposal: WisprLocal Fase 2 — Cross-Platform

## Intent

Portar WisprLocal a Linux/macOS preservando 100 % funcionalidad Windows mediante capa de abstracción `wispr/platform/`.

## Scope

### In Scope
- `wispr/platform/` — factory OOP (Windows/Linux/macOS).
- `sounds.py` — reemplazar `winsound`.
- `injection.py` — `Ctrl+V` (Win/Linux), `Cmd+V` (macOS).
- `config.py` — detectar MPS, ROCm, CUDA.
- `install.py` — `.vbs` (Win), `systemd` (Linux), `launchd` (macOS).
- Tray/hotkeys — graceful degradation headless.

### Out of Scope
- Wayland global hotkeys (known limitation).
- macOS `.app` bundle / GUI installer visual (Fase 3).
- Backend `evdev` experimental Wayland.

## Capabilities

### New
- `platform-abstraction`: factory OS-specific.
- `cross-platform-install`: scripts/servicios por OS.
- `multi-gpu-detection`: CUDA/MPS/ROCm + CPU fallback.
- `cross-platform-audio`: beep sin `winsound`.

### Modified
- None a nivel spec.

## Approach

**Factory OOP** (`BasePlatform` ABC + 3 implementaciones). Expone `play_beep()`, `get_paste_shortcut()`, `detect_gpu()`, `setup_autostart()`.

**Justificación vs `if/elif`:** Con 11 módulos, dispersar lógica OS por todo el código genera deuda técnica. La factory centraliza hacks, facilita tests y nuevas plataformas. Costo bajo (~5 archivos), beneficio mantenibilidad alto.

## Affected Areas

| Área | Impacto |
|------|---------|
| `wispr/platform/` | Nuevo |
| `wispr/sounds.py` | Usa `platform.play_beep()` |
| `wispr/injection.py` | Usa `platform.get_paste_shortcut()` |
| `wispr/config.py` | Usa `platform.detect_gpu()` |
| `install.py` | Delega a `_setup_<platform>()` |
| `requirements.txt` | Deps condicionales |
| `README.md` | Troubleshooting por OS |

## Work Packages

| Prioridad | Entregable |
|-----------|------------|
| **P0** Critical | `wispr/platform/`, sonidos, inyección cross-platform. |
| **P1** High | GPU MPS/ROCm/CUDA; `install.py` multiplataforma. |
| **P2** Medium | `wisprlocal.service`, `com.wisprlocal.plist`, autostart. |
| **P3** Docs | README: matriz compatibilidad, permisos macOS, deps Linux. |

## Risks

| Riesgo | P | Mitigación |
|--------|---|------------|
| Wayland sin hotkeys | A | Documentar; sugerir X11. |
| MPS inestable | M | `float16` en macOS; test real. |
| tkinter roto macOS | M | Recomendar Python oficial. |
| ROCm complejo AMD | M | Fallback CPU; docs índices PyTorch. |
| Permisos Accessibility macOS | A | Instrucciones paso a paso; mensaje primer arranque. |
| pystray headless | B | Try/except; modo sin tray. |

## Rollback Plan

- Git tag `pre-fase2`. Revertir si falla.
- `install.py` respaldado como `install_windows.py` durante transición.
- Nuevas deps opt-in por OS; no afectan Windows.

## Dependencies

- `simpleaudio` o `pyobjc` (macOS).
- Linux: `xclip`/`xsel`, `wl-clipboard`, `libappindicator3-1`.

## Success Criteria

- [ ] **Windows:** Paridad Fase 1.
- [ ] **Linux (X11):** Beep, hotkeys, inyección, tray, GPU OK.
- [ ] **Linux (Wayland):** Arranca, transcribe, inyecta; hotkeys documentados como no soportados.
- [ ] **macOS:** Beep, hotkeys (post-Accessibility), `Cmd+V`, MPS/CPU, tray OK.
- [ ] **Install:** Genera launcher/servicio correcto en cada OS.
