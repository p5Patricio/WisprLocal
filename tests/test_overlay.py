"""Rigorous tests for the overlay UI using mocked tkinter."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from whisperkey import overlay


class FakeTk:
    """Mock tkinter.Tk root."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self._withdrawn = False
        self._deiconified = False
        self._destroyed = False
        self._geometry = ""
        self._overrideredirect = False
        self._alpha = 1.0
        self._bg = ""
        self._topmost = False
        self._scheduled: list[tuple[int, Any]] = []
        self._width = 200
        self._height = 60
        self._screen_width = 1920
        self._screen_height = 1080

    def overrideredirect(self, value: bool) -> None:
        self._overrideredirect = value
        self.calls.append(("overrideredirect", (value,), {}))

    def wm_attributes(self, key: str, value: Any | None = None) -> Any:
        if value is None:
            if key == "-topmost":
                return self._topmost
            if key == "-alpha":
                return self._alpha
        if key == "-topmost":
            self._topmost = value
        elif key == "-alpha":
            self._alpha = value
        self.calls.append(("wm_attributes", (key, value), {}))

    def configure(self, **kwargs: Any) -> None:
        self._bg = kwargs.get("bg", self._bg)
        self.calls.append(("configure", tuple(), kwargs))

    def withdraw(self) -> None:
        self._withdrawn = True
        self.calls.append(("withdraw", tuple(), {}))

    def deiconify(self) -> None:
        self._deiconified = True
        self.calls.append(("deiconify", tuple(), {}))

    def destroy(self) -> None:
        self._destroyed = True
        self.calls.append(("destroy", tuple(), {}))

    def geometry(self, value: str | None = None) -> str:
        if value is not None:
            self._geometry = value
            self.calls.append(("geometry", (value,), {}))
        return self._geometry

    def update_idletasks(self) -> None:
        self.calls.append(("update_idletasks", tuple(), {}))

    def winfo_reqwidth(self) -> int:
        return self._width

    def winfo_reqheight(self) -> int:
        return self._height

    def winfo_screenwidth(self) -> int:
        return self._screen_width

    def winfo_screenheight(self) -> int:
        return self._screen_height

    def after(self, ms: int, fn: Any) -> str:
        """after(0) es el dispatch entre threads y corre ya; el resto se agenda.

        Ejecutar los timers al vuelo haría que las animaciones se
        reprogramen a sí mismas para siempre.
        """
        self._scheduled.append((ms, fn))
        self.calls.append(("after", (ms, fn), {}))
        if ms == 0:
            fn()
        return f"job{len(self._scheduled)}"

    def after_cancel(self, job: str) -> None:
        self.calls.append(("after_cancel", (job,), {}))

    def run_pending(self) -> None:
        """Dispara los timers agendados una vez (sin recursión)."""
        pending = [fn for ms, fn in self._scheduled if ms > 0]
        self._scheduled = [(ms, fn) for ms, fn in self._scheduled if ms == 0]
        for fn in pending:
            fn()

    def mainloop(self) -> None:
        self.calls.append(("mainloop", tuple(), {}))


class FakeLabel:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.config_calls: list[dict[str, Any]] = []

    def config(self, **kwargs: Any) -> None:
        self.config_calls.append(kwargs)

    def pack(self, **kwargs: Any) -> None:
        pass

    def update_idletasks(self) -> None:
        pass

    def winfo_reqwidth(self) -> int:
        return 120

    def winfo_reqheight(self) -> int:
        return 20


