"""Rigorous tests for the sounds feedback module."""

from __future__ import annotations

import importlib
import threading
import time
from typing import Any
from unittest.mock import MagicMock, call

import pytest

import whisperkey.platform
import whisperkey.sounds as sounds


def _wait_for(condicion, timeout: float = 3.0) -> bool:
    """Espera a que el beep del thread daemon ocurra, sin dormir a ciegas.

    Un sleep fijo ata el test a la carga de la máquina: con una suite que
    además levanta ventanas Tk, el thread llega tarde y el test parpadea.
    """
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.01)
    return False



def _drain_sound_threads(previos: set[int] | None = None, timeout: float = 1.0) -> None:
    """Espera a los threads nacidos durante el test, ignorando los preexistentes.

    Cada test recarga el módulo y sustituye la plataforma, así que un thread de
    sonido que sigue vivo del test anterior escribiría sobre el mock nuevo. Los
    threads que ya estaban vivos antes (otros módulos dejan algunos corriendo
    para siempre) no se esperan: agotarían el timeout sin aportar nada.
    """
    previos = previos or set()
    limite = time.monotonic() + timeout
    principal = threading.main_thread()
    while time.monotonic() < limite:
        nuevos = [
            th for th in threading.enumerate()
            if th is not principal and th.is_alive() and id(th) not in previos
        ]
        if not nuevos:
            return
        time.sleep(0.01)


@pytest.fixture
def mock_platform(monkeypatch: pytest.MonkeyPatch):
    """Provide a mocked platform and reload sounds module with it."""
    previos = {id(th) for th in threading.enumerate()}
    mock = MagicMock()
    mock.play_beep = MagicMock()
    monkeypatch.setattr(whisperkey.platform, "get_platform", lambda: mock)
    importlib.reload(sounds)
    yield mock
    _drain_sound_threads(previos)


class TestSoundsEnabled:
    def test_sounds_enabled_by_default(self, mock_platform: MagicMock) -> None:
        assert sounds._enabled is True

    def test_set_enabled_disables_sounds(self, mock_platform: MagicMock) -> None:
        sounds.set_enabled(False)
        assert sounds._enabled is False
        sounds.play_start()
        sounds.play_stop()
        sounds.play_ready()
        sounds.play_error()
        mock_platform.play_beep.assert_not_called()

    def test_set_enabled_reenables_sounds(self, mock_platform: MagicMock) -> None:
        sounds.set_enabled(False)
        sounds.set_enabled(True)
        sounds.play_start()
        assert _wait_for(lambda: mock_platform.play_beep.called)


class TestSoundsPlayStart:
    def test_play_start_triggers_beep(self, mock_platform: MagicMock) -> None:
        sounds.set_enabled(True)
        sounds.play_start()
        assert _wait_for(lambda: mock_platform.play_beep.called)
        mock_platform.play_beep.assert_any_call(1200, 0.1)


class TestSoundsPlayStop:
    def test_play_stop_triggers_beep(self, mock_platform: MagicMock) -> None:
        sounds.set_enabled(True)
        sounds.play_stop()
        assert _wait_for(lambda: mock_platform.play_beep.called)
        mock_platform.play_beep.assert_any_call(800, 0.1)


class TestSoundsPlayReady:
    def test_play_ready_triggers_double_beep(
        self, mock_platform: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ejecuta el trabajo del thread en línea, sin depender del scheduler.

        winsound.Beep es síncrono y se serializa en todo el proceso, así que un
        beep real dejado por otro test bloquea a éste y el resultado pasa a
        depender del orden de ejecución. Lo que interesa verificar es que
        play_ready emite los dos tonos, no cómo los agenda el sistema.
        """
        class ThreadInmediato:
            def __init__(self, target=None, args=(), kwargs=None, daemon=None):
                self._target, self._args = target, args
                self._kwargs = kwargs or {}

            def start(self):
                self._target(*self._args, **self._kwargs)

        monkeypatch.setattr(sounds.threading, "Thread", ThreadInmediato)
        sounds.set_enabled(True)
        sounds.play_ready()

        assert mock_platform.play_beep.call_args_list == [
            call(1000, 0.080),
            call(1200, 0.080),
        ]

    def test_play_ready_runs_off_the_main_thread(self, mock_platform: MagicMock) -> None:
        """El sonido nunca debe bloquear al hilo que lo dispara."""
        sounds.set_enabled(True)
        sounds.play_ready()  # con el threading real: no debe bloquear ni fallar


class TestSoundsPlayError:
    def test_play_error_triggers_beep(self, mock_platform: MagicMock) -> None:
        sounds.set_enabled(True)
        sounds.play_error()
        assert _wait_for(lambda: mock_platform.play_beep.called)
        mock_platform.play_beep.assert_any_call(400, 0.3)


class TestSoundsThreading:
    def test_sounds_run_in_background_threads(self, mock_platform: MagicMock) -> None:
        sounds.set_enabled(True)
        sounds.play_start()
        sounds.play_stop()
        sounds.play_ready()
        sounds.play_error()
        assert _wait_for(lambda: mock_platform.play_beep.call_count >= 4)
