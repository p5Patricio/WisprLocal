"""Model provisioning and the transcription worker (resident whisper-server)."""

from __future__ import annotations

import logging
import os
import pathlib
import re
import sys
import tempfile
import threading
import wave
import zipfile
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import numpy as np
import requests

from tqdm import tqdm

logger = logging.getLogger(__name__)

from whisperkey.engine import WhisperServer, resolve_server_exe
from whisperkey.errors import ModelLoadError
from whisperkey.history import add_entry, trim
from whisperkey.state import AppState

# ----------------------------------------------------------------------
# whisper.cpp engine & model sources
# ----------------------------------------------------------------------
WHISPER_CPP_VERSION = "v1.9.2"
_RELEASE_BASE = (
    f"https://github.com/ggml-org/whisper.cpp/releases/download/{WHISPER_CPP_VERSION}"
)
# CPU build (~8 MB): bundled with the installer, self-healed in dev if missing.
CPU_ENGINE_URL = f"{_RELEASE_BASE}/whisper-bin-x64.zip"
# CUDA build (~670 MB): downloaded on demand when an NVIDIA GPU is present.
CUDA_ENGINE_URL = f"{_RELEASE_BASE}/whisper-cublas-12.4.0-bin-x64.zip"
# GGML model weights.
MODEL_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
# Silero VAD weights for whisper.cpp's --vad (~0.9 MB).
VAD_MODEL_URL = (
    "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin"
)
VAD_MODEL_NAME = "ggml-silero-v5.1.2.bin"

# Below this RMS the audio is treated as silence/noise and skipped (Whisper
# tends to hallucinate on near-silent input).
_SILENCE_RMS_THRESHOLD = 0.004

# Long dictations used to be a single wait at the end: nothing was transcribed
# until the user stopped talking, so a three-minute recording meant staring at
# an indicator for seconds. Once a recording passes this length it is cut at a
# natural pause and the finished part is transcribed while the user keeps
# speaking, so only the last segment is still pending on release.
_SEGMENT_AFTER_S = 25.0
# Window at the end of the buffer searched for that pause.
_SEGMENT_SEARCH_S = 6.0
# A chunk quieter than this counts as a pause. Cutting on silence is what makes
# the split safe: a cut inside a word would come back as two words.
_SEGMENT_SILENCE_RMS = 0.015

# Loudness normalization: quiet microphones degrade recognition, but peak
# normalization lets a single click set the scale and amplifies the noise floor
# with it. Normalize towards a target RMS instead, with a capped gain.
_TARGET_RMS = 0.06
_MAX_GAIN = 8.0
_PEAK_CEILING = 0.99

# Non-speech markers whisper emits, e.g. "(música)", "[BLANK_AUDIO]", "(applause)".
_NONSPEECH = re.compile(
    r"(?i)[\[(]\s*(?:blank_audio|inaudible|music|m[uú]sica|applause|aplausos|"
    r"silence|silencio|sound|sonido|laughter|risas|noise|ruido|beep|cough|tos|"
    r"clears throat)[^\])]*[\])]"
)
# A segment that is entirely an all-caps bracketed token, e.g. "[BLANK_AUDIO]".
_BRACKET_TOKEN = re.compile(r"^[\[(][A-Z][A-Z0-9_ ]*[\])]$")


class CustomProgressBar(tqdm):
    """tqdm subclass that fans progress out to registered callbacks (settings UI)."""

    _callbacks: list[Callable[[int, int, float], None]] = []

    @classmethod
    def register(cls, cb: Callable[[int, int, float], None]) -> None:
        if cb not in cls._callbacks:
            cls._callbacks.append(cb)

    @classmethod
    def unregister(cls, cb: Callable[[int, int, float], None] | None = None) -> None:
        if cb is None:
            cls._callbacks.clear()
        elif cb in cls._callbacks:
            cls._callbacks.remove(cb)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._notify()

    def update(self, n: int = 1) -> bool | None:
        ret = super().update(n)
        self._notify()
        return ret

    def close(self) -> None:
        super().close()
        self._notify()

    def _notify(self) -> None:
        total = self.total if self.total else 0
        n = self.n if self.n else 0
        pct = (n / total * 100) if total > 0 else 0
        for cb in list(self._callbacks):
            try:
                cb(n, total, pct)
            except Exception as e:
                logger.warning("Error in CustomProgressBar callback: %s", e)


