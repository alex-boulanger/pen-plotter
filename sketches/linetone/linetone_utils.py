from pathlib import Path

import numpy as np
from PIL import Image

from shared.image_processing import open_rgb_image


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


def resize_to_samples(
    image: Image.Image,
    *,
    artwork_aspect: float,
    horizontal_samples: int,
    image_fit: str,
) -> Image.Image:
    vertical_samples = max(2, round(horizontal_samples / artwork_aspect))
    sample_size = (horizontal_samples, vertical_samples)

    if image_fit == "cover":
        return crop_to_aspect(image, artwork_aspect).resize(
            sample_size,
            Image.Resampling.LANCZOS,
        )

    if image_fit == "contain":
        image.thumbnail(sample_size, Image.Resampling.LANCZOS)
        samples = Image.new("RGB", sample_size, "white")
        samples.paste(
            image,
            (
                (horizontal_samples - image.width) // 2,
                (vertical_samples - image.height) // 2,
            ),
        )
        return samples

    raise ValueError(f"Unsupported image fit: {image_fit!r}")


def load_cmyk_field(
    path: Path,
    artwork_aspect: float,
    horizontal_samples: int,
    image_fit: str,
    saturation: float,
    red_scale: float,
    green_scale: float,
    blue_scale: float,
) -> np.ndarray:
    """Charge, recadre et convertit l'image en champ CMYK normalisé."""
    resized = resize_to_samples(
        open_rgb_image(
            path,
            saturation=saturation,
            red_scale=red_scale,
            green_scale=green_scale,
            blue_scale=blue_scale,
        ),
        artwork_aspect=artwork_aspect,
        horizontal_samples=horizontal_samples,
        image_fit=image_fit,
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
    return float(top_value * (1.0 - y_fraction) + bottom_value * y_fraction)


def point_segment_distance_sq(
    point_x: float,
    point_y: float,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
) -> float:
    segment_x = end_x - start_x
    segment_y = end_y - start_y
    segment_length_sq = segment_x * segment_x + segment_y * segment_y

    if segment_length_sq == 0.0:
        dx = point_x - start_x
        dy = point_y - start_y
        return dx * dx + dy * dy

    t = (
        (point_x - start_x) * segment_x + (point_y - start_y) * segment_y
    ) / segment_length_sq
    t = max(0.0, min(1.0, t))
    projection_x = start_x + t * segment_x
    projection_y = start_y + t * segment_y
    dx = point_x - projection_x
    dy = point_y - projection_y
    return dx * dx + dy * dy


def simplify_polyline(
    x_values: list[float],
    y_values: list[float],
    tolerance: float,
) -> tuple[list[float], list[float]]:
    """Réduit une polyligne en gardant l'écart max sous tolerance."""
    if tolerance <= 0.0 or len(x_values) <= 2:
        return x_values, y_values

    tolerance_sq = tolerance * tolerance
    keep = {0, len(x_values) - 1}
    stack = [(0, len(x_values) - 1)]

    while stack:
        start, end = stack.pop()
        max_distance_sq = 0.0
        split_index = start

        for index in range(start + 1, end):
            distance_sq = point_segment_distance_sq(
                x_values[index],
                y_values[index],
                x_values[start],
                y_values[start],
                x_values[end],
                y_values[end],
            )
            if distance_sq > max_distance_sq:
                max_distance_sq = distance_sq
                split_index = index

        if max_distance_sq > tolerance_sq:
            keep.add(split_index)
            stack.append((start, split_index))
            stack.append((split_index, end))

    kept_indices = sorted(keep)
    return (
        [x_values[index] for index in kept_indices],
        [y_values[index] for index in kept_indices],
    )
