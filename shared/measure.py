from __future__ import annotations

import argparse
from pathlib import Path

import vpype
from vpype.io import read_multilayer_svg


DEFAULT_QUANTIZATION = "0.1mm"


def to_meters(length: float) -> float:
    return length / vpype.UNITS["m"]


def layer_pen_up_length(layer: vpype.LineCollection) -> float:
    pen_up = layer.pen_up_length()
    return pen_up[0] if isinstance(pen_up, tuple) else pen_up


def print_svg_length(svg_path: Path, quantization: str) -> None:
    document = read_multilayer_svg(
        str(svg_path),
        quantization=vpype.convert_length(quantization),
        crop=True,
    )

    print(f"{svg_path}")
    print("Layer  Drawn (m)  Pen-up (m)  Paths  Segments")
    print("-----  ---------  ----------  -----  --------")

    for layer_id, layer in sorted(document.layers.items()):
        print(
            f"{layer_id:>5}  "
            f"{to_meters(layer.length()):>9.2f}  "
            f"{to_meters(layer_pen_up_length(layer)):>10.2f}  "
            f"{len(layer):>5}  "
            f"{layer.segment_count():>8}"
        )

    print("-----  ---------  ----------  -----  --------")
    print(
        f"Total  "
        f"{to_meters(document.length()):>9.2f}  "
        f"{to_meters(document.pen_up_length()):>10.2f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure drawn SVG path length in meters."
    )
    parser.add_argument("svg", type=Path, help="SVG file to measure")
    parser.add_argument(
        "-q",
        "--quantization",
        default=DEFAULT_QUANTIZATION,
        help=f"Curve flattening precision, as a vpype length (default: {DEFAULT_QUANTIZATION})",
    )
    args = parser.parse_args()

    print_svg_length(args.svg, args.quantization)


if __name__ == "__main__":
    main()
