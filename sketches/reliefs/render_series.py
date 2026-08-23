"""
Render the full series from the local cache, without network access.

No interaction, no per-place tuning: every place is rendered with the same
fixed grammar from `ReliefsSketch`. This is what makes the pieces read as a
family.

    python render_series.py                 # toute la série
    python render_series.py cervin eiger    # selected places

Each file embeds its place, coordinates, dataset, seed and code version in an
XML comment so it can be regenerated years later.
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import vpype as vp

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sketch_reliefs import ReliefsSketch
from terrain import CODE_VERSION, load_places

OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# Au-delà, le tracé dépasse deux heures de plotter à 40 mm/s.
MAX_LENGTH_M = 40.0
PLOTTER_SPEED_MM_S = 40.0


def pen_length_m(document: vp.Document) -> float:
    """Total drawn length in meters, excluding pen-up travel."""
    return document.length() / vp.convert_length("1m")


def provenance(sketch: ReliefsSketch, terrain) -> str:
    """XML provenance comment inserted at the top of each file."""
    params = sketch.params()
    settings = " ".join(
        f"{key}={params[key]}"
        for key in sorted(params)
        if key not in ("width", "height")
    )
    return (
        "\n  Reliefs — "
        f"{terrain.name}\n"
        f"  coordinates : {terrain.lat:.5f}, {terrain.lon:.5f}\n"
        f"  extent      : {terrain.extent_m:.0f} m, grid {terrain.res}\n"
        f"  data        : {terrain.dataset}, fetched {terrain.fetched_at}\n"
        f"  seed        : {terrain.seed}\n"
        f"  code        : v{CODE_VERSION}\n"
        f"  grammar     : {settings}\n"
    )


def write_svg(path: Path, document: vp.Document, comment: str) -> None:
    """Write the SVG with provenance and without timestamp metadata."""
    buffer = io.StringIO()
    vp.write_svg(
        buffer,
        document,
        source_string=f"Reliefs v{CODE_VERSION}",
        color_mode="layer",
        set_date=False,
    )
    svg = buffer.getvalue()

    head, sep, tail = svg.partition("\n")
    if not head.startswith("<?xml"):
        head, sep, tail = "", "", svg
    path.write_text(f"{head}{sep}<!--{comment}-->\n{tail}", encoding="utf-8")


def render(slug: str, output_dir: Path) -> tuple[Path, float]:
    # Force debug off so control layers never leak into a print export.
    ReliefsSketch.set_param_set({"place": slug, "debug": False})
    sketch = ReliefsSketch.execute(finalize=True)
    if sketch is None:
        raise RuntimeError(f"sketch execution failed for '{slug}'")

    from sketch_reliefs import load_terrain

    terrain = load_terrain(slug)
    document = sketch.vsk.document
    path = output_dir / f"reliefs_{slug}_{terrain.seed}.svg"
    write_svg(path, document, provenance(sketch, terrain))
    return path, pen_length_m(document)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("slugs", nargs="*", help="places to render (default: all)")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)

    known = [s["slug"] for s in load_places()]
    slugs = args.slugs or known
    unknown = [s for s in slugs if s not in known]
    if unknown:
        print(f"unknown place(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    lengths: list[tuple[str, float]] = []
    missing: list[str] = []

    for slug in slugs:
        try:
            path, length = render(slug, args.output)
        except FileNotFoundError as exc:
            print(f"{slug:20s} no cache — {exc}".split("\n")[0])
            missing.append(slug)
            continue
        minutes = length * 1000.0 / PLOTTER_SPEED_MM_S / 60.0
        over = "  <-- over limit" if length > MAX_LENGTH_M else ""
        print(f"{slug:20s} {length:6.1f} m  ~{minutes:4.0f} min  {path.name}{over}")
        lengths.append((slug, length))

    if lengths:
        worst = max(lengths, key=lambda kv: kv[1])
        print(
            f"\n{len(lengths)} piece(s). Longest plot: "
            f"{worst[0]} at {worst[1]:.1f} m (limit {MAX_LENGTH_M:.0f} m)."
        )
        if worst[1] > MAX_LENGTH_M:
            print(
                "The series grammar is too dense. Increase `detail` or "
                "`empty_threshold` for every place, not just one."
            )
    if missing:
        print(f"\n{len(missing)} place(s) without cache: {', '.join(missing)}")
        print("Run: python fetch_all.py")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
