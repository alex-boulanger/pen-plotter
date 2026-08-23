"""
Inspect input data outside vsketch.

The cache only contains the raw elevation grid and metadata. Every field used
by the print is recomputed on load.

    python inspect_terrain.py                     # summary for all
    python inspect_terrain.py cervin              # one place
    python inspect_terrain.py cervin --png out/   # one image per field
    python inspect_terrain.py cervin --asc out/   # Esri grids
    python inspect_terrain.py cervin --csv out/   # lat, lon, altitude
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from terrain import (
    Terrain,
    cache_path,
    extent_degrees,
    load_places,
)

SEQUENTIAL = [
    (0.00, (12, 14, 32)),
    (0.30, (60, 50, 120)),
    (0.60, (190, 85, 90)),
    (0.85, (245, 165, 60)),
    (1.00, (255, 248, 220)),
]
DIVERGING = [
    (0.00, (40, 90, 180)),
    (0.50, (248, 248, 248)),
    (1.00, (190, 55, 45)),
]

# Derived fields and color scale type.
FIELDS = {
    "elevation": "sequential",
    "slope": "sequential",
    "roughness": "sequential",
    "curvature": "diverging",
    "aspect": "cyclic",
}


# --- PNG writing, no extra dependency ---------------------------------------


def write_png(path: Path, rgb: np.ndarray) -> None:
    """Write an 8-bit RGB PNG."""
    height, width, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def _ramp(values: np.ndarray, anchors) -> np.ndarray:
    """Applique une échelle de couleurs à des valeurs déjà ramenées à [0, 1]."""
    stops = np.array([a[0] for a in anchors])
    colours = np.array([a[1] for a in anchors], dtype=float)
    out = np.empty((*values.shape, 3))
    for channel in range(3):
        out[..., channel] = np.interp(values, stops, colours[:, channel])
    return out.astype(np.uint8)


def _cyclic(angles: np.ndarray) -> np.ndarray:
    """Roue des teintes — la seule honnête pour une orientation.

    Une échelle linéaire ferait apparaître une fausse discontinuité le long de
    la coupure ±π, là où le terrain est parfaitement continu.
    """
    hue = (angles / (2.0 * np.pi) + 0.5) % 1.0
    sector = hue * 6.0
    index = np.floor(sector).astype(int) % 6
    frac = sector - np.floor(sector)
    p, q, t = 0.15, 1.0 - frac, frac
    table = [
        (np.ones_like(frac), t, np.full_like(frac, p)),
        (q, np.ones_like(frac), np.full_like(frac, p)),
        (np.full_like(frac, p), np.ones_like(frac), t),
        (np.full_like(frac, p), q, np.ones_like(frac)),
        (t, np.full_like(frac, p), np.ones_like(frac)),
        (np.ones_like(frac), np.full_like(frac, p), q),
    ]
    rgb = np.zeros((*angles.shape, 3))
    for i, (r, g, b) in enumerate(table):
        mask = index == i
        rgb[mask] = np.stack([r, g, b], axis=-1)[mask]
    return (rgb * 255).astype(np.uint8)


def colourise(terrain: Terrain, name: str) -> np.ndarray:
    """A derived field as an image, north up."""
    field = getattr(terrain, name)
    kind = FIELDS[name]
    if kind == "cyclic":
        rgb = _cyclic(field)
    elif kind == "diverging":
        rgb = _ramp((field + 1.0) / 2.0, DIVERGING)
    else:
        rgb = _ramp(np.clip(field, 0.0, 1.0), SEQUENTIAL)
    # La ligne 0 est au sud : on retourne pour regarder la carte à l'endroit.
    return rgb[::-1]


def hypsometry_image(terrain: Terrain, size: int = 256) -> np.ndarray:
    """L'histogramme d'altitude, en barres horizontales, les hautes en haut."""
    image = np.full((size, size, 3), 245, dtype=np.uint8)
    counts = np.asarray(terrain.hypsometry, dtype=float)
    peak = counts.max()
    if peak <= 0.0:
        return image
    band = size / len(counts)
    for i, value in enumerate(counts):
        top = int(round(size - (i + 1) * band))
        bottom = int(round(size - i * band))
        width = int(round((size - 4) * value / peak))
        image[top + 1 : bottom - 1, 2 : 2 + width] = (60, 50, 120)
    return image


def contact_sheet(terrain: Terrain, gap: int = 6) -> tuple[np.ndarray, list[str]]:
    """All fields side by side, plus raw altitude for scale."""
    res = terrain.res

    # L'altitude brute, agrandie au plus proche voisin : on voit alors la
    # vraie finesse de la donnée, que le rééchantillonnage masque. On passe
    # par une table d'indices plutôt que par `repeat` : le rapport 256/48
    # n'est pas entier, et `repeat` rendrait une image trop petite.
    coarse = np.load(cache_path(terrain.slug), allow_pickle=False)["elevation"]
    index = np.minimum(np.arange(res) * coarse.shape[0] // res, coarse.shape[0] - 1)
    coarse = coarse[np.ix_(index, index)]
    span = np.ptp(coarse)
    coarse_rgb = _ramp((coarse - coarse.min()) / (span if span else 1.0), SEQUENTIAL)[::-1]

    tiles = [("raw altitude 48x48", coarse_rgb)]
    tiles += [(name, colourise(terrain, name)) for name in FIELDS]
    tiles.append(("hypsometry", hypsometry_image(terrain, res)))

    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    sheet = np.full(
        (rows * res + (rows + 1) * gap, cols * res + (cols + 1) * gap, 3), 255, np.uint8
    )
    for i, (_, tile) in enumerate(tiles):
        y = gap + (i // cols) * (res + gap)
        x = gap + (i % cols) * (res + gap)
        sheet[y : y + res, x : x + res] = tile
    return sheet, [name for name, _ in tiles]


# --- GIS exports ------------------------------------------------------------


def write_asc(path: Path, grid: np.ndarray, cellsize: float) -> None:
    """Grille Esri ASCII, dans un repère métrique local.

    On n'écrit pas de degrés : la grille est carrée en mètres, donc *pas*
    carrée en degrés, et le format Esri impose une cellule carrée. Un export
    en degrés serait écrasé d'un tiers aux latitudes alpines. Pour de vraies
    coordonnées, utiliser `--csv`.
    """
    header = (
        f"ncols {grid.shape[1]}\n"
        f"nrows {grid.shape[0]}\n"
        f"xllcorner 0\n"
        f"yllcorner 0\n"
        f"cellsize {cellsize:.6f}\n"
        f"NODATA_value -9999\n"
    )
    body = "\n".join(
        " ".join(f"{v:.4f}" for v in row) for row in np.nan_to_num(grid[::-1], nan=-9999.0)
    )
    path.write_text(header + body + "\n", encoding="ascii")


def write_csv(path: Path, terrain: Terrain) -> None:
    """Raw grid in lat, lon, altitude: real coordinates."""
    grid = np.load(cache_path(terrain.slug), allow_pickle=False)["elevation"]
    n = grid.shape[0]
    dlat, dlon = extent_degrees(terrain.lat, terrain.extent_m)
    lats = np.linspace(terrain.lat - dlat / 2, terrain.lat + dlat / 2, n)
    lons = np.linspace(terrain.lon - dlon / 2, terrain.lon + dlon / 2, n)
    rows = ["lat,lon,elevation_m"]
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            rows.append(f"{lat:.6f},{lon:.6f},{grid[i, j]:.1f}")
    path.write_text("\n".join(rows) + "\n", encoding="ascii")


# --- Numeric summary --------------------------------------------------------


def summarise(terrain: Terrain) -> None:
    raw = np.load(cache_path(terrain.slug), allow_pickle=False)["elevation"]
    missing = int(np.isnan(raw).sum())
    print(f"\n{terrain.name}  ({terrain.slug})")
    print(f"  {terrain.lat:.5f}, {terrain.lon:.5f} | {terrain.dataset} | {terrain.fetched_at}")
    print(
        f"  extent {terrain.extent_m:.0f} m | raw grid {raw.shape[0]}x{raw.shape[1]}"
        f" ({terrain.extent_m / (raw.shape[0] - 1):.0f} m/point)"
        f" -> work grid {terrain.res}x{terrain.res} ({terrain.step_m:.1f} m/point)"
    )
    print(f"  altitudes {np.nanmin(raw):.0f}-{np.nanmax(raw):.0f} m | missing {missing}")
    print(f"  seed {terrain.seed}")
    print(f"  {'field':11s} {'min':>8} {'median':>8} {'max':>8}   (normalized)")
    for name in FIELDS:
        f = getattr(terrain, name)
        print(f"  {name:11s} {f.min():8.3f} {np.median(f):8.3f} {f.max():8.3f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("slugs", nargs="*", help="places (default: all)")
    parser.add_argument("--png", type=Path, metavar="DIR", help="one image per field")
    parser.add_argument("--asc", type=Path, metavar="DIR", help="Esri ASCII grids")
    parser.add_argument("--csv", type=Path, metavar="DIR", help="lat, lon, altitude")
    args = parser.parse_args(argv)

    known = [s["slug"] for s in load_places()]
    slugs = args.slugs or known
    unknown = [s for s in slugs if s not in known]
    if unknown:
        print(f"unknown place(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    for slug in slugs:
        try:
            terrain = Terrain.load(slug)
        except FileNotFoundError as exc:
            print(f"{slug} : {str(exc).splitlines()[0]}", file=sys.stderr)
            continue
        summarise(terrain)

        if args.png:
            args.png.mkdir(parents=True, exist_ok=True)
            for name in FIELDS:
                write_png(args.png / f"{slug}_{name}.png", colourise(terrain, name))
            sheet, order = contact_sheet(terrain)
            write_png(args.png / f"{slug}_sheet.png", sheet)
            print(f"  -> {len(FIELDS) + 1} images in {args.png}/")
            print(f"     sheet, left to right: {', '.join(order)}")

        if args.asc:
            args.asc.mkdir(parents=True, exist_ok=True)
            write_asc(args.asc / f"{slug}_elevation.asc", terrain.elevation_m, terrain.step_m)
            for name in ("slope", "curvature", "roughness"):
                write_asc(
                    args.asc / f"{slug}_{name}.asc", getattr(terrain, name), terrain.step_m
                )
            print(f"  -> 4 grilles .asc dans {args.asc}/ (repère métrique local)")

        if args.csv:
            args.csv.mkdir(parents=True, exist_ok=True)
            write_csv(args.csv / f"{slug}.csv", terrain)
            print(f"  -> {args.csv}/{slug}.csv (lat, lon, altitude)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
