"""Regression tests for the audio paths that cut and glued words together."""

from __future__ import annotations

import time
import wave
import zipfile
from pathlib import Path

import numpy as np
import pytest

from whisperkey import transcription
from whisperkey.state import AppState


class TestStopGrace:
    def test_capture_continues_after_the_key_is_released(self) -> None:
        """PortAudio still holds the last block when the hotkey comes up."""
        state = AppState()
        state.set_ptt(True)
        state.begin_stop_grace(0.3)

        assert state.is_recording() is False
        assert state.is_capturing() is True

    def test_capture_stops_once_the_grace_window_expires(self) -> None:
        state = AppState()
        state.set_ptt(True)
        state.begin_stop_grace(0.05)
        time.sleep(0.1)

        assert state.is_capturing() is False

    def test_stop_recording_ends_capture_immediately(self) -> None:
        state = AppState()
        state.set_ptt(True)
        state.begin_stop_grace(5.0)
        state.stop_recording()

        assert state.is_capturing() is False

    def test_stop_recording_keeps_queued_audio(self) -> None:
        state = AppState()
        state.audio_queue.put(np.zeros((10, 1), dtype=np.float32))
        state.set_ptt(True)
        state.stop_recording()

        assert state.audio_queue.qsize() == 1


class TestDropAccounting:
    def test_dropped_chunks_are_counted(self) -> None:
        """Discarded audio must leave a trace; silent loss cannot be diagnosed."""
        state = AppState()
        assert state.note_dropped_chunk() == 1
        assert state.note_dropped_chunk() == 2
        assert state.dropped_chunks == 2

    def test_reset_recording_discards_and_reports(self, caplog: pytest.LogCaptureFixture) -> None:
        state = AppState()
        for _ in range(3):
            state.audio_queue.put(np.zeros((10, 1), dtype=np.float32))

        with caplog.at_level("WARNING"):
            state.reset_recording()

        assert "3 chunks" in caplog.text
        assert state.audio_queue.get_nowait() == "RESET"


class TestPrepareWav:
    def _read(self, path: str) -> tuple[int, int, np.ndarray]:
        with wave.open(path, "rb") as wav:
            frames = wav.getnframes()
            data = np.frombuffer(wav.readframes(frames), dtype=np.int16)
            return wav.getnchannels(), wav.getframerate(), data

    def test_stereo_is_downmixed_not_interleaved(self, tmp_path: Path) -> None:
        """Flattening stereo doubles the apparent sample rate and garbles speech."""
        frames = 8000
        left = np.full((frames, 1), 0.5, dtype=np.float32)
        right = np.full((frames, 1), 0.1, dtype=np.float32)
        stereo = np.concatenate([left, right], axis=1)

        path = transcription._prepare_wav([stereo], 16000, 100, channels=2)
        assert path is not None
        try:
            channels, rate, data = self._read(path)
            assert channels == 1
            assert rate == 16000
            assert len(data) == frames  # not 2 * frames
        finally:
            Path(path).unlink(missing_ok=True)

    def test_rejects_audio_below_the_silence_floor(self) -> None:
        quiet = np.full((16000, 1), 1e-5, dtype=np.float32)
        assert transcription._prepare_wav([quiet], 16000, 100) is None

    def test_rejects_audio_shorter_than_the_minimum(self) -> None:
        short = np.full((50, 1), 0.2, dtype=np.float32)
        assert transcription._prepare_wav([short], 16000, 4800) is None


class TestLoudnessNormalization:
    def _rms(self, audio: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.square(audio))))

    def test_quiet_audio_is_brought_up_towards_the_target(self) -> None:
        audio = np.full(1000, 0.01, dtype=np.float32)
        out = transcription._normalize_loudness(audio, self._rms(audio))
        assert self._rms(out) > self._rms(audio)
        assert self._rms(out) <= transcription._TARGET_RMS + 1e-6

    def test_gain_is_capped(self) -> None:
        audio = np.full(1000, 1e-4, dtype=np.float32)
        out = transcription._normalize_loudness(audio, self._rms(audio))
        assert np.max(np.abs(out)) <= 1e-4 * transcription._MAX_GAIN + 1e-9

    def test_loud_audio_is_left_alone(self) -> None:
        audio = np.full(1000, 0.5, dtype=np.float32)
        out = transcription._normalize_loudness(audio, self._rms(audio))
        assert np.allclose(out, audio)

    def test_peak_never_clips(self) -> None:
        audio = np.full(1000, 0.01, dtype=np.float32)
        audio[0] = 0.9  # a single click must not push the signal over the ceiling
        out = transcription._normalize_loudness(audio, self._rms(audio))
        assert np.max(np.abs(out)) <= transcription._PEAK_CEILING + 1e-6

    def test_silence_is_not_amplified(self) -> None:
        audio = np.zeros(1000, dtype=np.float32)
        assert np.array_equal(transcription._normalize_loudness(audio, 0.0), audio)


class TestSafeExtract:
    def test_rejects_paths_escaping_the_destination(self, tmp_path: Path) -> None:
        archive = tmp_path / "evil.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../escaped.dll", b"x")

        dest = tmp_path / "out"
        dest.mkdir()
        with zipfile.ZipFile(archive) as zf:
            with pytest.raises(ValueError, match="fuera del destino"):
                transcription._safe_extract(zf, dest)

        assert not (tmp_path / "escaped.dll").exists()

    def test_extracts_normal_and_nested_entries(self, tmp_path: Path) -> None:
        archive = tmp_path / "ok.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("whisper-server.exe", b"x")
            zf.writestr("Release/whisper.dll", b"y")

        dest = tmp_path / "out"
        with zipfile.ZipFile(archive) as zf:
            transcription._safe_extract(zf, dest)

        assert (dest / "whisper-server.exe").exists()
        assert (dest / "Release" / "whisper.dll").exists()