# ----------------------------------------------------------------------
# Downloads
# ----------------------------------------------------------------------

_DOWNLOAD_ATTEMPTS = 3


def _download_file(url: str, dest: pathlib.Path, desc: str) -> None:
    """Stream *url* to *dest* with a progress bar, retrying on truncation.

    Large engine archives (~670 MB) are routinely cut short by flaky
    connections; a single failed attempt used to abort the whole download.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_exc: Exception | None = None

    for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
        try:
            _download_once(url, dest, desc)
            return
        except Exception as exc:
            last_exc = exc
            log_fn = logger.warning if attempt < _DOWNLOAD_ATTEMPTS else logger.error
            log_fn(
                "Descarga de %s fallida (intento %d/%d): %s",
                desc, attempt, _DOWNLOAD_ATTEMPTS, exc,
            )

    raise RuntimeError(f"No se pudo descargar {desc} tras {_DOWNLOAD_ATTEMPTS} intentos: {last_exc}")


def _download_once(url: str, dest: pathlib.Path, desc: str) -> None:
    """Single download attempt: stream to a .part file, then swap it in."""
    resp = requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()
    total = resp.headers.get("content-length")
    total = int(total) if total is not None else None

    tmp = dest.with_suffix(dest.suffix + ".part")
    disable_tqdm = not (sys.stdout and sys.stderr)
    written = 0
    with open(tmp, "wb") as f:
        if total is None:
            f.write(resp.content)
        else:
            with CustomProgressBar(
                total=total, unit="B", unit_scale=True, desc=desc, disable=disable_tqdm
            ) as pbar:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        written += len(chunk)
                        pbar.update(len(chunk))

    if total is not None and written != total:
        tmp.unlink(missing_ok=True)
        raise IOError(f"descarga incompleta: {written} de {total} bytes")

    tmp.replace(dest)


def _safe_extract(zf: zipfile.ZipFile, dest_dir: pathlib.Path) -> None:
    """Extract *zf* into *dest_dir*, refusing entries that escape it.

    A zip entry named ``../../evil.dll`` would otherwise be written outside the
    destination directory (Zip Slip).
    """
    root = dest_dir.resolve()
    for member in zf.infolist():
        target = (root / member.filename).resolve()
        if target != root and root not in target.parents:
            raise ValueError(f"Entrada de zip fuera del destino: {member.filename}")
    zf.extractall(dest_dir)


def _download_and_extract(url: str, dest_dir: pathlib.Path, desc: str) -> None:
    """Download a zip and extract it into *dest_dir*."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    temp_zip = pathlib.Path(tempfile.gettempdir()) / f"whisperkey_{dest_dir.name}.zip"
    try:
        _download_file(url, temp_zip, desc)
        logger.info("Extrayendo %s en %s...", desc, dest_dir)
        with zipfile.ZipFile(temp_zip, "r") as zf:
            _safe_extract(zf, dest_dir)
    finally:
        try:
            temp_zip.unlink()
        except Exception:
            pass


# ----------------------------------------------------------------------
# Engine / model resolution
# ----------------------------------------------------------------------

def _models_dir() -> pathlib.Path:
    return pathlib.Path.home() / ".whisperkey" / "models"


def _select_device(config: dict) -> str:
    """Return 'cuda' or 'cpu' based on config and hardware detection."""
    from whisperkey.platform import get_platform

    dev = (config.get("model", {}).get("device") or "auto").lower()
    if dev in ("cpu", "cuda"):
        return dev
    detected, _ = get_platform().detect_gpu()
    return "cuda" if detected == "cuda" else "cpu"


