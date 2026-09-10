"""Reglas del sistema de diseño que se rompieron una vez y no deben repetirse."""

from __future__ import annotations

import pytest

from whisperkey import theme


class TestBordesOptIn:
    """Un borde por defecto en CTkFrame llenaba las ventanas de líneas sueltas.

    Casi todos los frames existen sólo para maquetar y son transparentes; con
    border_width por defecto cada uno dibujaba su propia esquina redondeada, y
    quedaban fragmentos de línea que empezaban y terminaban en cualquier lado.
    """

    def test_los_frames_no_dibujan_borde_por_defecto(self) -> None:
        assert theme.build_theme()["CTkFrame"]["border_width"] == 0

    def test_las_tarjetas_piden_su_borde_explicitamente(self) -> None:
        """Si el default vuelve a 1, este test no alcanza: hay que revisar el uso."""
        import pathlib

        fuente = pathlib.Path(theme.__file__).with_name("settings_gui.py").read_text(
            encoding="utf-8"
        )
        # Las tres superficies con borde propio lo declaran en el sitio de uso.
        assert fuente.count("border_width=1, border_color=theme.BORDER") >= 3


class TestPaleta:
    def test_es_azul_sobre_negro(self) -> None:
        assert theme.BG_BASE.lower() == "#070b14"
        assert theme.ACCENT.lower() == "#2563eb"

    def test_el_tema_declara_todos_los_widgets_usados(self) -> None:
        construido = theme.build_theme()
        for widget in (
            "CTk", "CTkToplevel", "CTkFrame", "CTkButton", "CTkLabel", "CTkEntry",
            "CTkSwitch", "CTkProgressBar", "CTkSlider", "CTkComboBox",
            "CTkScrollbar", "CTkSegmentedButton", "CTkScrollableFrame", "CTkFont",
        ):
            assert widget in construido, f"falta {widget} en el tema"

    def test_el_boton_del_desplegable_se_funde_con_el_campo(self) -> None:
        """Como bloque de otro color quedaba pegado al costado, con canto duro."""
        combo = theme.build_theme()["CTkComboBox"]
        assert combo["button_color"] == combo["fg_color"]

    @pytest.mark.parametrize("nombre", ["BG_BASE", "BG_SURFACE", "BG_ELEVATED", "ACCENT", "TEXT"])
    def test_los_colores_son_hex_validos(self, nombre: str) -> None:
        valor = getattr(theme, nombre)
        assert valor.startswith("#") and len(valor) == 7
        int(valor[1:], 16)


class TestAplicacion:
    def test_apply_es_idempotente(self) -> None:
        pytest.importorskip("customtkinter")
        assert theme.apply() is True
        assert theme.apply() is True

    def test_apply_no_es_fatal_sin_customtkinter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """El diseño no puede impedir que alguien dicte."""
        monkeypatch.setattr(theme, "_applied", False)
        import builtins

        real_import = builtins.__import__

        def sin_ctk(nombre, *args, **kwargs):
            if nombre == "customtkinter":
                raise ImportError("no disponible")
            return real_import(nombre, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", sin_ctk)
        assert theme.apply() is False
