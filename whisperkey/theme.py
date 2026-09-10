"""Sistema de diseño de WhisperKey: azul sobre negro, sobrio y con aire.

Antes cada ventana elegía sus propios colores a mano —un verde para guardar, un
gris para cancelar, un azul distinto para los títulos—, así que la aplicación se
veía ensamblada en vez de diseñada. Acá vive la paleta única, y `apply()` la
instala como tema de customtkinter para que TODOS los widgets la hereden sin
tener que pintarlos uno por uno.

Reglas del diseño:
  · Un solo acento (azul). El color se reserva para lo accionable.
  · Jerarquía por peso tipográfico y espacio, no por más colores.
  · Bordes finos y superficies apenas separadas del fondo: profundidad sutil.
"""

from __future__ import annotations

import json
import logging
import pathlib
import sys
import tempfile

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Paleta
# ----------------------------------------------------------------------
BG_BASE = "#070B14"       # fondo de ventana, prácticamente negro
BG_SURFACE = "#0B1020"    # paneles y tarjetas (igual que el overlay)
BG_ELEVATED = "#131A2E"   # campos de entrada, filas
BG_HOVER = "#1B2440"

BORDER = "#1E293B"
BORDER_STRONG = "#334155"

ACCENT = "#2563EB"        # azul primario: sólo para lo accionable
ACCENT_HOVER = "#1D4ED8"
ACCENT_SOFT = "#3B82F6"
ACCENT_FAINT = "#1E3A8A"

TEXT = "#E6EDFB"
TEXT_MUTED = "#94A3B8"
TEXT_FAINT = "#64748B"

SUCCESS = "#34D399"
DANGER = "#F87171"
WARNING = "#FBBF24"

# ----------------------------------------------------------------------
# Tipografía y ritmo
# ----------------------------------------------------------------------
FONT_FAMILY = "Segoe UI Variable" if sys.platform == "win32" else "Segoe UI"
FONT_MONO = "Cascadia Mono" if sys.platform == "win32" else "Menlo"

SIZE_DISPLAY = 24
SIZE_TITLE = 18
SIZE_HEADING = 14
SIZE_BODY = 13
SIZE_SMALL = 11

# Escala de espaciado: múltiplos de 4, para que todo caiga en la misma grilla.
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 16
SPACE_LG = 24
SPACE_XL = 32

RADIUS = 10
RADIUS_SM = 6


def font(size: int = SIZE_BODY, weight: str = "normal"):
    """CTkFont de la familia del sistema de diseño."""
    import customtkinter as ctk

    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def _pair(color: str) -> list[str]:
    """customtkinter espera [claro, oscuro]; la app es sólo oscura."""
    return [color, color]