def _ensure_engine_for(device: str, overlay=None) -> pathlib.Path:
    """Ensure the whisper-server binary for *device* exists; return its path."""
    from whisperkey.platform import get_platform

    platform = get_platform()

    if device == "cuda":
        cuda_dir = platform.get_cuda_bin_dir()
        exe = resolve_server_exe(cuda_dir)
        if exe is None:
            logger.info("Motor CUDA no encontrado. Descargando (%s)...", CUDA_ENGINE_URL)
            if overlay is not None:
                overlay.show_loading()
            _download_and_extract(CUDA_ENGINE_URL, cuda_dir, "motor GPU (CUDA)")
            exe = resolve_server_exe(cuda_dir)
        if exe is None:
            raise ModelLoadError("No se encontró whisper-server tras descargar el motor CUDA.")
        return exe

    # CPU: bundled with the app; self-heal by downloading in dev if absent.
    bundled = platform.get_bundled_bin_dir()
    exe = resolve_server_exe(bundled)
    if exe is None:
        logger.info("Motor CPU no encontrado en %s. Descargando...", bundled)
        if overlay is not None:
            overlay.show_loading()
        _download_and_extract(CPU_ENGINE_URL, bundled, "motor CPU")
        exe = resolve_server_exe(bundled)
    if exe is None:
        raise ModelLoadError("No se encontró whisper-server (motor CPU).")
    return exe


def _resolve_model_name(config: dict) -> str:
    model_name = config["model"]["name"]
    if model_name == "auto":
        from whisperkey.config import detect_optimal_model

        model_name = detect_optimal_model(config)
    return model_name


def _ensure_model(model_name: str, overlay=None) -> pathlib.Path:
    from whisperkey.config import is_model_downloaded

    dest = _models_dir() / f"ggml-{model_name}.bin"
    if is_model_downloaded(model_name):
        return dest

    logger.info("Modelo %s no descargado. Descargando...", model_name)
    if overlay is not None:
        overlay.show_loading()
    url = f"{MODEL_BASE_URL}/ggml-{model_name}.bin"
    _download_file(url, dest, f"ggml-{model_name}.bin")
    logger.info("Modelo descargado en %s", dest)
    return dest


def _ensure_vad_model(overlay=None) -> pathlib.Path | None:
    """Download the Silero VAD weights if missing. Returns None on failure.

    VAD is an accuracy aid, never a startup requirement: if it cannot be
    provisioned the engine still starts without it.
    """
    dest = _models_dir() / VAD_MODEL_NAME
    if dest.exists():
        return dest

    logger.info("Descargando modelo VAD (%s)...", VAD_MODEL_NAME)
    if overlay is not None:
        overlay.show_loading()
    try:
        _download_file(VAD_MODEL_URL, dest, "modelo VAD")
        return dest
    except Exception as exc:
        logger.warning("No se pudo descargar el modelo VAD: %s. Continuando sin VAD.", exc)
        return None


def _start_server(config: dict, model_path: pathlib.Path, overlay=None) -> WhisperServer:
    """Start the resident whisper-server, falling back CUDA -> CPU on failure."""
    tcfg = config["transcription"]
    threads = tcfg.get("threads") or None
    language = tcfg.get("language") or "auto"
    prompt = tcfg.get("prompt", "")
    beam_size = int(tcfg.get("beam_size", 5))
    suppress_nst = bool(tcfg.get("suppress_non_speech", True))
    vad_model = _ensure_vad_model(overlay) if tcfg.get("vad", False) else None

    device = _select_device(config)
    attempts = ["cuda", "cpu"] if device == "cuda" else ["cpu"]

    last_exc: Exception | None = None
    for dev in attempts:
        try:
            exe = _ensure_engine_for(dev, overlay)
            server = WhisperServer(
                exe,
                model_path,
                language=language,
                threads=threads,
                prompt=prompt,
                beam_size=beam_size,
                suppress_nst=suppress_nst,
                vad_model_path=vad_model,
            )
            server.start()
            logger.info(
                "Motor %s residente en %s (hilos=%d, beam=%d, params por request=%s)",
                dev, server.base_url, server.threads, beam_size,
                "sí" if server.capabilities.accepts_request_params else "no",
            )
            return server
        except Exception as exc:
            last_exc = exc
            logger.warning("No se pudo iniciar el motor '%s': %s", dev, exc)

    raise ModelLoadError(f"No se pudo iniciar ningún motor de transcripción: {last_exc}")


