[ARCHIVED — WisprLocal Fase 1] Este documento forma parte del histórico archivado. No modificar.

# Proposal: WisprLocal Fase 1 — Reliability & Thread Safety

## Intent
Eliminate critical threading bugs, unbounded memory growth, and silent failures. Add foundational reliability features (VAD, clipboard restore, auto-model selection) while keeping the existing tkinter architecture.

## Scope

### In Scope
- **P0 (Critical)**: Thread-safe `AppState` with locks; graceful shutdown with `join()`; bounded audio queue (`maxsize`)
- **P1 (High)**: Preserve/restore clipboard around injection; VAD in transcription; hardware-based auto-model
- **P2 (Medium)**: Polish tkinter overlay visuals; structured error handling with user-visible messages

### Out of Scope
- Cross-platform support, GUI installer, auto-updater (Fase 2/3)
- Model hot-swapping, web UI, cloud transcription
- Replacing tkinter with another framework

## Capabilities

### New
- `graceful-shutdown`: Clean thread lifecycle with `join()` and state transitions
- `audio-backpressure`: Bounded `queue.Queue(maxsize)` to prevent memory exhaustion
- `clipboard-restore`: Preserve pre-injection clipboard, restore after `Ctrl+V`
- `vad-filtering`: Voice Activity Detection to suppress non-speech transcription
- `hardware-auto-model`: Recommend model size based on GPU VRAM / CPU RAM
- `overlay-polish`: Visual status feedback in tkinter overlay
- `structured-errors`: Surface exceptions to user instead of silent swallowing

### Modified
- `app-state`: Boolean flags become lock-protected; shutdown sequence added
- `audio-stream`: Queue constructor gains `maxsize`
- `transcription`: Pipeline gated by VAD segment validation
- `injection`: Surrounds paste with clipboard save/restore

## Approach
1. Introduce `threading.Lock` in `AppState` for all mutable flags.
2. Replace daemon-only exits with explicit shutdown flags and `join()` in `__main__.py`.
3. Add `maxsize` to audio queue; producer blocks on full.
4. Wrap `pyperclip` calls with save/restore in `injection.py`.
5. Integrate `silero-vad` or `webrtcvad` in `transcription.py` before Whisper decode.
6. Query `torch.cuda` / `psutil` at startup to map hardware to model size.
7. Improve overlay colors/positioning; add `try/except` blocks with overlay error toasts.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `wispr/state.py` | Modified | Add locks, atomic getters/setters |
| `wispr/audio.py` | Modified | `queue.Queue(maxsize=...)`, backpressure |
| `wispr/transcription.py` | Modified | VAD pre-filter, hardware-based model load |
| `wispr/injection.py` | Modified | Save/restore clipboard content |
| `wispr/overlay.py` | Modified | Visual polish, error display |
| `wispr/__main__.py` | Modified | Graceful shutdown sequence |
| `wispr/config.py` | Modified | Auto-model override logic |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| VAD adds latency or drops valid speech | Med | Make VAD configurable; tune threshold |
| Clipboard restore fails on large content | Low | Add size check; fallback to clear |
| Lock contention degrades responsiveness | Low | Use short critical sections only |
| Hardware detection misidentifies GPU | Med | Allow manual override in `config.toml` |

## Rollback Plan
Revert to previous `main` branch commit. All changes are additive or localized; no schema or dependency changes break backward compatibility.

## Dependencies
- `torch` and `psutil` already present for hardware detection
- VAD library (e.g., `silero-vad`) to be added to `requirements.txt`

## Success Criteria
- [ ] P0: All threads exit cleanly on shutdown; no daemon kill warnings
- [ ] P0: `AppState` flags never raise `RuntimeError` under concurrent access
- [ ] P0: Audio queue never exceeds 100 items under sustained load
- [ ] P1: Clipboard content identical before and after dictation
- [ ] P1: Transcription ignores silent/audio-only segments (>50% reduction in false positives)
- [ ] P1: Startup auto-selects `tiny`/`base`/`small` based on available VRAM
- [ ] P2: Overlay shows recording/listening/error states visually
- [ ] P2: Exceptions surface in overlay instead of console-only
