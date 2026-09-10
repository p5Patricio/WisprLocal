"""Ventana de configuración de WhisperKey via customtkinter."""

from __future__ import annotations

import logging
import os
import tkinter as tk
from typing import Callable
from PIL import Image

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore[assignment]

from pynput import keyboard as kb

import queue
import threading
import numpy as np
import sounddevice as sd

from whisperkey import theme
from whisperkey import config as config_module
from whisperkey.history import clear, get_entries
from whisperkey.platform import get_platform

log = logging.getLogger(__name__)

_MODEL_OPTIONS_DISPLAY = [
    "Automático (Detección automática)",
    "Tiny (Muy rápido, ~1GB VRAM)",
    "Base (Rápido, ~1GB VRAM)",
    "Small (Recomendado, ~2GB VRAM)",
    "Medium (Preciso, ~5GB VRAM)",
    "Large-v3 (Máxima calidad, ~10GB VRAM)"
]
_MODEL_DISPLAY_TO_CFG = {
    "Automático (Detección automática)": "auto",
    "Tiny (Muy rápido, ~1GB VRAM)": "tiny",
    "Base (Rápido, ~1GB VRAM)": "base",
    "Small (Recomendado, ~2GB VRAM)": "small",
    "Medium (Preciso, ~5GB VRAM)": "medium",
    "Large-v3 (Máxima calidad, ~10GB VRAM)": "large-v3"
}
_MODEL_CFG_TO_DISPLAY = {v: k for k, v in _MODEL_DISPLAY_TO_CFG.items()}

_DEVICE_OPTIONS_DISPLAY = [
    "Automático (Detección automática)",
    "CUDA (GPU NVIDIA - Recomendado)",
    "CPU (Procesador - Lento)",
    "MPS (Apple Silicon macOS)"
]
_DEVICE_DISPLAY_TO_CFG = {
    "Automático (Detección automática)": "auto",
    "CUDA (GPU NVIDIA - Recomendado)": "cuda",
    "CPU (Procesador - Lento)": "cpu",
    "MPS (Apple Silicon macOS)": "mps"
}
_DEVICE_CFG_TO_DISPLAY = {v: k for k, v in _DEVICE_DISPLAY_TO_CFG.items()}

_COMPUTE_OPTIONS_DISPLAY = [
    "float16 (Máxima calidad - GPU potente)",
    "int8_float16 (Balanceado - Recomendado)",
    "int8 (Baja VRAM)",
    "float32 (Solo CPU / Depuración)"
]
_COMPUTE_DISPLAY_TO_CFG = {
    "float16 (Máxima calidad - GPU potente)": "float16",
    "int8_float16 (Balanceado - Recomendado)": "int8_float16",
    "int8 (Baja VRAM)": "int8",
    "float32 (Solo CPU / Depuración)": "float32"
}
_COMPUTE_CFG_TO_DISPLAY = {v: k for k, v in _COMPUTE_DISPLAY_TO_CFG.items()}
_POSITION_OPTIONS = ["bottom-right", "bottom-left", "top-right", "top-left"]


class _KeyCaptureDialog:
    """Diálogo modal que captura la siguiente tecla presionada."""

    def __init__(self, parent: tk.Tk | tk.Toplevel, on_captured: Callable[[str], None]) -> None:
        self._on_captured = on_captured
        self._listener: kb.Listener | None = None

        self._window = tk.Toplevel(parent)
        self._window.title("Capturar tecla")
        self._window.geometry("300x120")
        self._window.resizable(False, False)
        self._window.transient(parent)
        self._window.grab_set()

        tk.Label(self._window, text="Presioná la tecla que querés asignar...", font=("Segoe UI", 12)).pack(pady=10)
        self._status = tk.Label(
            self._window, text="Esperando...",
            font=(theme.FONT_FAMILY, 10, "italic"),
            fg=theme.TEXT_MUTED, bg=theme.BG_BASE,
        )
        self._status.pack(pady=5)

        self._window.protocol("WM_DELETE_WINDOW", self._close)

        self._listener = kb.Listener(on_press=self._on_press)
        self._listener.start()

    def _on_press(self, key) -> None:
        try:
            key_str = key.char
        except AttributeError:
            key_str = str(key).replace("Key.", "")
        self._status.configure(text=f"Capturada: {key_str}")
        self._window.after(200, lambda: self._close(key_str))

    def _close(self, key_str: str | None = None) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._window.destroy()
        if key_str is not None:
            self._on_captured(key_str)