def build_theme() -> dict:
    """Tema completo de customtkinter con la paleta de WhisperKey."""
    return {
        "CTk": {"fg_color": _pair(BG_BASE)},
        "CTkToplevel": {"fg_color": _pair(BG_BASE)},
        # El borde es opt-in: la mayoría de los frames existen sólo para
        # maquetar y son transparentes. Con un borde por defecto cada uno de
        # ellos dibujaba una esquina redondeada suelta, y la ventana se llenaba
        # de líneas que empezaban y terminaban en cualquier lado.
        "CTkFrame": {
            "corner_radius": RADIUS,
            "border_width": 0,
            "fg_color": _pair(BG_SURFACE),
            "top_fg_color": _pair(BG_ELEVATED),
            "border_color": _pair(BORDER),
        },
        "CTkButton": {
            "corner_radius": RADIUS_SM,
            "border_width": 0,
            "fg_color": _pair(ACCENT),
            "hover_color": _pair(ACCENT_HOVER),
            "border_color": _pair(BORDER_STRONG),
            "text_color": _pair("#FFFFFF"),
            "text_color_disabled": _pair(TEXT_FAINT),
        },
        "CTkLabel": {
            "corner_radius": 0,
            "border_width": 0,
            "fg_color": "transparent",
            "border_color": _pair(BORDER),
            "text_color": _pair(TEXT),
        },
        "CTkEntry": {
            "corner_radius": RADIUS_SM,
            "border_width": 1,
            "fg_color": _pair(BG_ELEVATED),
            "border_color": _pair(BORDER),
            "text_color": _pair(TEXT),
            "placeholder_text_color": _pair(TEXT_FAINT),
        },
        "CTkCheckBox": {
            "corner_radius": RADIUS_SM,
            "border_width": 2,
            "fg_color": _pair(ACCENT),
            "border_color": _pair(BORDER_STRONG),
            "hover_color": _pair(ACCENT_HOVER),
            "checkmark_color": _pair("#FFFFFF"),
            "text_color": _pair(TEXT),
            "text_color_disabled": _pair(TEXT_FAINT),
        },
        "CTkSwitch": {
            "corner_radius": 1000,
            "border_width": 0,
            "button_length": 0,
            "fg_color": _pair(BG_HOVER),
            "progress_color": _pair(ACCENT),
            "button_color": _pair(TEXT_MUTED),
            "button_hover_color": _pair(TEXT),
            "text_color": _pair(TEXT),
            "text_color_disabled": _pair(TEXT_FAINT),
        },
        "CTkRadioButton": {
            "corner_radius": 1000,
            "border_width_checked": 6,
            "border_width_unchecked": 2,
            "fg_color": _pair(ACCENT),
            "border_color": _pair(BORDER_STRONG),
            "hover_color": _pair(ACCENT_HOVER),
            "text_color": _pair(TEXT),
            "text_color_disabled": _pair(TEXT_FAINT),
        },
        "CTkProgressBar": {
            "corner_radius": 1000,
            "border_width": 0,
            "fg_color": _pair(BG_ELEVATED),
            "progress_color": _pair(ACCENT),
            "border_color": _pair(BORDER),
        },
        "CTkSlider": {
            "corner_radius": 1000,
            "button_corner_radius": 1000,
            "border_width": 6,
            "button_length": 0,
            "fg_color": _pair(BG_ELEVATED),
            "progress_color": _pair(ACCENT),
            "button_color": _pair(ACCENT_SOFT),
            "button_hover_color": _pair(TEXT),
        },
        "CTkOptionMenu": {
            "corner_radius": RADIUS_SM,
            "fg_color": _pair(BG_ELEVATED),
            "button_color": _pair(BG_HOVER),
            "button_hover_color": _pair(ACCENT),
            "text_color": _pair(TEXT),
            "text_color_disabled": _pair(TEXT_FAINT),
        },
        # El botón del desplegable se funde con el campo: como bloque de otro
        # color quedaba pegado al costado, con un canto duro que no pertenece.
        "CTkComboBox": {
            "corner_radius": RADIUS_SM,
            "border_width": 1,
            "fg_color": _pair(BG_ELEVATED),
            "border_color": _pair(BORDER),
            "button_color": _pair(BG_ELEVATED),
            "button_hover_color": _pair(BG_HOVER),
            "text_color": _pair(TEXT),
            "text_color_disabled": _pair(TEXT_FAINT),
        },
        "CTkScrollbar": {
            "corner_radius": 1000,
            "border_spacing": 4,
            "fg_color": "transparent",
            "button_color": _pair(BORDER_STRONG),
            "button_hover_color": _pair(TEXT_FAINT),
        },
        "CTkSegmentedButton": {
            "corner_radius": RADIUS_SM,
            "border_width": 1,
            "fg_color": _pair(BG_ELEVATED),
            "selected_color": _pair(ACCENT),
            "selected_hover_color": _pair(ACCENT_HOVER),
            "unselected_color": _pair(BG_ELEVATED),
            "unselected_hover_color": _pair(BG_HOVER),
            "text_color": _pair(TEXT),
            "text_color_disabled": _pair(TEXT_FAINT),
        },
        "CTkTextbox": {
            "corner_radius": RADIUS_SM,
            "border_width": 1,
            "fg_color": _pair(BG_ELEVATED),
            "border_color": _pair(BORDER),
            "text_color": _pair(TEXT),
            "scrollbar_button_color": _pair(BORDER_STRONG),
            "scrollbar_button_hover_color": _pair(TEXT_FAINT),
        },
        "CTkScrollableFrame": {"label_fg_color": _pair(BG_SURFACE)},
        "DropdownMenu": {
            "fg_color": _pair(BG_ELEVATED),
            "hover_color": _pair(ACCENT),
            "text_color": _pair(TEXT),
        },
        "CTkFont": {
            "macOS": {"family": "SF Display", "size": SIZE_BODY, "weight": "normal"},
            "Windows": {"family": FONT_FAMILY, "size": SIZE_BODY, "weight": "normal"},
            "Linux": {"family": "Roboto", "size": SIZE_BODY, "weight": "normal"},
        },
    }


_applied = False


def apply() -> bool:
    """Instala el tema en customtkinter. Idempotente y nunca fatal.

    Debe llamarse antes de crear la raíz de Tk. Si algo falla la aplicación
    sigue funcionando con el tema por defecto: el diseño no puede impedir que
    alguien dicte.
    """
    global _applied
    if _applied:
        return True

    try:
        import customtkinter as ctk
    except ImportError:  # pragma: no cover - entorno sin GUI
        return False

    try:
        path = pathlib.Path(tempfile.gettempdir()) / "whisperkey-theme.json"
        path.write_text(json.dumps(build_theme(), indent=1), encoding="utf-8")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme(str(path))
        _applied = True
        return True
    except Exception as exc:  # pragma: no cover - depende de la versión de CTk
        log.warning("No se pudo aplicar el tema de WhisperKey: %s", exc)
        return False