class FakeCanvas:
    """Canvas de la píldora: registra las figuras dibujadas."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.items: list[tuple[str, dict[str, Any]]] = []
        self.config_calls: list[dict[str, Any]] = []

    def _add(self, kind: str, kwargs: dict[str, Any]) -> int:
        self.items.append((kind, kwargs))
        return len(self.items)

    def create_oval(self, *a: Any, **kw: Any) -> int:
        return self._add("oval", kw)

    def create_rectangle(self, *a: Any, **kw: Any) -> int:
        return self._add("rect", kw)

    def create_line(self, *a: Any, **kw: Any) -> int:
        return self._add("line", kw)

    def create_window(self, *a: Any, **kw: Any) -> int:
        return self._add("window", kw)

    def delete(self, *a: Any) -> None:
        self.items.clear()

    def config(self, **kwargs: Any) -> None:
        self.config_calls.append(kwargs)

    def pack(self, **kwargs: Any) -> None:
        pass

    def find_withtag(self, tag: str) -> list[int]:
        return list(range(1, len(self.items) + 1))

    def itemconfig(self, item: int, **kwargs: Any) -> None:
        if 1 <= item <= len(self.items):
            self.items[item - 1][1].update(kwargs)


def _overlay_listo(ov, fake_labels) -> None:
    """Verifica que el overlay quedó construido.

    Con el thread síncrono del fixture esto es inmediato; se mantiene la
    comprobación para que un fallo de construcción se lea claro.
    """
    assert fake_labels, "el overlay no construyó su etiqueta"
    assert ov._canvas is not None and ov._label is not None


@pytest.fixture
def mock_tk(monkeypatch: pytest.MonkeyPatch):
    """Provide mocked tkinter and label factories."""
    fake_roots: list[FakeTk] = []
    fake_labels: list[FakeLabel] = []
    fake_canvases: list[FakeCanvas] = []

    def make_root() -> FakeTk:
        root = FakeTk()
        fake_roots.append(root)
        return root

    def make_label(*args: Any, **kwargs: Any) -> FakeLabel:
        label = FakeLabel(*args, **kwargs)
        fake_labels.append(label)
        return label

    def make_canvas(*args: Any, **kwargs: Any) -> FakeCanvas:
        canvas = FakeCanvas(*args, **kwargs)
        fake_canvases.append(canvas)
        return canvas

    class ThreadInmediato:
        """Construye el overlay en línea, sin depender del planificador.

        FakeTk.mainloop() vuelve enseguida, así que no hay nada que esperar. El
        thread real hacía que estos tests dependieran de la carga del proceso:
        con otros módulos ocupando el GIL, los widgets llegaban tarde.
        """

        def __init__(self, target=None, args=(), kwargs=None, daemon=None, name=None):
            self._target, self._args = target, args
            self._kwargs = kwargs or {}

        def start(self):
            self._target(*self._args, **self._kwargs)

    import tkinter as tk
    monkeypatch.setattr(overlay.threading, "Thread", ThreadInmediato)
    monkeypatch.setattr(tk, "Tk", make_root)
    monkeypatch.setattr(tk, "Label", make_label)
    monkeypatch.setattr(tk, "Canvas", make_canvas)
    monkeypatch.setattr(overlay, "tk", tk)
    return fake_roots, fake_labels, fake_canvases


class TestRecordingOverlay:
    def test_disabled_overlay_does_not_create_window(self, mock_tk: tuple) -> None:
        fake_roots, fake_labels, fake_canvases = mock_tk
        config = {"overlay": {"enabled": False}}
        ov = overlay.RecordingOverlay(config)
        assert ov._enabled is False
        assert fake_roots == []

    def test_enabled_overlay_creates_window(self, mock_tk: tuple) -> None:
        fake_roots, fake_labels, fake_canvases = mock_tk
        config = {"overlay": {"enabled": True, "position": "bottom-right", "opacity": 0.85, "font_size": 14}}
        ov = overlay.RecordingOverlay(config)
        assert len(fake_roots) == 1
        root = fake_roots[0]
        assert root._overrideredirect is True
        assert root._topmost is True
        assert root._alpha == 0.85
        assert root._withdrawn is True

    def test_position_bottom_right(self, mock_tk: tuple) -> None:
        fake_roots, fake_labels, fake_canvases = mock_tk
        config = {"overlay": {"enabled": True, "position": "bottom-right", "opacity": 0.85, "font_size": 14}}
        ov = overlay.RecordingOverlay(config)
        _overlay_listo(ov, fake_labels)
        ov.show_ptt()
        root = fake_roots[0]
        assert "+" in root._geometry

    def test_show_ptt(self, mock_tk: tuple) -> None:
        fake_roots, fake_labels, fake_canvases = mock_tk
        config = {"overlay": {"enabled": True, "position": "bottom-right", "opacity": 0.85, "font_size": 14}}
        ov = overlay.RecordingOverlay(config)
        _overlay_listo(ov, fake_labels)
        ov.show_ptt()
        label = fake_labels[0]
        assert any(call.get("text") == overlay.STATES["ptt"]["text"] for call in label.config_calls)
        assert fake_roots[0]._deiconified

    def test_show_toggle(self, mock_tk: tuple) -> None:
        fake_roots, fake_labels, fake_canvases = mock_tk
        config = {"overlay": {"enabled": True, "position": "bottom-right", "opacity": 0.85, "font_size": 14}}
        ov = overlay.RecordingOverlay(config)
        _overlay_listo(ov, fake_labels)
        ov.show_toggle()
        label = fake_labels[0]
        assert any(call.get("text") == overlay.STATES["toggle"]["text"] for call in label.config_calls)

    def test_show_loading(self, mock_tk: tuple) -> None:
        fake_roots, fake_labels, fake_canvases = mock_tk
        config = {"overlay": {"enabled": True, "position": "bottom-right", "opacity": 0.85, "font_size": 14}}
        ov = overlay.RecordingOverlay(config)
        _overlay_listo(ov, fake_labels)
        ov.show_loading()
        label = fake_labels[0]
        assert any(call.get("text") == overlay.STATES["loading"]["text"] for call in label.config_calls)

    def test_show_error(self, mock_tk: tuple) -> None:
        fake_roots, fake_labels, fake_canvases = mock_tk
        config = {"overlay": {"enabled": True, "position": "bottom-right", "opacity": 0.85, "font_size": 14}}
        ov = overlay.RecordingOverlay(config)
        _overlay_listo(ov, fake_labels)
        ov.show_error("custom error")
        label = fake_labels[0]
        assert any(call.get("text") == "custom error" for call in label.config_calls)

    def test_hide(self, mock_tk: tuple) -> None:
        fake_roots, fake_labels, fake_canvases = mock_tk
        config = {"overlay": {"enabled": True, "position": "bottom-right", "opacity": 0.85, "font_size": 14}}
        ov = overlay.RecordingOverlay(config)
        _overlay_listo(ov, fake_labels)
        ov.show_ptt()
        ov.hide()
        assert fake_roots[0]._withdrawn

    def test_destroy(self, mock_tk: tuple) -> None:
        fake_roots, fake_labels, fake_canvases = mock_tk
        config = {"overlay": {"enabled": True, "position": "bottom-right", "opacity": 0.85, "font_size": 14}}
        ov = overlay.RecordingOverlay(config)
        ov.destroy()
        assert fake_roots[0]._destroyed

    def test_position_top_left(self, mock_tk: tuple) -> None:
        fake_roots, fake_labels, fake_canvases = mock_tk
        config = {"overlay": {"enabled": True, "position": "top-left", "opacity": 0.85, "font_size": 14}}
        ov = overlay.RecordingOverlay(config)
        _overlay_listo(ov, fake_labels)
        ov.show_ptt()
        root = fake_roots[0]
        # geometry is "+x+y"
        assert root._geometry.startswith("+")

    def test_invalid_position_defaults_to_bottom_right(self, mock_tk: tuple) -> None:
        fake_roots, fake_labels, fake_canvases = mock_tk
        config = {"overlay": {"enabled": True, "position": "invalid", "opacity": 0.85, "font_size": 14}}
        ov = overlay.RecordingOverlay(config)
        _overlay_listo(ov, fake_labels)
        ov.show_ptt()
        root = fake_roots[0]
        assert root._geometry


class TestProcessingFeedback:
    """Entre soltar la tecla y ver el texto no había ninguna señal, y una
    transcripción larga se percibía como que la aplicación se colgó."""

    def _overlay(self, mock_tk: tuple):
        config = {"overlay": {"enabled": True, "position": "bottom-right", "opacity": 0.85, "font_size": 14}}
        return overlay.RecordingOverlay(config), mock_tk

    def test_processing_shows_and_animates(self, mock_tk: tuple) -> None:
        fake_roots, fake_labels, _ = mock_tk
        ov, _ = self._overlay(mock_tk)
        ov.show_processing()
        textos = [c.get("text") for c in fake_labels[0].config_calls if c.get("text")]
        assert any(t.startswith(overlay.STATES["processing"]["text"]) for t in textos)
        assert fake_roots[0]._deiconified

    def test_processing_animation_advances_the_dots(self, mock_tk: tuple) -> None:
        fake_roots, fake_labels, _ = mock_tk
        ov, _ = self._overlay(mock_tk)
        ov.show_processing()
        for _ in range(3):
            fake_roots[0].run_pending()
        textos = [c.get("text") for c in fake_labels[0].config_calls if c.get("text")]
        assert len({t for t in textos if "Transcribiendo" in t}) > 1

    def test_processing_reports_elapsed_time_on_long_waits(
        self, mock_tk: tuple, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_roots, fake_labels, _ = mock_tk
        ov, _ = self._overlay(mock_tk)
        ov.show_processing()
        # Simular que ya pasó el umbral para mostrar segundos.
        ov._anim_started -= overlay._PROCESSING_ELAPSED_AFTER_S + 1
        fake_roots[0].run_pending()
        textos = [c.get("text") for c in fake_labels[0].config_calls if c.get("text")]
        assert any(t.rstrip().endswith("s") and "Transcribiendo" in t for t in textos)

    def test_cancelled_state_is_transient(self, mock_tk: tuple) -> None:
        fake_roots, fake_labels, _ = mock_tk
        ov, _ = self._overlay(mock_tk)
        ov.show_cancelled()
        textos = [c.get("text") for c in fake_labels[0].config_calls if c.get("text")]
        assert overlay.STATES["cancelled"]["text"] in textos
        fake_roots[0].run_pending()
        assert fake_roots[0]._withdrawn

    def test_error_hides_itself(self, mock_tk: tuple) -> None:
        fake_roots, fake_labels, _ = mock_tk
        ov, _ = self._overlay(mock_tk)
        ov.show_error("algo falló")
        fake_roots[0].run_pending()
        assert fake_roots[0]._withdrawn

    def test_error_can_be_pinned(self, mock_tk: tuple) -> None:
        fake_roots, fake_labels, _ = mock_tk
        ov, _ = self._overlay(mock_tk)
        fake_roots[0]._withdrawn = False
        ov.show_error("permanente", auto_hide_ms=0)
        fake_roots[0].run_pending()
        assert fake_roots[0]._withdrawn is False


class TestPillRendering:
    """La píldora se dibuja con esquinas redondeadas y un punto de estado."""

    def _overlay(self, position: str = "bottom-right"):
        return overlay.RecordingOverlay(
            {"overlay": {"enabled": True, "position": position, "opacity": 0.85, "font_size": 14}}
        )

    def test_pill_draws_dot_and_rounded_ends(self, mock_tk: tuple) -> None:
        _, _, fake_canvases = mock_tk
        ov = self._overlay()
        ov.show_ptt()
        kinds = [k for k, _ in fake_canvases[0].items]
        # dos óvalos para los extremos redondeados + el punto de estado
        assert kinds.count("oval") >= 3
        assert "window" in kinds

    def test_dot_uses_the_state_colour(self, mock_tk: tuple) -> None:
        _, _, fake_canvases = mock_tk
        ov = self._overlay()
        ov.show_ptt()
        fills = [str(kw.get("fill")).lower() for k, kw in fake_canvases[0].items if k == "oval"]
        assert overlay.STATES["ptt"]["dot"].lower() in fills

    def test_palette_stays_blue_on_black(self) -> None:
        assert overlay.SURFACE.lower() == "#0b1020"
        for key in ("ptt", "toggle", "processing"):
            assert overlay.STATES[key]["dot"].lower().startswith("#3") or \
                   overlay.STATES[key]["dot"].lower().startswith("#6")


class TestBlend:
    def test_blend_endpoints(self) -> None:
        assert overlay._blend("#3B82F6", "#000000", 0.0).lower() == "#3b82f6"
        assert overlay._blend("#3B82F6", "#000000", 1.0).lower() == "#000000"

    def test_blend_midpoint_is_between(self) -> None:
        mid = overlay._blend("#ffffff", "#000000", 0.5)
        assert mid.lower() in ("#808080", "#7f7f7f")