# ----------------------------------------------------------------------
# Public API used by __main__ / tray
# ----------------------------------------------------------------------

def load_model(state: AppState, config: dict, sounds, overlay=None) -> None:
    """Provision engine + model and start the resident whisper-server."""
    if state.get_model() is not None or state.get_loading():
        return

    state.set_loading(True)
    try:
        model_name = _resolve_model_name(config)
        model_path = _ensure_model(model_name, overlay)
        server = _start_server(config, model_path, overlay)
        state.set_model(server)
        sounds.play_ready()
        logger.info("Modelo %s residente y listo para transcripción.", model_name)
        if overlay is not None:
            overlay.hide()
    except Exception as exc:
        logger.exception("Error al cargar el motor de transcripción")
        sounds.play_error()
        if overlay is not None:
            overlay.show_error(f"Error al cargar modelo: {exc}")
        raise ModelLoadError(f"Error al cargar el motor de transcripción: {exc}") from exc
    finally:
        state.set_loading(False)


def unload_model(state: AppState) -> None:
    """Stop the resident server, freeing the model from memory."""
    server = state.get_model()
    if server is None:
        return
    logger.info("Deteniendo motor residente...")
    try:
        if hasattr(server, "stop"):
            server.stop()
    except Exception as exc:
        logger.warning("Error al detener el motor: %s", exc)
    state.clear_model()
    logger.info("Motor detenido; memoria liberada.")


# ----------------------------------------------------------------------
# Audio prep & text cleanup
# ----------------------------------------------------------------------

def _normalize_loudness(audio: np.ndarray, rms: float) -> np.ndarray:
    """Bring *audio* towards a target RMS with a capped gain and peak ceiling.

    Whisper degrades on very quiet input, but peak normalization would let a
    single click set the scale and drag the noise floor up with it.
    """
    if rms <= 0.0:
        return audio
    gain = min(_TARGET_RMS / rms, _MAX_GAIN)
    if gain <= 1.0:
        return audio

    out = audio * gain
    peak = float(np.max(np.abs(out)))
    if peak > _PEAK_CEILING:
        out = out * (_PEAK_CEILING / peak)
    return out


def _prepare_wav(
    buffer: list, sample_rate: int, min_frames: int, channels: int = 1
) -> str | None:
    """Concatenate the buffer to a temp mono WAV. None if too short/silent."""
    audio_np = np.concatenate(buffer, axis=0).astype(np.float32)
    # Multi-channel capture must be downmixed, not flattened: flattening
    # interleaves the channels and doubles the apparent sample rate.
    if audio_np.ndim > 1 and audio_np.shape[1] > 1:
        audio_np = audio_np.mean(axis=1)
    audio_np = audio_np.flatten()

    if len(audio_np) < min_frames:
        logger.warning(
            "Audio demasiado corto (%d muestras, mínimo %d). Ignorando.",
            len(audio_np), min_frames,
        )
        return None

    rms = float(np.sqrt(np.mean(np.square(audio_np)))) if len(audio_np) else 0.0
    if rms < _SILENCE_RMS_THRESHOLD:
        logger.info("Audio bajo el umbral de energía (RMS=%.5f). Ignorando.", rms)
        return None

    audio_np = _normalize_loudness(audio_np, rms)
    audio_int16 = (np.clip(audio_np, -1.0, 1.0) * 32767.0).astype(np.int16)

    temp_fd, temp_path = tempfile.mkstemp(suffix=".wav")
    os.close(temp_fd)
    with wave.open(temp_path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_int16.tobytes())
    return temp_path


