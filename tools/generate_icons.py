"""Genera íconos de marca para WisprLocal usando Pillow."""

from __future__ import annotations

import logging
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw

log = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "assets" / "icons"

# Paleta de colores para los estados del tray
colors = {
    "idle": "#718096",
    "loading": "#D69E2E",
    "ready": "#38A169",
    "error": "#E53E3E",
}


def _draw_microphone(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int) -> None:
    """Dibuja una silueta de micrófono centrada en (cx, cy) con escala *size*."""
    s = size / 64.0

    # Cabeza del micrófono (óvalo)
    head_w = int(20 * s)
    head_h = int(24 * s)
    head_top = cy - int(12 * s)
    draw.ellipse(
        [cx - head_w // 2, head_top, cx + head_w // 2, head_top + head_h],
        fill="white",
    )

    # Cuello del micrófono (trapecio)
    neck_top = head_top + head_h
    neck_h = int(6 * s)
    draw.polygon(
        [
            (cx - head_w // 2, neck_top),
            (cx + head_w // 2, neck_top),
            (cx + int(8 * s), neck_top + neck_h),
            (cx - int(8 * s), neck_top + neck_h),
        ],
        fill="white",
    )

    # Base / pie (rectángulo + línea)
    base_y = neck_top + neck_h
    base_h = int(4 * s)
    draw.rectangle(
        [cx - int(8 * s), base_y, cx + int(8 * s), base_y + base_h],
        fill="white",
    )

    # Pie
    draw.rectangle(
        [cx - int(12 * s), base_y + base_h, cx + int(12 * s), base_y + base_h + int(3 * s)],
        fill="white",
    )


def _create_tray_icon(size: int, color: str) -> Image.Image:
    """Crea un ícono de bandeja con fondo circular del color dado."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fondo circular
    draw.ellipse([0, 0, size - 1, size - 1], fill=color)

    # Microphone silhouette
    _draw_microphone(draw, size // 2, size // 2, size)
    return img


def _create_app_icon(size: int, bg: tuple[int, int, int, int] = (30, 30, 30, 255)) -> Image.Image:
    """Crea el ícono de aplicación con fondo cuadrado redondeado."""
    img = Image.new("RGBA", (size, size), bg)
    draw = ImageDraw.Draw(img)

    # Fondo redondeado
    radius = size // 8
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=(45, 55, 72, 255))

    # Microphone
    _draw_microphone(draw, size // 2, size // 2, size)
    return img


def _write_icns(images: dict[int, Image.Image], path: Path) -> None:
    """Escribe un archivo .icns con entradas PNG embebidas (macOS)."""
    # Type codes para tamaños PNG en ICNS
    type_map = {
        16: b"icp4",
        32: b"icp5",
        64: b"icp6",
        128: b"ic07",
        256: b"ic08",
        512: b"ic09",
        1024: b"ic10",
    }

    entries = []
    total_size = 8  # header size

    for size, img in images.items():
        if size not in type_map:
            continue
        data = img.tobytes("png")
        type_code = type_map[size]
        entry_size = 8 + len(data)
        entries.append(struct.pack(">4sI", type_code, entry_size) + data)
        total_size += entry_size

    if not entries:
        return

    header = struct.pack(">4sI", b"icns", total_size)
    path.write_bytes(header + b"".join(entries))


def generate_all() -> None:
    """Genera todos los íconos necesarios."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Íconos de bandeja (64x64)
    for name, color in colors.items():
        img = _create_tray_icon(64, color)
        img.save(OUTPUT_DIR / f"tray_{name}.png")
        log.info("Generado tray_%s.png", name)

    # Ícono de aplicación .ico (multi-tamaño)
    ico_sizes = [16, 32, 48, 64, 128, 256]
    ico_images = [_create_app_icon(s) for s in ico_sizes]
    ico_path = OUTPUT_DIR / "app.ico"
    ico_images[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in ico_sizes],
        append_images=ico_images[1:],
    )
    log.info("Generado app.ico (%s tamaños)", len(ico_sizes))

    # Ícono de aplicación .icns (macOS)
    icns_sizes = {s: _create_app_icon(s) for s in [16, 32, 64, 128, 256, 512, 1024]}
    _write_icns(icns_sizes, OUTPUT_DIR / "app.icns")
    log.info("Generado app.icns")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    generate_all()


if __name__ == "__main__":
    main()
