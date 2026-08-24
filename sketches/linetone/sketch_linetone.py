"""Linetone — une image CMYK traduite en scanlines à boucles.

Chaque couche est parcourue par des lignes horizontales. Dans les zones
encrées, leur trajectoire tourne autour de la ligne de base : faible rayon pour
les tons clairs, boucles plus larges pour les tons denses. Les blancs coupent
le chemin afin de limiter les tracés inutiles.
"""

from math import ceil, cos, sin, tau
from pathlib import Path
import sys

import numpy as np
import vsketch

SKETCH_DIR = Path(__file__).resolve().parent
REPO_ROOT = SKETCH_DIR.parents[1]
if str(SKETCH_DIR) not in sys.path:
    sys.path.insert(0, str(SKETCH_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.images import image_names, image_path

from linetone_utils import load_cmyk_field, sample_field, simplify_polyline


PAGE_WIDTH = 21.0
PAGE_HEIGHT = 29.7
IMAGE_CHOICES = image_names()
DEFAULT_IMAGE = "jungle.jpg" if "jungle.jpg" in IMAGE_CHOICES else IMAGE_CHOICES[0]

CYAN = 1
MAGENTA = 2
YELLOW = 3
BLACK = 4
CMYK_LAYERS = (CYAN, MAGENTA, YELLOW, BLACK)

LAYER_PHASES = {
    CYAN: 0.0,
    MAGENTA: tau / 4,
    YELLOW: tau / 2,
    BLACK: 3 * tau / 4,
}


class LinetoneSketch(vsketch.SketchClass):
    image = vsketch.Param(DEFAULT_IMAGE, choices=IMAGE_CHOICES)
    image_fit = vsketch.Param("cover", choices=("contain", "cover"))
    saturation = vsketch.Param(1.0, 0.0, 3.0, step=0.1)
    red_scale = vsketch.Param(1.0, 0.0, 2.0, step=0.1)
    green_scale = vsketch.Param(1.0, 0.0, 2.0, step=0.1)
    blue_scale = vsketch.Param(1.0, 0.0, 2.0, step=0.1)

    margin = vsketch.Param(1.5, 0.5, 5.0, step=0.1)

    row_pitch = vsketch.Param(0.15, 0.06, 0.8, step=0.01)
    sample_step = vsketch.Param(0.02, 0.005, 0.2, step=0.005)
    wavelength = vsketch.Param(0.18, 0.05, 1.0, step=0.01)
    image_samples = vsketch.Param(240, 40, 600)
    simplify_tolerance = vsketch.Param(0.03, 0.0, 0.08, step=0.005, decimals=3)

    tone_curve = vsketch.Param(1.0, 0.25, 3.0, step=0.05)
    min_ink = vsketch.Param(0.12, 0.0, 0.8, step=0.01)
    black_min_ink = vsketch.Param(0.70, 0.0, 0.9, step=0.01)
    amplitude_ratio = vsketch.Param(0.95, 0.0, 1.5, step=0.05)
    horizontal_loop_ratio = vsketch.Param(1.0, 0.0, 2.0, step=0.1)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False, center=False)
        vsk.scale("cm")
        vsk.noFill()

        for layer in CMYK_LAYERS:
            vsk.penWidth("0.4mm", layer)

        x_min = self.margin
        y_min = self.margin
        x_max = PAGE_WIDTH - self.margin
        y_max = PAGE_HEIGHT - self.margin
        artwork_width = x_max - x_min
        artwork_height = y_max - y_min
        row_count = max(1, int(artwork_height / self.row_pitch))
        used_height = (row_count - 1) * self.row_pitch
        first_row_y = (PAGE_HEIGHT - used_height) / 2

        field = load_cmyk_field(
            image_path(str(self.image)),
            artwork_width / artwork_height,
            self.image_samples,
            str(self.image_fit),
            self.saturation,
            self.red_scale,
            self.green_scale,
            self.blue_scale,
        )

        for channel, layer in enumerate(CMYK_LAYERS):
            vsk.stroke(layer)
            ink_threshold = self.black_min_ink if layer == BLACK else self.min_ink

            for row in range(row_count):
                self.draw_scanline(
                    vsk,
                    field=field,
                    channel=channel,
                    baseline_y=first_row_y + row * self.row_pitch,
                    phase_offset=LAYER_PHASES[layer],
                    ink_threshold=ink_threshold,
                    bounds=(x_min, y_min, x_max, y_max),
                )

        # Ces métadonnées colorent également l'aperçu interactif.
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

    def draw_scanline(
        self,
        vsk: vsketch.Vsketch,
        *,
        field: np.ndarray,
        channel: int,
        baseline_y: float,
        phase_offset: float,
        ink_threshold: float,
        bounds: tuple[float, float, float, float],
    ) -> None:
        """Dessine les segments encrés d'une scanline horizontale."""
        x_min, _, x_max, _ = bounds
        width = x_max - x_min
        point_count = max(2, ceil(width / self.sample_step) + 1)
        actual_step = width / (point_count - 1)
        max_radius = self.row_pitch * self.amplitude_ratio
        x_values: list[float] = []
        y_values: list[float] = []

        for point_index in range(point_count):
            base_x = x_min + point_index * actual_step
            ink = sample_field(field, channel, base_x, baseline_y, bounds)
            ink = ink**self.tone_curve

            if ink < ink_threshold:
                self.flush_path(vsk, x_values, y_values, self.simplify_tolerance)
                x_values = []
                y_values = []
                continue

            # Ramène le rayon à zéro au niveau du seuil afin que les segments
            # commencent et finissent sans saut brutal.
            visible_ink = (ink - ink_threshold) / (1.0 - ink_threshold)
            radius = max_radius * visible_ink
            phase = phase_offset + tau * (base_x - x_min) / self.wavelength
            x_values.append(
                base_x + radius * self.horizontal_loop_ratio * cos(phase)
            )
            y_values.append(baseline_y + radius * sin(phase))

        self.flush_path(vsk, x_values, y_values, self.simplify_tolerance)

    @staticmethod
    def flush_path(
        vsk: vsketch.Vsketch,
        x_values: list[float],
        y_values: list[float],
        tolerance: float,
    ) -> None:
        """Émet uniquement les chemins contenant au moins deux points."""
        x_values, y_values = simplify_polyline(x_values, y_values, tolerance)
        if len(x_values) >= 2:
            vsk.polygon(x_values, y_values)

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    LinetoneSketch.display()
