"""A/B Thumbnail Generator — Pillow-based, cinematic style with shock text overlay."""

import logging
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from config import OUTPUT_DIR

logger = logging.getLogger(__name__)

THUMBNAIL_W = 1280
THUMBNAIL_H = 720

# Tried in order. A Linux-only path used to be the sole candidate, so on the
# Windows target every truetype load failed and the bitmap fallback rendered
# the 120px shock text at roughly 11px — unreadable, and silent about it.
FONT_CANDIDATES = (
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/seguibl.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)

_warned_fallback = False


def _load_font(size: int):
    global _warned_fallback
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    if not _warned_fallback:
        _warned_fallback = True
        logger.warning(
            "No scalable font found — thumbnail text will render at bitmap size. "
            "Tried: %s", ", ".join(FONT_CANDIDATES),
        )
    return ImageFont.load_default()


def _darken_and_vignette(img: Image.Image) -> Image.Image:
    """Apply cinematic dark overlay + vignette."""
    img = img.convert("RGBA")
    img = ImageEnhance.Brightness(img).enhance(0.55)
    img = ImageEnhance.Contrast(img).enhance(1.3)

    # Vignette
    vignette = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(vignette)
    w, h = img.size
    for i in range(min(w, h) // 3):
        alpha = int(200 * (i / (min(w, h) // 3)) ** 2)
        draw.rectangle(
            [i, i, w - i, h - i],
            outline=(0, 0, 0, max(0, 200 - alpha)),
        )
    img = Image.alpha_composite(img, vignette)
    return img.convert("RGB")


def _draw_text_with_stroke(
    draw: ImageDraw.ImageDraw,
    text: str,
    position: tuple[int, int],
    font: ImageFont.FreeTypeFont,
    fill: str | tuple,
    stroke_fill: str | tuple,
    stroke_width: int = 4,
):
    x, y = position
    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=stroke_fill)
    draw.text((x, y), text, font=font, fill=fill)


def _make_thumbnail(
    background_path: Path | None,
    overlay_text: str,
    topic: str,
    out_path: Path,
    variant: str = "A",
) -> Path:
    if background_path and background_path.exists():
        img = Image.open(background_path).convert("RGB")
        img = img.resize((THUMBNAIL_W, THUMBNAIL_H), Image.LANCZOS)
    else:
        color = (20, 10, 40) if variant == "A" else (10, 30, 20)
        img = Image.new("RGB", (THUMBNAIL_W, THUMBNAIL_H), color)

    img = _darken_and_vignette(img)
    draw = ImageDraw.Draw(img)

    # Overlay shock text (top, large, yellow/red)
    shock_font_size = 120 if variant == "A" else 110
    shock_font = _load_font(shock_font_size)
    shock_color = "#FFD700" if variant == "A" else "#FF4444"

    shock_lines = textwrap.wrap(overlay_text.upper(), width=12)
    shock_y = 40
    for line in shock_lines:
        bbox = draw.textbbox((0, 0), line, font=shock_font)
        lw = bbox[2] - bbox[0]
        _draw_text_with_stroke(
            draw,
            line,
            ((THUMBNAIL_W - lw) // 2, shock_y),
            shock_font,
            fill=shock_color,
            stroke_fill=(0, 0, 0),
            stroke_width=6,
        )
        shock_y += shock_font_size + 10

    # Topic subtitle (bottom)
    topic_font = _load_font(42)
    topic_lines = textwrap.wrap(topic, width=40)
    topic_y = THUMBNAIL_H - 40 - len(topic_lines) * 52
    for line in topic_lines:
        bbox = draw.textbbox((0, 0), line, font=topic_font)
        lw = bbox[2] - bbox[0]
        _draw_text_with_stroke(
            draw,
            line,
            ((THUMBNAIL_W - lw) // 2, topic_y),
            topic_font,
            fill="white",
            stroke_fill=(0, 0, 0),
            stroke_width=3,
        )
        topic_y += 52

    img.save(out_path, "JPEG", quality=95)
    logger.info("Thumbnail %s saved: %s", variant, out_path)
    return out_path


class ThumbnailGenerator:
    def __init__(self, topic_slug: str):
        self.slug = topic_slug
        self.out_dir = OUTPUT_DIR / topic_slug / "thumbnails"
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        topic: str,
        overlay_text: str,
        background_a: Path | None = None,
        background_b: Path | None = None,
    ) -> tuple[Path, Path]:
        """Returns (thumbnail_a_path, thumbnail_b_path)."""
        path_a = _make_thumbnail(background_a, overlay_text, topic, self.out_dir / "thumbnail_a.jpg", "A")
        path_b = _make_thumbnail(background_b, overlay_text, topic, self.out_dir / "thumbnail_b.jpg", "B")
        return path_a, path_b
