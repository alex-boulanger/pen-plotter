"""
Reliefs — one plotter-printed relief portrait per remembered place.

Each piece is a deterministic function of a real place: its topographic data
fully governs the composition. Rendering the same place twice produces the
same file.

The abstraction is maximal. No contour lines, no silhouette, no shading, no
viewpoint. The terrain only provides derived quantities — slope, aspect,
curvature — which drive a closed mark system.

All pieces share this code and this grammar. Only the place changes: the
constants below are the fixed grammar of the series, not per-piece controls.

    vsk run sketches/reliefs              # viewer
    python render_series.py               # full SVG series

The cache must be populated first (`python fetch_all.py`): this file never
touches the network.
"""

import sys
from functools import cache
from pathlib import Path

import numpy as np
import vsketch

# `vsk run` already inserts the sketch folder in sys.path; repeat it here so
# the module can be imported from render_series or a REPL.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import debug
import marks
from terrain import WORK_RES, Terrain, load_places

PAGE_W, PAGE_H = 21.0, 29.7  # A4 portrait, en cm
PEN_WIDTH = "0.3mm"
DEBUG_PEN_WIDTH = "0.1mm"

# The identifying caption is plotted with its own pen pass, independently of
# the two terrain inks. Debug layers start above it (see debug.py).
LAYER_METADATA = 3
METADATA_TEXT_SIZE = 0.32
METADATA_OFFSET = 0.55

PLACE_SLUGS = [s["slug"] for s in load_places()]

# Fixed series grammar. These values define the common language of the pieces;
# they are no longer exposed as viewer sliders.
SERIES_PARAMS = {
    "width": PAGE_W,
    "height": PAGE_H,
    # All lengths are in centimeters, like the drawing coordinates.
    "margin": 2.5,
    # `hatch_min` is the full-black pitch: with a 0.3 mm pen and 0.03 cm pitch,
    # adjacent strokes touch and fill the surface.
    "hatch_min": 0.03,
    "hatch_max": 0.60,
    "angle_steps": 4,
    # Explicit edges for the six marks, as fractions of the slope range above
    # the empty threshold. They form a fixed tonal scale.
    "level_edges": (0.06, 0.16, 0.31, 0.48),
    # A facet is split while its slope remains dispersed.
    "detail": 0.16,
    "min_facet": 0.6,
    "max_cuts": 9,
    "min_cuts": 2,
    "samples": 12,
    # Only organic component: erode the outer contour, modulated by roughness.
    "erosion": 0.25,
    # Control layers: never exported, fixed to keep the viewer readable without
    # turning the print into a tunable object.
    "debug_partition": True,
    "debug_gradient": True,
    "debug_markers": True,
    "debug_step": 0.6,
}


def debug_module_fields() -> list[str]:
    return list(debug.FIELDS)


def metadata_caption(terrain: Terrain) -> str:
    """Human-readable identity carried by every print."""
    lat_hemisphere = "N" if terrain.lat >= 0.0 else "S"
    lon_hemisphere = "E" if terrain.lon >= 0.0 else "W"
    return (
        f"{terrain.name} | GPS {abs(terrain.lat):.5f} {lat_hemisphere}, "
        f"{abs(terrain.lon):.5f} {lon_hemisphere} | altitude {terrain.alt_m:.0f} m"
    )


@cache
def load_terrain(slug: str, res: int = WORK_RES) -> Terrain:
    """Terrain data, computed once per place.

    The viewer calls `draw()` on every slider move. Without this cache, every
    refresh would reload the .npz and recompute all derived fields.
    """
    return Terrain.load(slug, res=res)


class ReliefsSketch(vsketch.SketchClass):
    place = vsketch.Param(PLACE_SLUGS[0], choices=PLACE_SLUGS)

    # The compositional controls stay global to the series: their defaults
    # are also the values used by render_series.py.
    empty_threshold = vsketch.Param(0.4, 0.0, 1.0, step=0.01, decimals=2)
    exposure = vsketch.Param(0.9, 0.0, 1.0, step=0.05, decimals=2)
    cut_spread = vsketch.Param(0.5, 0.0, 1.0, step=0.05, decimals=2)

    # Viewer controls for choosing a place and showing control layers.
    debug = vsketch.Param(False)
    debug_field = vsketch.Param("slope", choices=["none", *debug_module_fields()])

    def params(self) -> dict:
        """Fixed grammar, in the shape expected by `marks.generate()`."""
        return {
            **SERIES_PARAMS,
            "empty_threshold": float(self.empty_threshold),
            "exposure": float(self.exposure),
            "cut_spread": float(self.cut_spread),
            "debug_field": str(self.debug_field),
        }

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False, center=False)
        vsk.scale("cm")
        vsk.penWidth(PEN_WIDTH, marks.LAYER_CONCAVE)
        vsk.penWidth(PEN_WIDTH, marks.LAYER_CONVEX)

        terrain = load_terrain(str(self.place))

        # The seed comes from the place, not from a random draw.
        seed = terrain.seed
        vsk.randomSeed(seed)
        vsk.noiseSeed(seed)
        rng = np.random.default_rng(seed)

        params = self.params()
        facets = marks.plan(terrain, params, rng)
        for layer, geometry in marks.render(facets, params, rng):
            vsk.stroke(layer)
            vsk.geometry(geometry)

        # Keep the identity separate from both terrain inks so it can be
        # plotted, hidden or assigned a pen on its own.
        vsk.penWidth(PEN_WIDTH, LAYER_METADATA)
        vsk.stroke(LAYER_METADATA)
        vsk.text(
            metadata_caption(terrain),
            params["margin"],
            PAGE_H - params["margin"] + METADATA_OFFSET,
            size=METADATA_TEXT_SIZE,
        )

        if self.debug:
            self.draw_debug(vsk, terrain, facets, params)

    def draw_debug(self, vsk: vsketch.Vsketch, terrain, facets, params: dict) -> None:
        """Overlay control layers without changing the print."""
        for layer, geometry in debug.overlay(terrain, facets, params):
            vsk.penWidth(DEBUG_PEN_WIDTH, layer)
            vsk.stroke(layer)
            vsk.geometry(geometry)

        # The caption shares the marker layer and follows its switch.
        if params["debug_markers"]:
            vsk.stroke(debug.LAYER_MARKERS)
            vsk.text(
                debug.caption(terrain, facets),
                params["margin"],
                PAGE_H - params["margin"] * 0.18,
                size=0.28,
            )

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        # No `linemerge`: it would fuse neighboring collinear hatches and erase
        # the texture.
        vsk.vpype("linesimplify linesort")


if __name__ == "__main__":
    ReliefsSketch.display()