def clean_transcription(text: str) -> str:
    """Strip whisper non-speech markers (music/blank-audio/etc.) from *text*.

    Segments are concatenated, never joined with a space. whisper.cpp opens a
    new segment at token boundaries, and Whisper's tokenizer splits words into
    subword tokens, so a segment break lands mid-word often enough to matter
    ("dedic" + "ación"). Each segment already carries its own leading space when
    it starts a new word and none when it continues one, so that spacing is the
    signal: stripping it and re-joining with " " is what produced "pala bras".
    """
    out: list[str] = []
    dropped_between = False

    for raw in text.replace("\r", "").split("\n"):
        segment = _NONSPEECH.sub("", raw)
        stripped = segment.strip()
        if not stripped or _BRACKET_TOKEN.match(stripped):
            # A discarded segment was still a real boundary between the words
            # around it; remember it so they do not get glued together.
            dropped_between = True
            continue

        if out and dropped_between and not _touching_whitespace(out[-1], segment):
            out.append(" ")
        out.append(segment)
        dropped_between = False

    return re.sub(r"[^\S\n]+", " ", "".join(out)).strip()


def _touching_whitespace(left: str, right: str) -> bool:
    """True if joining *left* and *right* already keeps them separated."""
    return left[-1:].isspace() or right[:1].isspace()


def _chunk_rms(chunk) -> float:
    """RMS de un bloque de audio, tolerante a mono o multicanal."""
    arr = np.asarray(chunk, dtype=np.float32)
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(arr))))


def find_pause_split(
    buffer: list,
    sample_rate: int,
    search_seconds: float = _SEGMENT_SEARCH_S,
    silence_rms: float = _SEGMENT_SILENCE_RMS,
) -> int | None:
    """Índice donde cortar el buffer, o None si no hay una pausa clara.

    Busca el bloque más silencioso dentro de la ventana final. Cortar en
    silencio es lo que hace seguro el corte: un corte dentro de una palabra
    vuelve partido en dos, que es exactamente el defecto que se acaba de
    eliminar del pegado de segmentos.
    """
    if len(buffer) < 2:
        return None

    frames_per_chunk = max(1, len(buffer[-1]))
    search_chunks = max(1, int(search_seconds * sample_rate / frames_per_chunk))
    start = max(1, len(buffer) - search_chunks)

    best_idx: int | None = None
    best_rms = silence_rms
    for i in range(start, len(buffer)):
        rms = _chunk_rms(buffer[i])
        if rms < best_rms:
            best_rms = rms
            best_idx = i
    return best_idx


class _DictationParts:
    """Texto de una dictado repartido en segmentos, en orden."""

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._lock = threading.Lock()

    def add(self, text: str) -> None:
        if text:
            with self._lock:
                self._parts.append(text)

    def drain(self, last: str) -> str:
        with self._lock:
            parts = list(self._parts)
            self._parts.clear()
        if last:
            parts.append(last)
        return " ".join(p for p in parts if p).strip()


def _transcribe_buffer(
    buffer: list,
    state: AppState,
    injection_fn: Callable[[str], None],
    sounds,
    sample_rate: int,
    min_frames: int,
    channels: int,
    language: str | None,
    prompt: str,
    overlay=None,
    parts: "_DictationParts | None" = None,
    is_final: bool = True,
) -> None:
    """Transcribe an accumulated buffer and inject the result.

    Runs on the inference thread, never on the queue-draining thread: blocking
    the drain loop would let the audio queue overflow and silently discard
    chunks of whatever the user records next.
    """
    logger.info("Procesando buffer de %d chunks", len(buffer))

    # The overlay is showing "transcribing" from the moment the key was
    # released, so every exit path below has to resolve it. Leaving it on would
    # be worse than never showing it.
    def _clear_overlay() -> None:
        if overlay is not None:
            overlay.hide()

    def _fail_overlay(message: str) -> None:
        if overlay is not None:
            overlay.show_error(message)

    def _deliver(text: str) -> None:
        """Acumula el segmento; sólo el último entrega el dictado completo."""
        if parts is not None and not is_final:
            parts.add(text)
            return
        full = parts.drain(text) if parts is not None else text
        if not full:
            logger.warning("Transcripción vacía tras limpieza (no se reconoció voz).")
            _clear_overlay()
            return
        logger.info("Transcripción exitosa: %s", full)
        _clear_overlay()
        injection_fn(full)
        sounds.play_done()
        add_entry(full)
        trim()

    if not buffer:
        logger.warning("No hay audio acumulado para transcribir.")
        if is_final:
            _deliver("")
        else:
            _clear_overlay()
        return

    server = state.get_model()
    if server is None:
        logger.error("No se puede transcribir: el motor no está cargado.")
        _fail_overlay("El motor de transcripción no está cargado.")
        return

    temp_path = _prepare_wav(buffer, sample_rate, min_frames, channels)
    if temp_path is None:
        if is_final:
            _deliver("")
        else:
            _clear_overlay()
        return

    try:
        raw = server.transcribe(
            pathlib.Path(temp_path), prompt=prompt, language=language
        )
        _deliver(clean_transcription(raw))
    except Exception as exc:
        logger.exception("Error en transcripción")
        sounds.play_error()
        _fail_overlay(f"Error de transcripción: {exc}")
    finally:
        try:
            os.unlink(temp_path)
        except Exception as e:
            logger.warning("No se pudo eliminar archivo temporal %s: %s", temp_path, e)


