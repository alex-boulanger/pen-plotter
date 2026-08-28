import math
from pathlib import Path
import sys

import vsketch
from shapely import box as shapely_box

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.isometric3d import (
    Axis,
    Cuboid,
    CuboidFace,
    ErodedHatchedVolume,
    FaceStyle,
    FlowHatchedVolume,
    HatchedPlane,
    HatchedVolume,
    RandomizedHatchedVolume,
    RecursiveHatchedVolume,
    Scene,
    StratifiedVolume,
)


class FadeSketch(vsketch.SketchClass):
    width = vsketch.Param(6.0, min_value=0.5, step=0.25)
    depth = vsketch.Param(4.5, min_value=0.5, step=0.25)
    height = vsketch.Param(9.5, min_value=0.5, step=0.25)
    hatch_spacing = vsketch.Param(0.065, min_value=0.02, step=0.005)
    plane_width = vsketch.Param(6.0, min_value=0.5, step=0.25)
    plane_height = vsketch.Param(9.5, min_value=0.5, step=0.25)
    plane_hatch_spacing = vsketch.Param(0.065, min_value=0.02, step=0.005)
    plane_offset = vsketch.Param(0.0, min_value=0.0, step=0.1)
    translucent_width = vsketch.Param(6.0, min_value=0.5, step=0.25)
    translucent_depth = vsketch.Param(4.5, min_value=0.5, step=0.25)
    translucent_height = vsketch.Param(9.5, min_value=0.5, step=0.25)
    slice_spacing = vsketch.Param(0.16, min_value=0.02, step=0.005)
    volume_style = vsketch.Param(
        "randomized",
        choices=("randomized", "flow", "eroded", "stratified", "recursive"),
    )
    randomized_spacing_jitter = vsketch.Param(
        0.65,
        min_value=0.0,
        max_value=0.95,
        step=0.05,
    )
    cloud_density = vsketch.Param(5, min_value=0, max_value=12, step=1)
    cloud_spread = vsketch.Param(0.78, min_value=0.1, max_value=1.0, step=0.05)
    cloud_length = vsketch.Param(0.72, min_value=0.1, max_value=1.0, step=0.05)
    flow_strength = vsketch.Param(0.18, min_value=0.0, max_value=1.0, step=0.02)
    flow_frequency = vsketch.Param(1.4, min_value=0.1, max_value=6.0, step=0.1)
    erosion = vsketch.Param(0.42, min_value=0.0, max_value=1.0, step=0.02)
    erosion_scale = vsketch.Param(2.4, min_value=0.2, max_value=8.0, step=0.1)
    stratum_count = vsketch.Param(4.0, min_value=0.5, max_value=12.0, step=0.5)
    stratum_contrast = vsketch.Param(0.78, min_value=0.0, max_value=1.0, step=0.05)
    recursion_levels = vsketch.Param(6, min_value=1, max_value=12, step=1)
    recursion_inset_width = vsketch.Param(0.84, min_value=0.4, max_value=0.98)
    recursion_inset_depth = vsketch.Param(0.78, min_value=0.4, max_value=0.98)
    recursion_inset_height = vsketch.Param(0.82, min_value=0.4, max_value=0.98)
    recursion_drift_x = vsketch.Param(0.0, min_value=-0.5, max_value=0.5)
    recursion_drift_y = vsketch.Param(-0.1, min_value=-0.5, max_value=0.5)
    recursion_drift_z = vsketch.Param(-0.18, min_value=-0.5, max_value=0.5)
    recursion_spacing_decay = vsketch.Param(0.88, min_value=0.5, max_value=1.2)
    recursion_jitter = vsketch.Param(0.035, min_value=0.0, max_value=0.2)
    seed = vsketch.Param(12, min_value=0, max_value=9999, step=1)
    projection_scale = vsketch.Param(1.25, min_value=0.25, step=0.05)
    projection_angle = vsketch.Param(20.0, min_value=5.0, max_value=45.0)
    horizontal_offset = vsketch.Param(
        -2.5,
        min_value=-8.0,
        max_value=8.0,
        step=0.25,
    )
    margin = vsketch.Param(1.5, min_value=0.0, step=0.25)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False)
        vsk.scale("cm")

        frame = shapely_box(
            self.margin,
            self.margin,
            vsk.width - self.margin,
            vsk.height - self.margin,
        )
        opaque_form = Cuboid(
            size=(self.width, self.depth, self.height),
            hatch_spacing=self.hatch_spacing,
            layer=1,
            face_styles={CuboidFace.FRONT: FaceStyle.HIDDEN},
        )

        plane_y = -self.depth / 2 - self.plane_offset
        half_plane_width = self.plane_width / 2
        half_plane_height = self.plane_height / 2
        separator_plane = HatchedPlane(
            corners=(
                (-half_plane_width, plane_y, -half_plane_height),
                (half_plane_width, plane_y, -half_plane_height),
                (half_plane_width, plane_y, half_plane_height),
                (-half_plane_width, plane_y, half_plane_height),
            ),
            hatch_spacing=self.plane_hatch_spacing,
            layer=2,
        )
        translucent_center = (0.0, plane_y - self.translucent_depth / 2, 0.0)
        translucent_size = (
            self.translucent_width,
            self.translucent_depth,
            self.translucent_height,
        )
        if self.volume_style == "recursive":
            translucent_forms = [
                HatchedVolume(
                    center=translucent_center,
                    size=translucent_size,
                    hatch_spacing=self.slice_spacing,
                    hatch_axis=Axis.Y,
                    layer=1,
                ),
                RecursiveHatchedVolume(
                    center=translucent_center,
                    size=translucent_size,
                    hatch_spacing=self.slice_spacing,
                    hatch_axis=Axis.Y,
                    levels=self.recursion_levels,
                    inset=(
                        self.recursion_inset_width,
                        self.recursion_inset_depth,
                        self.recursion_inset_height,
                    ),
                    drift=(
                        self.recursion_drift_x,
                        self.recursion_drift_y,
                        self.recursion_drift_z,
                    ),
                    spacing_decay=self.recursion_spacing_decay,
                    jitter=self.recursion_jitter,
                    seed=self.seed,
                    layer=1,
                ),
            ]
        elif self.volume_style == "randomized":
            translucent_forms = [
                RandomizedHatchedVolume(
                    center=translucent_center,
                    size=translucent_size,
                    hatch_spacing=self.slice_spacing,
                    hatch_axis=Axis.Y,
                    spacing_jitter=self.randomized_spacing_jitter,
                    cloud_density=self.cloud_density,
                    cloud_spread=self.cloud_spread,
                    cloud_length=self.cloud_length,
                    seed=self.seed,
                    layer=1,
                )
            ]
        elif self.volume_style == "flow":
            translucent_forms = [
                FlowHatchedVolume(
                    center=translucent_center,
                    size=translucent_size,
                    hatch_spacing=self.slice_spacing,
                    hatch_axis=Axis.Y,
                    flow_strength=self.flow_strength,
                    flow_frequency=self.flow_frequency,
                    seed=self.seed,
                    layer=1,
                )
            ]
        elif self.volume_style == "eroded":
            translucent_forms = [
                ErodedHatchedVolume(
                    center=translucent_center,
                    size=translucent_size,
                    hatch_spacing=self.slice_spacing,
                    hatch_axis=Axis.Y,
                    erosion=self.erosion,
                    erosion_scale=self.erosion_scale,
                    seed=self.seed,
                    layer=1,
                )
            ]
        else:
            translucent_forms = [
                StratifiedVolume(
                    center=translucent_center,
                    size=translucent_size,
                    hatch_spacing=self.slice_spacing,
                    hatch_axis=Axis.Y,
                    band_count=self.stratum_count,
                    density_contrast=self.stratum_contrast,
                    seed=self.seed,
                    layer=1,
                )
            ]
        scene = Scene(
            frame=frame,
            scale=self.projection_scale,
            children=[
                opaque_form,
                *translucent_forms,
                separator_plane,
            ],
            origin=(
                vsk.width / 2 + self.horizontal_offset,
                vsk.height / 2,
            ),
            angle=math.radians(self.projection_angle),
        )
        scene.render(vsk)

        vsk.vpype("color --layer 1 black color --layer 2 red")

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    FadeSketch.display()
