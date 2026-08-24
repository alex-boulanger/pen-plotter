from math import sqrt
from pathlib import Path

from PIL import Image, ImageOps
import vsketch


PAGE_WIDTH = 21.0
PAGE_HEIGHT = 29.7
SOURCE_IMAGE = Path(__file__).parent / "data" / "grace_hopper.jpg"
CYAN = 1
MAGENTA = 2
YELLOW = 3
BLACK = 4

CMYK_LAYERS = (CYAN, MAGENTA, YELLOW, BLACK)

class GlyphtoneSketch(vsketch.SketchClass):
    columns = vsketch.Param(42, 8, 100)
    margin = vsketch.Param(1.5, 0.5, 5.0, step=0.1)
    tone_curve = vsketch.Param(1.0, 0.25, 3.0, step=0.05)
    min_ink = vsketch.Param(0.06, 0.0, 0.5, step=0.01)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False, center=False)
        vsk.scale("cm")
        for layer in CMYK_LAYERS:
            vsk.penWidth("0.4mm", layer)
        
        drawing_width = PAGE_WIDTH - 2 * self.margin
        drawing_height = PAGE_HEIGHT - 2 * self.margin

        cell_size = drawing_width / self.columns
        rows = max(1, round(drawing_height / cell_size))

        with Image.open(SOURCE_IMAGE) as source:
            samples = ImageOps.fit(
                source.convert("RGB"),
                (self.columns, rows),
                method=Image.Resampling.LANCZOS,
            )

        grid_height = rows * cell_size
        y_offset = (PAGE_HEIGHT - grid_height) / 2

        for row in range(rows):
            for column in range(self.columns):
                red, green, blue = samples.getpixel((column, row))
                amounts = self.rgb_to_cmyk(red, green, blue)

                for layer, amount in zip(CMYK_LAYERS, amounts):
                    ink = amount**self.tone_curve
                    if ink < self.min_ink:
                        continue

                    vsk.stroke(layer)
                    vsk.fill(layer)
                    x = self.margin + (column + 0.5) * cell_size
                    y = y_offset + (row + 0.5) * cell_size
                    self.draw_glyph(
                        vsk,
                        x=x,
                        y=y,
                        size=cell_size,
                        ink=ink,
                    )
        
        vsk.vpype(
            "color --layer 1 cyan "
            "color --layer 2 magenta "
            "color --layer 3 yellow "
            "color --layer 4 black "
            "alpha --layer 1 0.7 "
            "alpha --layer 2 0.7 "
            "alpha --layer 3 0.7 "
            "alpha --layer 4 0.7"
        )

    def draw_glyph(
        self,
        vsk: vsketch.Vsketch,
        x: float,
        y: float,
        size: float,
        ink: float,
    ) -> None:
        # L'aire du disque est proportionnelle à ink : comme A = pi * r²,
        # le rayon doit évoluer avec la racine carrée du niveau d'encre.
        radius = size * 0.45 * sqrt(ink)
        vsk.circle(x, y, radius=radius)

    def rgb_to_cmyk(self, red: int, green: int, blue: int) -> tuple[float, ...]:
        r = red / 255.0
        g = green / 255.0
        b = blue / 255.0

        key = 1.0 - max(r, g, b)

        if key >= 1.0:
            return 0.0, 0.0, 0.0, 1.0

        cyan = (1.0 - r - key) / (1.0 - key)
        magenta = (1.0 - g - key) / (1.0 - key)
        yellow = (1.0 - b - key) / (1.0 - key)

        return cyan, magenta, yellow, key
    
    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    GlyphtoneSketch.display()
