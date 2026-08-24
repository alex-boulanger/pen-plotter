"""Linetone — une image CMYK traduite en scanlines à boucles.

Chaque couche est parcourue par des lignes horizontales. Dans les zones
encrées, leur trajectoire tourne autour de la ligne de base : faible rayon pour
les tons clairs, boucles plus larges pour les tons denses. Les blancs coupent
le chemin afin de limiter les tracés inutiles.
"""

from math import ceil, cos, sin, tau
from pathlib import Path

import numpy as np
from PIL import Image
import vsketch


PAGE_WIDTH = 21.0
PAGE_HEIGHT = 29.7
SOURCE_IMAGE = (
    Path(__file__).parent.parent / "glyphtone" / "data" / "grace_hopper.jpg"
)

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


def crop_to_aspect(image: Image.Image, target_aspect: float) -> Image.Image:
    """Centre-crop une image selon un ratio largeur/hauteur physique."""
    width, height = image.size
    source_aspect = width / height

    if source_aspect > target_aspect:
        crop_width = round(height * target_aspect)
        left = (width - crop_width) // 2
        return image.crop((left, 0, left + crop_width, height))

    crop_height = round(width / target_aspect)
    top = (height - crop_height) // 2
    return image.crop((0, top, width, top + crop_height))


def load_cmyk_field(
    path: Path,
    artwork_aspect: float,
    horizontal_samples: int,
) -> np.ndarray:
    """Charge, recadre et convertit l'image en champ CMYK normalisé."""
    with Image.open(path) as source:
        cropped = crop_to_aspect(source.convert("RGB"), artwork_aspect)
        vertical_samples = max(2, round(horizontal_samples / artwork_aspect))
        resized = cropped.resize(
            (horizontal_samples, vertical_samples),
            Image.Resampling.LANCZOS,
        )
        rgb = np.asarray(resized, dtype=float) / 255.0

    key = 1.0 - np.max(rgb, axis=2)
    remaining = 1.0 - key
    cmy = np.zeros_like(rgb)
    np.divide(
        1.0 - rgb - key[:, :, np.newaxis],
        remaining[:, :, np.newaxis],
        out=cmy,
        where=remaining[:, :, np.newaxis] > 0,
    )
    return np.clip(np.dstack((cmy, key)), 0.0, 1.0)


class LinetoneSketch(vsketch.SketchClass):
    margin = vsketch.Param(1.5, 0.5, 5.0, step=0.1)

    row_pitch = vsketch.Param(0.15, 0.06, 0.8, step=0.01)
    sample_step = vsketch.Param(0.02, 0.005, 0.2, step=0.005)
    wavelength = vsketch.Param(0.18, 0.05, 1.0, step=0.01)
    image_samples = vsketch.Param(240, 40, 600)

    tone_curve = vsketch.Param(1.0, 0.25, 3.0, step=0.05)
    min_ink = vsketch.Param(0.12, 0.0, 0.8, step=0.01)
    black_min_ink = vsketch.Param(0.35, 0.0, 0.9, step=0.01)
    amplitude_ratio = vsketch.Param(0.55, 0.0, 1.5, step=0.05)
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
            SOURCE_IMAGE,
            artwork_width / artwork_height,
            self.image_samples,
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
            ink = self.sample_field(field, channel, base_x, baseline_y, bounds)
            ink = ink**self.tone_curve

            if ink < ink_threshold:
                self.flush_path(vsk, x_values, y_values)
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

        self.flush_path(vsk, x_values, y_values)

    @staticmethod
    def flush_path(
        vsk: vsketch.Vsketch,
        x_values: list[float],
        y_values: list[float],
    ) -> None:
        """Émet uniquement les chemins contenant au moins deux points."""
        if len(x_values) >= 2:
            vsk.polygon(x_values, y_values)

    @staticmethod
    def sample_field(
        field: np.ndarray,
        channel: int,
        x: float,
        y: float,
        bounds: tuple[float, float, float, float],
    ) -> float:
        """Échantillonne le champ CMYK par interpolation bilinéaire."""
        x_min, y_min, x_max, y_max = bounds
        if x < x_min or x > x_max or y < y_min or y > y_max:
            return 0.0

        height, width, _ = field.shape
        image_x = (x - x_min) / (x_max - x_min) * (width - 1)
        image_y = (y - y_min) / (y_max - y_min) * (height - 1)
        left = int(image_x)
        top = int(image_y)
        right = min(left + 1, width - 1)
        bottom = min(top + 1, height - 1)
        x_fraction = image_x - left
        y_fraction = image_y - top

        top_value = (
            field[top, left, channel] * (1.0 - x_fraction)
            + field[top, right, channel] * x_fraction
        )
        bottom_value = (
            field[bottom, left, channel] * (1.0 - x_fraction)
            + field[bottom, right, channel] * x_fraction
        )
        return float(
            top_value * (1.0 - y_fraction) + bottom_value * y_fraction
        )

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linesimplify linesort")


if __name__ == "__main__":
    LinetoneSketch.display()
