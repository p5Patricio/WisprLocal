"""Rigorous tests for text injection via clipboard + paste shortcut."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from whisperkey import injection
from whisperkey.errors import InjectionError


@pytest.fixture
def mock_dependencies(monkeypatch: pytest.MonkeyPatch):
    """Mock clipboard and keyboard controller for isolated injection tests."""
    clipboard_state = {"current": "original", "previous": "original", "copies": 0}

    def fake_copy(text: str) -> None:
        clipboard_state["current"] = text
        clipboard_state["copies"] += 1

    def fake_paste() -> str:
        return clipboard_state["current"]

    monkeypatch.setattr("pyperclip.copy", fake_copy)
    monkeypatch.setattr("pyperclip.paste", fake_paste)

    class FakeController:
        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []

        def pressed(self, key: object):
            class Context:
                def __enter__(ctx) -> "Context":
                    return ctx

                def __exit__(ctx, *args: object) -> None:
                    pass

            return Context()

        def press(self, key: object) -> None:
            self.calls.append(("press", str(key)))

        def release(self, key: object) -> None:
            self.calls.append(("release", str(key)))

    fake_controller = FakeController()
    monkeypatch.setattr("pynput.keyboard.Controller", lambda: fake_controller)

    monkeypatch.setattr(
        injection._platform,  # type: ignore[attr-defined]
        "get_paste_shortcut",
        lambda: ("ctrl", "v"),
    )

    return clipboard_state, fake_controller


class TestInjectText:
    def test_inject_empty_text_is_noop(self, mock_dependencies: tuple) -> None:
        clipboard_state, controller = mock_dependencies
        injection.inject_text("")
        assert clipboard_state["current"] == "original"
        assert controller.calls == []

    def test_inject_copies_text_and_sends_shortcut(self, mock_dependencies: tuple) -> None:
        clipboard_state, controller = mock_dependencies
        injection.inject_text("hello world", restore_delay_s=0.0)
        # clipboard is restored after injection; controller should have sent paste
        assert ("press", "v") in controller.calls
        assert ("release", "v") in controller.calls
        assert clipboard_state["current"] == "original"

    def test_inject_restores_previous_clipboard(self, mock_dependencies: tuple) -> None:
        clipboard_state, controller = mock_dependencies
        injection.inject_text("new text", restore_delay_s=0.0)
        assert clipboard_state["current"] == "original"

    def test_inject_skips_restore_when_previous_too_large(self, mock_dependencies: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
        clipboard_state, controller = mock_dependencies
        clipboard_state["current"] = "x" * (injection._CLIPBOARD_SIZE_LIMIT + 1)
        injection.inject_text("new text", restore_delay_s=0.0)
        # Should not restore because previous was too large
        assert clipboard_state["current"] == "new text"

    def test_inject_raises_injection_error_on_failure(self, mock_dependencies: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
        def failing_copy(_: str) -> None:
            raise RuntimeError("clipboard broken")

        monkeypatch.setattr("pyperclip.copy", failing_copy)
        with pytest.raises(InjectionError):
            injection.inject_text("boom", restore_delay_s=0.0)


class TestClipboardConfirmation:
    """El pegado espera la confirmación real del portapapeles, no un tiempo fijo.

    Pegar antes de que el portapapeles esté listo inserta el contenido anterior;
    esperar un tiempo fijo pensado para el peor caso era el 28% de la latencia
    percibida de un dictado corto.
    """

    def test_paste_happens_only_after_clipboard_confirms(
        self, mock_dependencies: tuple, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clipboard_state, controller = mock_dependencies
        reads = {"n": 0}
        real_paste = __import__("pyperclip").paste

        def slow_paste() -> str:
            # El portapapeles tarda tres lecturas en reflejar la copia.
            reads["n"] += 1
            if reads["n"] <= 3:
                return "stale"
            return clipboard_state["current"]

        monkeypatch.setattr("pyperclip.paste", slow_paste)
        injection.inject_text("texto nuevo", restore_delay_s=0.0)

        assert reads["n"] > 3
        assert ("press", "v") in controller.calls

    def test_confirmation_returns_immediately_when_ready(
        self, mock_dependencies: tuple
    ) -> None:
        clipboard_state, _ = mock_dependencies
        clipboard_state["current"] = "ya listo"
        assert injection._wait_for_clipboard("ya listo", timeout_s=0.05) is True

    def test_confirmation_times_out_without_hanging(
        self, mock_dependencies: tuple
    ) -> None:
        assert injection._wait_for_clipboard("nunca llega", timeout_s=0.03) is False

    def test_paste_still_sent_when_confirmation_times_out(
        self, mock_dependencies: tuple, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Un portapapeles que no confirma no debe perder el dictado."""
        clipboard_state, controller = mock_dependencies
        monkeypatch.setattr("pyperclip.paste", lambda: "nunca coincide")
        monkeypatch.setattr(injection, "_CLIPBOARD_TIMEOUT_S", 0.03)
        injection.inject_text("texto", restore_delay_s=0.0)
        assert ("press", "v") in controller.calls


class TestKeyMap:
    def test_key_map_contains_expected_modifiers(self) -> None:
        from pynput import keyboard
        assert injection._KEY_MAP["ctrl"] == keyboard.Key.ctrl
        assert injection._KEY_MAP["command"] == keyboard.Key.cmd
        assert injection._KEY_MAP["alt"] == keyboard.Key.alt
        assert injection._KEY_MAP["shift"] == keyboard.Key.shift
