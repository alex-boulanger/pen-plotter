from functools import cache
from string import ascii_letters, digits, punctuation

import vsketch
import vpype


FONT_CHOICES = (
    "futural",
    "futuram",
    "rowmans",
    "scripts",
    "scriptc",
    "gothiceng",
    "gothicger",
    "gothicita",
)

GLYPH_CHAR_PRESETS = {
    "symbols": " " + punctuation + digits,
    "ascii": " " + punctuation + digits + ascii_letters,
}


@cache
def glyph_template(font: str, glyph: str) -> vpype.LineCollection:
    return vpype.text_line(glyph, font, 1.0, align="center")


@cache
def ranked_glyphs(font: str, glyph_chars: str) -> tuple[str, ...]:
    chars = GLYPH_CHAR_PRESETS[glyph_chars]
    ranked = sorted(
        ((glyph_template(font, char).length(), char) for char in chars),
        key=lambda item: item[0],
    )
    return tuple(char for _, char in ranked)


def glyph_for_ink(ink: float, font: str, glyph_chars: str) -> str:
    glyphs = ranked_glyphs(font, glyph_chars)
    index = round(max(0.0, min(1.0, ink)) * (len(glyphs) - 1))
    return glyphs[index]


def draw_glyph(
    vsk: vsketch.Vsketch,
    *,
    glyph: str,
    font: str,
    x: float,
    y: float,
    size: float,
    angle: float,
) -> None:
    if glyph == " ":
        return

    lines = vpype.LineCollection(glyph_template(font, glyph))
    bounds = lines.bounds()
    if bounds is None:
        return

    min_x, min_y, max_x, max_y = bounds
    lines.translate(
        -(min_x + max_x) / 2,
        -(min_y + max_y) / 2,
    )
    lines.scale(size)
    lines.rotate(angle)
    lines.translate(x, y)

    for line in lines:
        vsk.polygon(line)
