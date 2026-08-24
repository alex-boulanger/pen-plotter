from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from shared.image_processing import open_rgb_image


@dataclass(frozen=True)
class Grid:
    columns: int
    rows: int
    cell_size: float
    x_offset: float
    y_offset: float


def make_grid(
    *,
    page_width: float,
    page_height: float,
    margin: float,
    columns: int,
) -> Grid:
    drawing_width = page_width - 2 * margin
    drawing_height = page_height - 2 * margin
    cell_size = drawing_width / columns
    rows = max(1, round(drawing_height / cell_size))
    grid_height = rows * cell_size

    return Grid(
        columns=columns,
        rows=rows,
        cell_size=cell_size,
        x_offset=margin,
        y_offset=(page_height - grid_height) / 2,
    )


def load_sample_grid(
    path: Path,
    columns: int,
    rows: int,
    image_fit: str,
    saturation: float,
    red_scale: float,
    green_scale: float,
    blue_scale: float,
) -> Image.Image:
    image = open_rgb_image(
        path,
        saturation=saturation,
        red_scale=red_scale,
        green_scale=green_scale,
        blue_scale=blue_scale,
    )

    if image_fit == "cover":
        return ImageOps.fit(
            image,
            (columns, rows),
            method=Image.Resampling.LANCZOS,
        )

    if image_fit == "contain":
        image.thumbnail((columns, rows), Image.Resampling.LANCZOS)
        samples = Image.new("RGB", (columns, rows), "white")
        samples.paste(
            image,
            ((columns - image.width) // 2, (rows - image.height) // 2),
        )
        return samples

    raise ValueError(f"Unsupported image fit: {image_fit!r}")


def rgb_to_cmyk(red: int, green: int, blue: int) -> tuple[float, ...]:
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