# Kept as the historical name used by the tests and by __main__.
_handle_sentinel = _transcribe_buffer


def transcription_worker(
    state: AppState,
    config: dict,
    injection_fn: Callable[[str], None],
    sounds,
    overlay=None,
) -> None:
    """Worker daemon: drain audio chunks and dispatch on sentinel None.

    This loop only ever accumulates and dispatches; the actual inference runs on
    a separate single-slot executor so the audio queue keeps draining while a
    transcription is in flight.
    """
    sample_rate: int = config["audio"]["sample_rate"]
    channels: int = config["audio"].get("channels", 1)
    transcription_cfg = config["transcription"]
    min_duration: float = transcription_cfg["min_duration"]
    min_frames = int(sample_rate * min_duration)
    max_duration: float = float(transcription_cfg.get("max_duration", 600.0))
    language: str | None = transcription_cfg.get("language") or None
    prompt: str = transcription_cfg.get("prompt", "")

    segment_after_frames = int(_SEGMENT_AFTER_S * sample_rate)

    # Single slot: segments of one dictation stay strictly in order, so the
    # final one always runs last and can assemble the whole text.
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisperkey-infer")

    parts = _DictationParts()

    def dispatch(chunks: list, is_final: bool = True) -> None:
        if not chunks and not is_final:
            return
        executor.submit(
            _transcribe_buffer,
            chunks, state, injection_fn, sounds,
            sample_rate, min_frames, channels, language, prompt, overlay,
            parts, is_final,
        )

    buffer: list = []
    total_frames = 0
    try:
        while not state.shutdown_event.is_set():
            chunk = state.audio_queue.get()
            if chunk is None:
                dispatch(buffer, is_final=True)
                buffer = []
                total_frames = 0
            elif isinstance(chunk, str) and chunk == "RESET":
                logger.info("Señal de RESET: vaciando buffer sin procesar.")
                parts.drain("")
                buffer = []
                total_frames = 0
            else:
                buffer.append(chunk)
                total_frames += len(chunk)

                if max_duration > 0 and (total_frames / sample_rate) >= max_duration:
                    logger.warning(
                        "Duración máxima de grabación alcanzada (%.1fs). Forzando corte.",
                        max_duration,
                    )
                    state.stop_recording()
                    sounds.play_stop()
                    dispatch(buffer, is_final=True)
                    buffer = []
                    total_frames = 0
                    continue

                # Dictado largo: adelantar el trabajo cortando en una pausa, de
                # modo que al soltar la tecla sólo quede pendiente el último
                # tramo en lugar de la grabación entera.
                if total_frames >= segment_after_frames:
                    split = find_pause_split(buffer, sample_rate)
                    if split is not None:
                        head, buffer = buffer[:split], buffer[split:]
                        logger.info(
                            "Dictado largo: transcribiendo %.1fs mientras seguís hablando.",
                            sum(len(c) for c in head) / sample_rate,
                        )
                        dispatch(head, is_final=False)
                        total_frames = sum(len(c) for c in buffer)
    finally:
        executor.shutdown(wait=False)
