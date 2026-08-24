from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps


def open_rgb_image(
    path: Path,
    *,
    saturation: float,
    red_scale: float,
    green_scale: float,
    blue_scale: float,
) -> Image.Image:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")

    if saturation != 1.0:
        image = ImageEnhance.Color(image).enhance(saturation)

    if (red_scale, green_scale, blue_scale) != (1.0, 1.0, 1.0):
        channels = []
        for channel, scale in zip(
            image.split(),
            (red_scale, green_scale, blue_scale),
        ):
            channels.append(
                channel.point(lambda value: int(max(0, min(255, value * scale))))
            )
        image = Image.merge("RGB", channels)

    return image
