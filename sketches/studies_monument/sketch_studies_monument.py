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
    ErodedHatchedVolume,
    FlowHatchedVolume,
    HatchedVolume,
    RandomizedHatchedVolume,
    RecursiveHatchedVolume,
    Renderable,
    Scene,
    StratifiedVolume,
)
from sketches.studies_monument.composition import (
    MARGIN,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    PROJECTION_ANGLE,
    PROJECTION_SCALE,
    VolumeSpec,
    VolumeTreatment,
    plan_composition,
)


class StudiesMonumentSketch(vsketch.SketchClass):
    opaque_flow = vsketch.Param(False)
    opaque_flow_intensity = vsketch.Param(
        0.12,
        min_value=0.0,
        max_value=0.5,
        step=0.01,
    )

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False)
        vsk.scale("cm")

        composition = plan_composition(
            vsk.random_seed,
            opaque_flow=self.opaque_flow,
            opaque_flow_intensity=self.opaque_flow_intensity,
        )
        children = [
            renderable
            for volume in composition.volumes
            for renderable in renderables_for_volume(volume)
        ]
        scene = Scene(
            frame=shapely_box(
                MARGIN,
                MARGIN,
                PAGE_WIDTH - MARGIN,
                PAGE_HEIGHT - MARGIN,
            ),
            scale=PROJECTION_SCALE,
            children=children,
            origin=composition.origin,
            angle=PROJECTION_ANGLE,
        )
        scene.render(vsk)
        _apply_pen_colors(vsk)

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")
        _apply_pen_colors(vsk)


def renderables_for_volume(volume: VolumeSpec) -> list[Renderable]:
    parameters = volume.parameter_map
    hatch_spacing = float(parameters["hatch_spacing"])
    common = {
        "center": volume.center,
        "size": volume.size,
        "hatch_spacing": hatch_spacing,
        "hatch_axis": volume.hatch_axis,
        "layer": volume.layer,
    }

    match volume.treatment:
        case VolumeTreatment.OPAQUE:
            return [
                Cuboid(
                    center=volume.center,
                    size=volume.size,
                    hatch_spacing=hatch_spacing,
                    hatch_angle=_projected_axis_angle(volume.hatch_axis),
                    flow_strength=float(parameters["flow_strength"]),
                    flow_frequency=float(parameters["flow_frequency"]),
                    flow_seed=volume.seed,
                    layer=volume.layer,
                )
            ]
        case VolumeTreatment.RANDOMIZED:
            return [
                RandomizedHatchedVolume(
                    **common,
                    spacing_jitter=float(parameters["spacing_jitter"]),
                    cloud_density=int(parameters["cloud_density"]),
                    cloud_spread=float(parameters["cloud_spread"]),
                    cloud_length=float(parameters["cloud_length"]),
                    seed=volume.seed,
                )
            ]
        case VolumeTreatment.FLOW:
            return [
                FlowHatchedVolume(
                    **common,
                    flow_strength=float(parameters["flow_strength"]),
                    flow_frequency=float(parameters["flow_frequency"]),
                    seed=volume.seed,
                )
            ]
        case VolumeTreatment.ERODED:
            return [
                ErodedHatchedVolume(
                    **common,
                    erosion=float(parameters["erosion"]),
                    erosion_scale=float(parameters["erosion_scale"]),
                    seed=volume.seed,
                )
            ]
        case VolumeTreatment.STRATIFIED:
            return [
                StratifiedVolume(
                    **common,
                    band_count=float(parameters["band_count"]),
                    density_contrast=float(parameters["density_contrast"]),
                    seed=volume.seed,
                )
            ]
        case VolumeTreatment.RECURSIVE:
            return [
                HatchedVolume(**common),
                RecursiveHatchedVolume(
                    **common,
                    levels=int(parameters["levels"]),
                    inset=tuple(parameters["inset"]),
                    drift=tuple(parameters["drift"]),
                    spacing_decay=float(parameters["spacing_decay"]),
                    jitter=float(parameters["jitter"]),
                    seed=volume.seed,
                ),
            ]
        case _:
            raise ValueError(f"unsupported treatment: {volume.treatment}")


def _projected_axis_angle(axis: Axis) -> float:
    match axis:
        case Axis.X:
            return -PROJECTION_ANGLE
        case Axis.Y:
            return PROJECTION_ANGLE
        case Axis.Z:
            return -math.pi / 2.0


def _apply_pen_colors(vsk: vsketch.Vsketch) -> None:
    vsk.vpype("color --layer 1 black color --layer 2 red")


if __name__ == "__main__":
    StudiesMonumentSketch.display()