class SettingsGUI:
    """Ventana de configuración con pestañas (Modelo, Audio, Hotkeys, Overlay, Historial, Sistema).

    Si *customtkinter* no está disponible, la ventana no se crea.
    """

    def __init__(self, master: tk.Tk | None = None, config: dict | None = None) -> None:
        if ctk is None:
            log.warning("customtkinter no disponible; settings GUI desactivado")
            return

        self._config = config or config_module.load_config()
        self._master = master
        self._mic_test_thread = None
        self._stop_mic_test_event = threading.Event()

        self._window = ctk.CTkToplevel(master)
        self._window.title("Configuración de WhisperKey")
        self._window.geometry("660x600")
        self._window.resizable(False, False)
        if master is not None:
            self._window.transient(master)

        self._window.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()

        # Registrar callback de progreso de descarga
        try:
            from whisperkey.transcription import CustomProgressBar
            CustomProgressBar.register(self._on_download_progress)
        except ImportError:
            pass

    def _build_ui(self) -> None:
        """Construye la interfaz con tabs y botones."""
        assert ctk is not None

        # Mostrar el logo en la parte superior si existe
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "logo.png")
        has_logo = False
        if os.path.exists(logo_path):
            try:
                pil_image = Image.open(logo_path)
                # Mantener aspect ratio: logo original es 1148x730 (~1.57:1)
                max_width = 60
                aspect_ratio = pil_image.width / pil_image.height
                logo_height = int(max_width / aspect_ratio)
                logo_image = ctk.CTkImage(
                    light_image=pil_image,
                    dark_image=pil_image,
                    size=(max_width, logo_height)
                )
                self._logo_label = ctk.CTkLabel(self._window, text="", image=logo_image)
                self._logo_label.pack(pady=(15, 0))
                has_logo = True
            except Exception as e:
                log.warning("No se pudo cargar el logo en configuración: %s", e)

        if has_logo:
            self._window.geometry("660x640")
            self._tabview = ctk.CTkTabview(self._window, width=620, height=460, command=self._on_tab_change)
        else:
            self._tabview = ctk.CTkTabview(self._window, width=620, height=470, command=self._on_tab_change)
        self._tabview.pack(pady=10, padx=20, fill="both", expand=True)

        self._tabview.add("Modelo")
        self._tabview.add("Audio")
        self._tabview.add("Hotkeys")
        self._tabview.add("Overlay")
        self._tabview.add("Historial")
        self._tabview.add("Sistema")

        self._build_model_tab()
        self._build_audio_tab()
        self._build_hotkeys_tab()
        self._build_overlay_tab()
        self._build_history_tab()
        self._build_system_tab()

        btn_frame = ctk.CTkFrame(self._window, fg_color="transparent")
        btn_frame.pack(pady=10)

        ctk.CTkButton(
            btn_frame, text="Guardar cambios", command=self._on_save, width=150, height=36,
        ).pack(side="left", padx=theme.SPACE_SM)
        # Secundario sin relleno: el color queda reservado a la acción principal.
        ctk.CTkButton(
            btn_frame, text="Cancelar", command=self._on_cancel, width=110, height=36,
            fg_color="transparent", hover_color=theme.BG_HOVER,
            text_color=theme.TEXT_MUTED, border_width=1, border_color=theme.BORDER,
        ).pack(side="left", padx=theme.SPACE_SM)

    # ------------------------------------------------------------------
    # Bloques reutilizables del sistema de diseño
    # ------------------------------------------------------------------

    def _section(self, parent, title: str, description: str = ""):
        """Encabezado de sección: título con peso y bajada apagada.

        La jerarquía la dan el peso y el espacio, no colores distintos.
        """
        assert ctk is not None
        holder = ctk.CTkFrame(parent, fg_color="transparent")
        holder.pack(fill="x", padx=theme.SPACE_LG, pady=(theme.SPACE_LG, theme.SPACE_SM))
        ctk.CTkLabel(
            holder, text=title, anchor="w",
            font=theme.font(theme.SIZE_HEADING, "bold"), text_color=theme.TEXT,
        ).pack(fill="x")
        if description:
            ctk.CTkLabel(
                holder, text=description, anchor="w", justify="left",
                font=theme.font(theme.SIZE_SMALL), text_color=theme.TEXT_MUTED,
            ).pack(fill="x", pady=(theme.SPACE_XS, 0))
        return holder

    def _body(self, tab):
        """Contenedor desplazable para el contenido de una pestaña.

        El alto de una pestaña es fijo y el contenido no: sin esto, el último
        ajuste de Audio y de Hotkeys quedaba cortado fuera de la vista. La barra
        sólo aparece cuando hace falta: dejarla fija dibujaba una línea vertical
        permanente incluso en pestañas que entran enteras.
        """
        assert ctk is not None
        cuerpo = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True)
        self._autohide_scrollbar(cuerpo)
        return cuerpo

    def _autohide_scrollbar(self, cuerpo) -> None:
        """Muestra la barra de desplazamiento sólo si el contenido no entra."""
        barra = getattr(cuerpo, "_scrollbar", None)
        lienzo = getattr(cuerpo, "_parent_canvas", None)
        if barra is None or lienzo is None:  # pragma: no cover - otra versión de CTk
            return

        def revisar(_=None) -> None:
            try:
                region = lienzo.bbox("all")
                if region is None:
                    return
                necesita = (region[3] - region[1]) > lienzo.winfo_height() + 2
                if necesita:
                    barra.grid()
                else:
                    barra.grid_remove()
            except Exception:  # pragma: no cover - widget ya destruido
                pass

        cuerpo.bind("<Configure>", revisar, add="+")
        lienzo.bind("<Configure>", revisar, add="+")
        cuerpo.after(120, revisar)

    def _field(self, parent, label: str, hint: str = ""):
        """Fila de ajuste: etiqueta y pista a la izquierda, control a la derecha.

        El que llama empaqueta su control con side="right" sobre la fila que se
        devuelve. Mantiene el mismo ritmo vertical en todas las pestañas.
        """
        assert ctk is not None
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=theme.SPACE_LG, pady=(0, theme.SPACE_MD))
        textos = ctk.CTkFrame(row, fg_color="transparent")
        textos.pack(side="left", fill="x", expand=True)
        # El texto se recorta antes que el control de la derecha.
        row.pack_propagate(False)
        row.configure(height=46)
        ctk.CTkLabel(
            textos, text=label, anchor="w",
            font=theme.font(theme.SIZE_BODY), text_color=theme.TEXT,
        ).pack(fill="x")
        if hint:
            ctk.CTkLabel(
                textos, text=hint, anchor="w", justify="left",
                font=theme.font(theme.SIZE_SMALL), text_color=theme.TEXT_MUTED,
            ).pack(fill="x")
        return row

    def _status_card(self, parent):
        """Tarjeta de estado: un punto de color y dos líneas de texto."""
        assert ctk is not None
        card = ctk.CTkFrame(
            parent, fg_color=theme.BG_ELEVATED,
            border_width=1, border_color=theme.BORDER,
        )
        card.pack(fill="x", padx=theme.SPACE_LG, pady=theme.SPACE_MD)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=theme.SPACE_MD, pady=theme.SPACE_MD)
        dot = ctk.CTkLabel(inner, text="⬤", font=theme.font(9), width=14)
        dot.pack(side="left", padx=(0, theme.SPACE_SM), anchor="n", pady=(3, 0))
        body = ctk.CTkFrame(inner, fg_color="transparent")
        body.pack(side="left", fill="x", expand=True)
        title = ctk.CTkLabel(
            body, text="", anchor="w", justify="left",
            font=theme.font(theme.SIZE_BODY, "bold"), text_color=theme.TEXT,
        )
        title.pack(fill="x")
        detail = ctk.CTkLabel(
            body, text="", anchor="w", justify="left",
            font=theme.font(theme.SIZE_SMALL), text_color=theme.TEXT_MUTED,
        )
        detail.pack(fill="x")
        return dot, title, detail

    def _update_model_info(self, _=None) -> None:
        model_name = _MODEL_DISPLAY_TO_CFG.get(self._model_combo.get(), "auto")
        device_name, _ = get_platform().detect_gpu()

        temp_config = {
            "model": {
                "name": model_name,
                "device": device_name,
            }
        }

        if model_name == "auto":
            from whisperkey.config import detect_optimal_model
            resolved = detect_optimal_model(temp_config)
            resolved_text = f"Automático (Detectado: {resolved.upper()})"
        else:
            resolved = model_name
            resolved_text = model_name.upper()

        downloaded = config_module.is_model_downloaded(resolved)
        if downloaded:
            status_text = "Descargado y listo para dictar."
            status_color = theme.SUCCESS
        else:
            status_text = "Se descargará la próxima vez que abras la aplicación."
            status_color = theme.WARNING

        # El color vive sólo en el punto; el texto se queda en la paleta base
        # para que la ventana no se llene de colores compitiendo entre sí.
        self._model_dot.configure(text_color=status_color)
        self._model_status_title.configure(text=resolved_text)
        self._model_status_detail.configure(text=status_text)

    def _build_model_tab(self) -> None:
        """Pestaña Modelo: elección del modelo y estado de descarga."""
        assert ctk is not None
        tab = self._tabview.tab("Modelo")
        model_cfg = self._config.get("model", {})
        tab = self._body(tab)

        self._section(
            tab, "Modelo de transcripción",
            "Los modelos grandes entienden mejor el Spanglish y los términos técnicos.\n"
            "Los chicos responden más rápido y ocupan menos memoria.",
        )

        self._model_combo = ctk.CTkComboBox(
            tab, values=_MODEL_OPTIONS_DISPLAY, height=36,
            command=self._update_model_info, font=theme.font(),
        )
        self._model_combo.set(
            _MODEL_CFG_TO_DISPLAY.get(model_cfg.get("name", "auto"), _MODEL_CFG_TO_DISPLAY["auto"])
        )
        self._model_combo.pack(fill="x", padx=theme.SPACE_LG)

        self._model_dot, self._model_status_title, self._model_status_detail = (
            self._status_card(tab)
        )
        self._update_model_info()

        # Esta pestaña usa pack; mezclar grid en el mismo contenedor rompe Tk.
        self._download_progress_lbl = ctk.CTkLabel(
            tab, text="", anchor="w",
            font=theme.font(theme.SIZE_SMALL), text_color=theme.TEXT_MUTED,
        )
        self._download_progress_lbl.pack(fill="x", padx=theme.SPACE_LG)
        self._download_progress_lbl.pack_forget()

        self._download_progress_bar = ctk.CTkProgressBar(tab, height=6)
        self._download_progress_bar.set(0.0)
        self._download_progress_bar.pack(fill="x", padx=theme.SPACE_LG, pady=(theme.SPACE_SM, 0))
        self._download_progress_bar.pack_forget()

    def _build_audio_tab(self) -> None:
        """Pestaña Audio: micrófono, sonidos y parámetros de captura."""
        assert ctk is not None
        tab = self._tabview.tab("Audio")
        audio_cfg = self._config.get("audio", {})
        tab = self._body(tab)

        self._section(
            tab, "Entrada de audio",
            "Elegí el micrófono y comprobá que WhisperKey te esté escuchando.",
        )

        try:
            import sounddevice as sd
            devices = sd.query_devices()
            input_devices = ["Predeterminado del sistema"]
            for dev in devices:
                if dev["max_input_channels"] > 0 and dev["name"] not in input_devices:
                    input_devices.append(dev["name"])
        except Exception:
            input_devices = ["Predeterminado del sistema"]

        self._device_audio_combo = ctk.CTkComboBox(
            tab, values=input_devices, height=34, font=theme.font(theme.SIZE_SMALL)
        )
        current_device = audio_cfg.get("device", "")
        self._device_audio_combo.set(
            current_device if current_device in input_devices else "Predeterminado del sistema"
        )
        self._device_audio_combo.pack(fill="x", padx=theme.SPACE_LG, pady=(0, theme.SPACE_MD))

        prueba = ctk.CTkFrame(tab, fg_color="transparent")
        prueba.pack(fill="x", padx=theme.SPACE_LG, pady=(0, theme.SPACE_MD))
        self._mic_test_btn = ctk.CTkButton(
            prueba, text="Probar micrófono", command=self._toggle_mic_test,
            width=150, height=34,
            fg_color="transparent", hover_color=theme.BG_HOVER,
            text_color=theme.TEXT, border_width=1, border_color=theme.BORDER,
        )
        self._mic_test_btn.pack(side="left")
        self._mic_level_bar = ctk.CTkProgressBar(prueba, height=6)
        self._mic_level_bar.set(0.0)
        self._mic_level_bar.pack(side="right", fill="x", expand=True, padx=(theme.SPACE_MD, 0))

        fila = self._field(
            tab, "Sonidos de notificación",
            "Avisos al empezar, cortar y entregar el dictado.",
        )
        self._sounds_enabled = ctk.CTkSwitch(fila, text="")
        if audio_cfg.get("notification_sounds", True):
            self._sounds_enabled.select()
        self._sounds_enabled.pack(side="right")

        self._section(
            tab, "Captura avanzada",
            "No hace falta tocar esto salvo que tengas problemas de audio.",
        )

        fila = self._field(tab, "Frecuencia de muestreo", "En hercios. Whisper espera 16000.")
        self._sample_rate = ctk.CTkEntry(fila, width=110, height=32, justify="center")
        self._sample_rate.insert(0, str(audio_cfg.get("sample_rate", 16000)))
        self._sample_rate.pack(side="right")

        fila = self._field(tab, "Canales", "1 = mono, recomendado. 2 = estéreo se mezcla a mono.")
        self._channels = ctk.CTkEntry(fila, width=110, height=32, justify="center")
        self._channels.insert(0, str(audio_cfg.get("channels", 1)))
        self._channels.pack(side="right")

        fila = self._field(
            tab, "Tamaño de la cola",
            "Bloques de audio en espera antes de descartar.",
        )
        self._queue_maxsize = ctk.CTkEntry(fila, width=110, height=32, justify="center")
        self._queue_maxsize.insert(0, str(audio_cfg.get("queue_maxsize", 100)))
        self._queue_maxsize.pack(side="right")

    def _build_hotkeys_tab(self) -> None:
        """Pestaña Hotkeys: teclas de dictado, cancelación y modelo."""
        assert ctk is not None
        tab = self._tabview.tab("Hotkeys")
        hotkeys_cfg = self._config.get("hotkeys", {})
        tab = self._body(tab)

        self._section(
            tab, "Teclas de dictado",
            "Push-to-Talk dicta mientras mantenés la tecla. Toggle empieza y "
            "termina con dos pulsaciones.",
        )

        def campo(label: str, hint: str, valor: str):
            fila = self._field(tab, label, hint)
            entry = ctk.CTkEntry(fila, width=140, height=32, justify="center")
            entry.insert(0, valor)
            entry.pack(side="right", padx=(theme.SPACE_SM, 0))
            # width fijo + expand desactivado: el texto de la izquierda cede
            # espacio antes que el control, nunca al revés.
            ctk.CTkButton(
                fila, text="Capturar", width=90, height=32,
                command=lambda e=entry: self._capture_key(e),
                fg_color="transparent", hover_color=theme.BG_HOVER,
                text_color=theme.TEXT_MUTED, border_width=1, border_color=theme.BORDER,
            ).pack(side="right")
            return entry

        self._ptt_entry = campo(
            "Push-to-Talk", "Mantené presionada mientras hablás.",
            hotkeys_cfg.get("ptt", "f9"),
        )
        self._toggle_entry = campo(
            "Toggle", "Una pulsación empieza, otra termina.",
            hotkeys_cfg.get("toggle", "f10"),
        )
        self._cancel_entry = campo(
            "Cancelar dictado",
            "Descarta lo grabado sin transcribir.",
            hotkeys_cfg.get("cancel", "esc"),
        )

        self._section(
            tab, "Avanzado",
            "Dejar vacío para desactivar la tecla.",
        )
        self._load_model_entry = campo(
            "Cargar o liberar el modelo",
            "Libera la memoria del motor sin cerrar la aplicación.",
            hotkeys_cfg.get("load_model_key", ""),
        )

    def _build_overlay_tab(self) -> None:
        """Pestaña Overlay: visibilidad y apariencia del indicador."""
        assert ctk is not None
        tab = self._tabview.tab("Overlay")
        overlay_cfg = self._config.get("overlay", {})
        tab = self._body(tab)

        self._section(
            tab, "Indicador en pantalla",
            "La píldora que muestra si WhisperKey está escuchando o transcribiendo.",
        )

        fila = self._field(
            tab, "Mostrar el indicador",
            "Sin él no hay señal visible de que el dictado está en curso.",
        )
        self._overlay_enabled = ctk.CTkSwitch(fila, text="")
        if overlay_cfg.get("enabled", True):
            self._overlay_enabled.select()
        self._overlay_enabled.pack(side="right")

        fila = self._field(tab, "Posición", "Esquina de la pantalla donde aparece.")
        self._position_combo = ctk.CTkComboBox(
            fila, values=_POSITION_OPTIONS, width=190, height=32,
            font=theme.font(theme.SIZE_SMALL),
        )
        self._position_combo.set(overlay_cfg.get("position", "bottom-right"))
        self._position_combo.pack(side="right")

        fila = self._field(tab, "Opacidad", "Cuánto se transparenta sobre lo que tenés detrás.")
        self._opacity_label = ctk.CTkLabel(
            fila, text="", width=42,
            font=theme.font(theme.SIZE_SMALL), text_color=theme.TEXT_MUTED,
        )
        self._opacity_label.pack(side="right", padx=(theme.SPACE_SM, 0))
        self._opacity_slider = ctk.CTkSlider(fila, from_=0.1, to=1.0, number_of_steps=18, width=180)
        self._opacity_slider.set(overlay_cfg.get("opacity", 0.85))
        self._opacity_slider.pack(side="right")
        self._opacity_label.configure(text=f"{self._opacity_slider.get():.2f}")
        self._opacity_slider.configure(
            command=lambda v: self._opacity_label.configure(text=f"{v:.2f}")
        )

        fila = self._field(tab, "Tamaño de la fuente", "En puntos.")
        self._font_size = ctk.CTkEntry(fila, width=110, height=32, justify="center")
        self._font_size.insert(0, str(overlay_cfg.get("font_size", 14)))
        self._font_size.pack(side="right")

    def _build_history_tab(self) -> None:
        """Pestaña Historial: transcripciones previas, guardadas localmente."""
        assert ctk is not None
        tab = self._tabview.tab("Historial")

        entries = get_entries(limit=100)

        encabezado = self._section(
            tab, "Dictados recientes",
            "Se guardan sólo en tu equipo, nunca salen de acá.",
        )
        ctk.CTkButton(
            encabezado, text="Limpiar", command=self._clear_history, width=90, height=30,
            fg_color="transparent", hover_color=theme.BG_HOVER,
            text_color=theme.TEXT_MUTED, border_width=1, border_color=theme.BORDER,
        ).place(relx=1.0, rely=0.0, anchor="ne")

        lista = ctk.CTkScrollableFrame(
            tab, fg_color=theme.BG_ELEVATED,
            border_width=1, border_color=theme.BORDER,
        )
        lista.pack(padx=theme.SPACE_LG, pady=(0, theme.SPACE_LG), fill="both", expand=True)

        if not entries:
            ctk.CTkLabel(
                lista, text="Todavía no dictaste nada.",
                font=theme.font(theme.SIZE_BODY), text_color=theme.TEXT_MUTED,
            ).pack(pady=theme.SPACE_XL)
            return

        for pos, entry in enumerate(entries):
            ts = entry.get("timestamp", "")[:16].replace("T", "  ")
            texto = entry.get("text", "")
            fila = ctk.CTkFrame(lista, fg_color="transparent")
            fila.pack(fill="x", pady=(0, theme.SPACE_XS))

            # anchor="n": la fecha se alinea con la PRIMERA línea del dictado.
            # Centrada, quedaba flotando a media altura de los textos largos.
            ctk.CTkLabel(
                fila, text=ts, width=110, anchor="nw",
                font=theme.font(theme.SIZE_SMALL), text_color=theme.TEXT_FAINT,
            ).pack(side="left", anchor="n")
            ctk.CTkButton(
                fila, text="Copiar", width=64, height=26,
                command=lambda x=texto: self._copy_to_clipboard(x),
                fg_color="transparent", hover_color=theme.BG_HOVER,
                text_color=theme.TEXT_MUTED, border_width=1, border_color=theme.BORDER,
                font=theme.font(theme.SIZE_SMALL),
            ).pack(side="right", anchor="n", padx=(theme.SPACE_SM, 0))
            ctk.CTkLabel(
                fila, text=texto, anchor="w", justify="left", wraplength=340,
                font=theme.font(theme.SIZE_SMALL), text_color=theme.TEXT,
            ).pack(side="left", fill="x", expand=True)

            if pos < len(entries) - 1:
                sep = ctk.CTkFrame(lista, height=1, fg_color=theme.BORDER)
                sep.pack(fill="x", pady=(0, theme.SPACE_XS))

    def _copy_to_clipboard(self, text: str) -> None:
        try:
            import pyperclip
            pyperclip.copy(text)
        except Exception as exc:
            log.warning("No se pudo copiar al clipboard: %s", exc)

    def _clear_history(self) -> None:
        clear()
        if self._window is not None:
            self._window.destroy()
            SettingsGUI(master=self._master, config=self._config)

    def _build_system_tab(self) -> None:
        """Pestaña Sistema: arranque automático e información de la versión."""
        assert ctk is not None
        tab = self._body(self._tabview.tab("Sistema"))

        platform = get_platform()

        self._section(
            tab, "Arranque",
            "WhisperKey vive en la bandeja del sistema y no consume nada mientras "
            "no dictás.",
        )

        fila = self._field(
            tab, "Iniciar con el sistema",
            "Crea un lanzador en la carpeta de inicio de tu equipo.",
        )
        self._autostart_var = tk.BooleanVar(value=platform.is_autostart_enabled())
        self._autostart_check = ctk.CTkSwitch(
            fila, text="", variable=self._autostart_var, onvalue=True, offvalue=False,
        )
        self._autostart_check.pack(side="right")

        self._section(tab, "Acerca de")

        tarjeta = ctk.CTkFrame(
            tab, fg_color=theme.BG_ELEVATED,
            border_width=1, border_color=theme.BORDER,
        )
        tarjeta.pack(fill="x", padx=theme.SPACE_LG, pady=(0, theme.SPACE_LG))
        interior = ctk.CTkFrame(tarjeta, fg_color="transparent")
        interior.pack(fill="x", padx=theme.SPACE_MD, pady=theme.SPACE_MD)

        from whisperkey.version import __version__ as version

        detalles = [
            ("Versión", version),
            ("Motor", "whisper.cpp (local)"),
            ("Privacidad", "El audio nunca sale de tu equipo"),
        ]
        for etiqueta, valor in detalles:
            linea = ctk.CTkFrame(interior, fg_color="transparent")
            linea.pack(fill="x", pady=1)
            ctk.CTkLabel(
                linea, text=etiqueta, anchor="w", width=90,
                font=theme.font(theme.SIZE_SMALL), text_color=theme.TEXT_MUTED,
            ).pack(side="left")
            ctk.CTkLabel(
                linea, text=valor, anchor="w",
                font=theme.font(theme.SIZE_SMALL), text_color=theme.TEXT,
            ).pack(side="left")

    def _capture_key(self, entry: ctk.CTkEntry) -> None:
        """Abre el diálogo de captura de tecla y escribe el resultado en *entry*."""
        if self._window is None:
            return

        def on_captured(key_str: str) -> None:
            entry.delete(0, "end")
            entry.insert(0, key_str)

        _KeyCaptureDialog(self._window, on_captured)

    def _on_save(self) -> None:
        """Persiste la configuración y muestra aviso de reinicio."""
        assert ctk is not None
        try:
            model_name = _MODEL_DISPLAY_TO_CFG.get(self._model_combo.get(), "auto")
            device_name = self._config.get("model", {}).get("device", "auto")

            selected_audio_device = self._device_audio_combo.get()
            audio_device_val = "" if selected_audio_device == "Predeterminado del sistema" else selected_audio_device

            updated_values = {
                "model": {
                    "name": model_name,
                    "device": device_name,
                },
                "audio": {
                    "sample_rate": int(self._sample_rate.get()),
                    "channels": int(self._channels.get()),
                    "queue_maxsize": int(self._queue_maxsize.get()),
                    "device": audio_device_val,
                    "notification_sounds": bool(self._sounds_enabled.get()),
                },
                "hotkeys": {
                    "ptt": self._ptt_entry.get(),
                    "toggle": self._toggle_entry.get(),
                    "load_model_key": self._load_model_entry.get(),
                    "cancel": self._cancel_entry.get(),
                },
                "overlay": {
                    "enabled": bool(self._overlay_enabled.get()),
                    "position": self._position_combo.get(),
                    "opacity": round(float(self._opacity_slider.get()), 2),
                    "font_size": int(self._font_size.get()),
                },
            }
            new_config = config_module._deep_merge(self._config, updated_values)
            config_module.write_config(config_module.get_config_path(), new_config)
            self._config = new_config


            # Sincronizar estado de sonido inmediatamente
            from whisperkey import sounds
            sounds.set_enabled(bool(self._sounds_enabled.get()))

            # Manejar inicio automático
            platform = get_platform()
            if getattr(self, "_autostart_var", None) is not None:
                if self._autostart_var.get():
                    platform.setup_autostart()
                else:
                    platform.remove_autostart()

            dialog = ctk.CTkToplevel(self._window)
            dialog.title("Configuración guardada")
            dialog.geometry("350x120")
            dialog.resizable(False, False)
            dialog.transient(self._window)
            dialog.grab_set()

            ctk.CTkLabel(dialog, text="Reiniciar para aplicar cambios", font=ctk.CTkFont(size=14)).pack(pady=15)
            ctk.CTkButton(dialog, text="Aceptar", command=dialog.destroy, width=100).pack(pady=5)
        except Exception as exc:
            log.exception("Error al guardar configuración")
            dialog = ctk.CTkToplevel(self._window)
            dialog.title("Error")
            dialog.geometry("350x120")
            dialog.resizable(False, False)
            dialog.transient(self._window)
            dialog.grab_set()
            ctk.CTkLabel(dialog, text=f"Error: {exc}", font=ctk.CTkFont(size=12)).pack(pady=15)
            ctk.CTkButton(dialog, text="Cerrar", command=dialog.destroy, width=100).pack(pady=5)

    def _on_cancel(self) -> None:
        """Cierra la ventana sin guardar."""
        self._on_close()

    def _on_close(self) -> None:
        try:
            from whisperkey.transcription import CustomProgressBar
            CustomProgressBar.unregister(self._on_download_progress)
        except ImportError:
            pass
        self._stop_mic_test()
        if self._window is not None:
            self._window.destroy()

    def _on_tab_change(self) -> None:
        if self._tabview.get() != "Audio":
            self._stop_mic_test()

    def _on_download_progress(self, n: int, total: int, pct: float) -> None:
        if self._window is not None and self._window.winfo_exists():
            self._window.after(0, lambda: self._update_progress_ui(n, total, pct))

    def _update_progress_ui(self, n: int, total: int, pct: float) -> None:
        if self._tabview.get() == "Modelo":
            self._download_progress_lbl.pack(fill="x", padx=theme.SPACE_LG)
            self._download_progress_bar.pack(
                fill="x", padx=theme.SPACE_LG, pady=(theme.SPACE_SM, 0)
            )
            self._download_progress_bar.set(pct / 100.0)
            megas = total / (1024 * 1024) if total else 0
            self._download_progress_lbl.configure(
                text=f"Descargando el modelo… {pct:.0f}% de {megas:.0f} MB"
            )
            if pct >= 100.0:
                self._window.after(2000, self._hide_download_progress)

    def _hide_download_progress(self) -> None:
        if self._window is not None and self._window.winfo_exists():
            self._download_progress_bar.pack_forget()
            self._download_progress_lbl.pack_forget()

    def _toggle_mic_test(self) -> None:
        if self._mic_test_thread is not None and self._mic_test_thread.is_alive():
            self._stop_mic_test()
        else:
            self._start_mic_test()

    def _start_mic_test(self) -> None:
        self._stop_mic_test_event.clear()
        self._mic_test_btn.configure(text="Detener Prueba")
        self._mic_test_thread = threading.Thread(target=self._run_mic_test, daemon=True)
        self._mic_test_thread.start()

    def _stop_mic_test(self) -> None:
        self._stop_mic_test_event.set()
        if self._mic_test_thread is not None:
            self._mic_test_thread = None
        if self._window is not None and self._window.winfo_exists():
            self._mic_test_btn.configure(text="Probar micrófono")
            self._mic_level_bar.set(0.0)

    def _run_mic_test(self) -> None:
        try:
            import time
            duration = 3.0
            samplerate = 16000
            channels = 1
            q = queue.Queue()

            def callback(indata, frames, time_info, status):
                if not self._stop_mic_test_event.is_set():
                    q.put(indata.copy())

            # Resolve selected mic
            selected_mic = self._device_audio_combo.get()
            device_id = None
            if selected_mic != "Predeterminado del sistema":
                try:
                    devices = sd.query_devices()
                    for idx, dev in enumerate(devices):
                        if dev["max_input_channels"] > 0 and selected_mic in dev["name"]:
                            device_id = idx
                            break
                except Exception:
                    pass

            with sd.InputStream(device=device_id, samplerate=samplerate, channels=channels, callback=callback):
                start = time.time()
                while time.time() - start < duration and not self._stop_mic_test_event.is_set():
                    try:
                        data = q.get(timeout=0.1)
                        peak = float(np.max(np.abs(data)))
                        if self._window is not None and self._window.winfo_exists():
                            self._window.after(0, lambda v=peak: self._mic_level_bar.set(min(v, 1.0)))
                    except queue.Empty:
                        continue

            if not self._stop_mic_test_event.is_set():
                if self._window is not None and self._window.winfo_exists():
                    self._window.after(0, self._stop_mic_test)

        except Exception as exc:
            log.warning("Error en test de micrófono de configuración: %s", exc)
            if self._window is not None and self._window.winfo_exists():
                self._window.after(0, self._stop_mic_test)
