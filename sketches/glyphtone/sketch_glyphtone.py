from math import radians
from pathlib import Path
import sys

import vsketch

SKETCH_DIR = Path(__file__).resolve().parent
REPO_ROOT = SKETCH_DIR.parents[1]
if str(SKETCH_DIR) not in sys.path:
    sys.path.insert(0, str(SKETCH_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.images import image_names, image_path

from glyph_library import (
    FONT_CHOICES,
    GLYPH_CHAR_PRESETS,
    draw_glyph,
    glyph_for_ink,
)
from glyphtone_utils import load_sample_grid, make_grid, rgb_to_cmyk


PAGE_WIDTH = 21.0
PAGE_HEIGHT = 29.7
IMAGE_CHOICES = image_names()
DEFAULT_IMAGE = (
    "jungle.jpg" if "jungle.jpg" in IMAGE_CHOICES else IMAGE_CHOICES[0]
)
CYAN = 1
MAGENTA = 2
YELLOW = 3
BLACK = 4

CMYK_LAYERS = (CYAN, MAGENTA, YELLOW, BLACK)


class GlyphtoneSketch(vsketch.SketchClass):
    image = vsketch.Param(DEFAULT_IMAGE, choices=IMAGE_CHOICES)
    image_fit = vsketch.Param("cover", choices=("contain", "cover"))
    saturation = vsketch.Param(1.0, 0.0, 3.0, step=0.05)
    red_scale = vsketch.Param(1.0, 0.0, 2.0, step=0.05)
    green_scale = vsketch.Param(1.0, 0.0, 2.0, step=0.05)
    blue_scale = vsketch.Param(1.0, 0.0, 2.0, step=0.05)

    font = vsketch.Param("futural", choices=FONT_CHOICES)
    glyph_chars = vsketch.Param("symbols", choices=tuple(GLYPH_CHAR_PRESETS))
    glyph_scale = vsketch.Param(1.0, 0.2, 1.5, step=0.05)
    glyph_rotation = vsketch.Param(25, 0, 45, step=5)
    glyph_random_position = vsketch.Param(0.05, 0.0, 0.3, step=0.01)

    columns = vsketch.Param(70, 8, 100)
    margin = vsketch.Param(1.5, 0.5, 5.0, step=0.1)
    tone_curve = vsketch.Param(1.0, 0.25, 3.0, step=0.05)
    min_ink = vsketch.Param(0.06, 0.0, 0.5, step=0.01)
    black_min_ink = vsketch.Param(0.20, 0.0, 0.9, step=0.01)
    black_ink_scale = vsketch.Param(0.75, 0.0, 1.5, step=0.05)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False, center=False)
        vsk.scale("cm")
        vsk.noFill()

        for layer in CMYK_LAYERS:
            vsk.penWidth("0.4mm", layer)

        grid = make_grid(
            page_width=PAGE_WIDTH,
            page_height=PAGE_HEIGHT,
            margin=float(self.margin),
            columns=int(self.columns),
        )
        samples = load_sample_grid(
            image_path(str(self.image)),
            grid.columns,
            grid.rows,
            str(self.image_fit),
            self.saturation,
            self.red_scale,
            self.green_scale,
            self.blue_scale,
        )

        for row in range(grid.rows):
            for column in range(grid.columns):
                red, green, blue = samples.getpixel((column, row))
                amounts = rgb_to_cmyk(red, green, blue)

                for layer, amount in zip(CMYK_LAYERS, amounts):
                    ink = amount**self.tone_curve
                    ink_threshold = (
                        self.black_min_ink if layer == BLACK else self.min_ink
                    )
                    if ink < ink_threshold:
                        continue
                    if layer == BLACK:
                        ink *= self.black_ink_scale

                    angle = radians(
                        vsk.random(-self.glyph_rotation, self.glyph_rotation)
                    )

                    rnd_x_offset = vsk.random(
                        -self.glyph_random_position,
                        self.glyph_random_position,
                    )
                    rnd_y_offset = vsk.random(
                        -self.glyph_random_position,
                        self.glyph_random_position,
                    )
                    vsk.stroke(layer)
                    draw_glyph(
                        vsk,
                        glyph=glyph_for_ink(
                            ink,
                            str(self.font),
                            str(self.glyph_chars),
                        ),
                        font=str(self.font),
                        x=(
                            grid.x_offset
                            + rnd_x_offset
                            + (column + 0.5) * grid.cell_size
                        ),
                        y=(
                            grid.y_offset
                            + rnd_y_offset
                            + (row + 0.5) * grid.cell_size
                        ),
                        size=grid.cell_size * self.glyph_scale,
                        angle=angle,
                    )

        vsk.vpype(
            "color --layer 1 cyan "
            "color --layer 2 magenta "
            "color --layer 3 yellow "
            "color --layer 4 black "
            "alpha --layer 1 0.6 "
            "alpha --layer 2 0.6 "
            "alpha --layer 3 0.6 "
            "alpha --layer 4 0.6"
        )

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    GlyphtoneSketch.display()
