from pathlib import Path


IMAGE_DIR = Path(__file__).resolve().parent / "img"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}


def image_names() -> list[str]:
    """Return shared image filenames usable as vsketch dropdown choices."""
    return sorted(
        path.name
        for path in IMAGE_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def image_path(name: str) -> Path:
    """Resolve a shared image name to a path under shared/img."""
    if Path(name).name != name:
        raise ValueError(f"Invalid shared image name: {name!r}")

    path = IMAGE_DIR / name
    if not path.is_file():
        raise FileNotFoundError(path)

    return path