class TestSubwordSegmentJoining:
    """whisper.cpp opens segments at token boundaries, and Whisper's tokenizer
    splits words into subword tokens, so a break lands mid-word regularly.

    Every case below was taken verbatim from real dictations that came out
    wrong: joining stripped segments with a space turned "dedicación" into
    "dedic ación".
    """

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("la dedic\nación necesaria", "la dedicación necesaria"),
            ("los días pi\nensan", "los días piensan"),
            ("encontrar mét\nodos alternativos", "encontrar métodos alternativos"),
            ("distribuir y organiz\nar tu tiempo", "distribuir y organizar tu tiempo"),
            ("necesitar\nás tomar decisiones", "necesitarás tomar decisiones"),
            ("cualquier circun\nstancia", "cualquier circunstancia"),
            ("hasta que alc\nance", "hasta que alcance"),
            ("la gente no em\nprende", "la gente no emprende"),
            ("comúnmente us\nado", "comúnmente usado"),
            ("mucho que gan\nar", "mucho que ganar"),
        ],
    )
    def test_subword_splits_are_rejoined(self, raw: str, expected: str) -> None:
        assert transcription.clean_transcription(raw) == expected

    def test_real_word_boundaries_keep_their_space(self) -> None:
        """Segments that start a new word carry their own leading space."""
        raw = "Necesito revisar las palabras\n exactas que aparecen en la\n documentación"
        assert transcription.clean_transcription(raw) == (
            "Necesito revisar las palabras exactas que aparecen en la documentación"
        )

    def test_discarded_segment_still_separates_its_neighbours(self) -> None:
        """Dropping a non-speech marker must not glue the words around it."""
        assert transcription.clean_transcription("Texto\n[MUSIC]\nmas texto") == "Texto mas texto"

    def test_discarded_segment_does_not_double_an_existing_space(self) -> None:
        assert transcription.clean_transcription("Texto\n(música)\n mas texto") == "Texto mas texto"

    def test_mixed_boundaries_in_one_dictation(self) -> None:
        raw = "Voy a organiz\nar el backend,\n después reviso los mét\nodos del deploy."
        assert transcription.clean_transcription(raw) == (
            "Voy a organizar el backend, después reviso los métodos del deploy."
        )


class TestLongDictationSegmentation:
    """Un dictado largo era una sola espera al final. Ahora se corta en una
    pausa y los tramos terminados se transcriben mientras el usuario habla."""

    def _voz(self, n: int, nivel: float = 0.2) -> np.ndarray:
        rng = np.random.default_rng(3)
        return (rng.normal(0, nivel, (n, 1))).astype(np.float32)

    def _silencio(self, n: int) -> np.ndarray:
        return np.full((n, 1), 1e-4, dtype=np.float32)

    def test_splits_on_the_quietest_block(self) -> None:
        buffer = [self._voz(400) for _ in range(20)]
        buffer[14] = self._silencio(400)
        idx = transcription.find_pause_split(buffer, 16000)
        assert idx == 14

    def test_no_split_without_a_real_pause(self) -> None:
        """Cortar a mitad de palabra devolvería la palabra partida en dos."""
        buffer = [self._voz(400) for _ in range(20)]
        assert transcription.find_pause_split(buffer, 16000) is None

    def test_only_searches_the_recent_window(self) -> None:
        """Un silencio viejo no sirve: cortaría ahí y dejaría todo pendiente."""
        buffer = [self._voz(400) for _ in range(400)]
        buffer[2] = self._silencio(400)  # silencio muy al principio
        idx = transcription.find_pause_split(buffer, 16000, search_seconds=1.0)
        assert idx is None

    def test_split_is_never_at_zero(self) -> None:
        buffer = [self._silencio(400) for _ in range(5)]
        idx = transcription.find_pause_split(buffer, 16000)
        assert idx is None or idx >= 1

    def test_too_short_buffer_is_not_split(self) -> None:
        assert transcription.find_pause_split([], 16000) is None
        assert transcription.find_pause_split([self._silencio(400)], 16000) is None


class TestDictationParts:
    """Los tramos se entregan una sola vez, en orden, al terminar."""

    def test_parts_are_joined_in_order(self) -> None:
        parts = transcription._DictationParts()
        parts.add("primera parte")
        parts.add("segunda parte")
        assert parts.drain("y el final") == "primera parte segunda parte y el final"

    def test_drain_empties_the_buffer(self) -> None:
        parts = transcription._DictationParts()
        parts.add("algo")
        parts.drain("")
        assert parts.drain("") == ""

    def test_empty_parts_are_ignored(self) -> None:
        parts = transcription._DictationParts()
        parts.add("")
        parts.add("texto")
        assert parts.drain("") == "texto"

    def test_partial_segments_do_not_inject(self) -> None:
        """Sólo el segmento final entrega el texto a la aplicación."""
        from unittest.mock import MagicMock
        from whisperkey.state import AppState

        inject = MagicMock()
        parts = transcription._DictationParts()
        state = AppState()
        state.set_model(MagicMock(transcribe=MagicMock(return_value="hola mundo")))

        audio = [np.full((16000, 1), 0.2, dtype=np.float32)]
        transcription._transcribe_buffer(
            audio, state, inject, MagicMock(), 16000, 100, 1, "es", "",
            None, parts, False,
        )
        inject.assert_not_called()

        transcription._transcribe_buffer(
            audio, state, inject, MagicMock(), 16000, 100, 1, "es", "",
            None, parts, True,
        )
        inject.assert_called_once_with("hola mundo hola mundo")
