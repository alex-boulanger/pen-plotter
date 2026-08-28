from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from enum import Enum

from shared.isometric3d import Axis, Vector2, Vector3


PAGE_WIDTH = 21.0
PAGE_HEIGHT = 29.7
MARGIN = 1.5
PROJECTION_ANGLE = math.radians(20.0)
PROJECTION_SCALE = 1.15
MAX_OFFSET_X = 0.75
MAX_OFFSET_Y = 1.0

AXES = (Axis.X, Axis.Y, Axis.Z)
AXIS_INDEX = {Axis.X: 0, Axis.Y: 1, Axis.Z: 2}


class VolumeTreatment(Enum):
    OPAQUE = "opaque"
    RANDOMIZED = "randomized"
    FLOW = "flow"
    ERODED = "eroded"
    STRATIFIED = "stratified"
    RECURSIVE = "recursive"


ParameterValue = int | float | Vector3


@dataclass(frozen=True)
class VolumeSpec:
    center: Vector3
    size: Vector3
    primary_axis: Axis
    hatch_axis: Axis
    treatment: VolumeTreatment
    layer: int
    seed: int
    parameters: tuple[tuple[str, ParameterValue], ...]
    parent_index: int | None = None
    attachment_axis: Axis | None = None
    attachment_side: int = 0
    penetration: float = 0.0

    @property
    def parameter_map(self) -> dict[str, ParameterValue]:
        return dict(self.parameters)

    @property
    def volume(self) -> float:
        return self.size[0] * self.size[1] * self.size[2]


@dataclass(frozen=True)
class CompositionSpec:
    seed: int
    volumes: tuple[VolumeSpec, ...]
    origin: Vector2
    fit_scale: float


def plan_composition(
    seed: int,
    opaque_flow: bool = False,
    opaque_flow_intensity: float = 0.12,
) -> CompositionSpec:
    if opaque_flow_intensity < 0:
        raise ValueError("opaque_flow_intensity cannot be negative")

    rng = random.Random(seed)
    shape_count = _shape_count(rng)
    primary_axes = _axis_sequence(rng, shape_count)
    hatch_axes = _axis_sequence(rng, shape_count)
    treatments = _secondary_treatments(rng, shape_count - 1)

    core_size = [rng.uniform(3.0, 5.0) for _ in AXES]
    core_size[AXIS_INDEX[primary_axes[0]]] = rng.uniform(6.5, 9.0)
    core_seed = rng.randrange(2**31)
    generated_flow_frequency = rng.uniform(0.7, 1.8)
    core_flow_strength = opaque_flow_intensity if opaque_flow else 0.0
    core_flow_frequency = generated_flow_frequency if opaque_flow else 1.4
    volumes = [
        VolumeSpec(
            center=(0.0, 0.0, 0.0),
            size=tuple(core_size),
            primary_axis=primary_axes[0],
            hatch_axis=hatch_axes[0],
            treatment=VolumeTreatment.OPAQUE,
            layer=1,
            seed=core_seed,
            parameters=(
                ("hatch_spacing", rng.uniform(0.05, 0.085)),
                ("flow_strength", core_flow_strength),
                ("flow_frequency", core_flow_frequency),
            ),
        )
    ]

    core_length = core_size[AXIS_INDEX[primary_axes[0]]]
    for index in range(1, shape_count):
        primary_axis = primary_axes[index]
        primary_index = AXIS_INDEX[primary_axis]
        child_size = [
            max(1.2, core_size[axis_index] * rng.uniform(0.25, 0.55))
            for axis_index in range(3)
        ]
        child_size[primary_index] = core_length * rng.uniform(0.45, 0.85)

        if index == 1 or rng.random() < 0.7:
            parent_index = 0
        else:
            parent_index = rng.randrange(1, index)
        parent = volumes[parent_index]
        attachment_axis = rng.choice(AXES)
        attachment_index = AXIS_INDEX[attachment_axis]
        attachment_side = rng.choice((-1, 1))
        penetration = (
            0.0
            if rng.random() < 0.6
            else child_size[attachment_index] * rng.uniform(0.1, 0.3)
        )

        child_center = list(parent.center)
        child_center[attachment_index] += attachment_side * (
            parent.size[attachment_index] / 2.0
            + child_size[attachment_index] / 2.0
            - penetration
        )
        for axis_index in range(3):
            if axis_index == attachment_index:
                continue
            inset = max(
                0.0,
                (parent.size[axis_index] - child_size[axis_index]) / 2.0,
            )
            child_center[axis_index] += rng.uniform(-inset, inset)

        treatment = treatments[index - 1]
        volume_seed = rng.randrange(2**31)
        volumes.append(
            VolumeSpec(
                center=tuple(child_center),
                size=tuple(child_size),
                primary_axis=primary_axis,
                hatch_axis=hatch_axes[index],
                treatment=treatment,
                layer=1,
                seed=volume_seed,
                parameters=_treatment_parameters(treatment, rng),
                parent_index=parent_index,
                attachment_axis=attachment_axis,
                attachment_side=attachment_side,
                penetration=penetration,
            )
        )

    red_index = rng.randrange(1, shape_count)
    volumes[red_index] = replace(volumes[red_index], layer=2)
    offset = (
        rng.uniform(-MAX_OFFSET_X, MAX_OFFSET_X),
        rng.uniform(-MAX_OFFSET_Y, MAX_OFFSET_Y),
    )
    fitted_volumes, fit_scale = _fit_to_page(tuple(volumes), offset)
    bounds = projected_bounds(fitted_volumes, (0.0, 0.0))
    origin = (
        PAGE_WIDTH / 2.0 + offset[0] - (bounds[0] + bounds[2]) / 2.0,
        PAGE_HEIGHT / 2.0 + offset[1] - (bounds[1] + bounds[3]) / 2.0,
    )
    return CompositionSpec(seed, fitted_volumes, origin, fit_scale)


def projected_bounds(
    volumes: tuple[VolumeSpec, ...],
    origin: Vector2,
) -> tuple[float, float, float, float]:
    points = [
        _project_point(vertex, origin)
        for volume in volumes
        for vertex in _volume_vertices(volume)
    ]
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def _shape_count(rng: random.Random) -> int:
    draw = rng.random()
    if draw < 0.45:
        return 2
    if draw < 0.8:
        return 3
    if draw < 0.95:
        return 4
    return 5


def _axis_sequence(rng: random.Random, count: int) -> tuple[Axis, ...]:
    sequence: list[Axis] = []
    while len(sequence) < count:
        deck = list(AXES)
        rng.shuffle(deck)
        if sequence and deck[0] == sequence[-1]:
            swap_index = 1 if deck[1] != sequence[-1] else 2
            deck[0], deck[swap_index] = deck[swap_index], deck[0]
        sequence.extend(deck)
    return tuple(sequence[:count])


def _secondary_treatments(
    rng: random.Random,
    count: int,
) -> tuple[VolumeTreatment, ...]:
    palette = [
        VolumeTreatment.RANDOMIZED,
        VolumeTreatment.FLOW,
        VolumeTreatment.ERODED,
        VolumeTreatment.STRATIFIED,
        VolumeTreatment.RECURSIVE,
    ]
    rng.shuffle(palette)
    selected = palette[:count]
    if count == 4 and rng.random() < 0.4:
        selected[-1] = rng.choice(selected[:-1])
    return tuple(selected)


def _treatment_parameters(
    treatment: VolumeTreatment,
    rng: random.Random,
) -> tuple[tuple[str, ParameterValue], ...]:
    parameters: dict[str, ParameterValue] = {
        "hatch_spacing": rng.uniform(0.13, 0.2),
    }
    match treatment:
        case VolumeTreatment.RANDOMIZED:
            parameters.update(
                spacing_jitter=rng.uniform(0.45, 0.8),
                cloud_density=rng.randint(3, 7),
                cloud_spread=rng.uniform(0.6, 0.95),
                cloud_length=rng.uniform(0.5, 0.85),
            )
        case VolumeTreatment.FLOW:
            parameters.update(
                flow_strength=rng.uniform(0.08, 0.3),
                flow_frequency=rng.uniform(0.8, 2.2),
            )
        case VolumeTreatment.ERODED:
            parameters.update(
                erosion=rng.uniform(0.3, 0.55),
                erosion_scale=rng.uniform(1.4, 3.8),
            )
        case VolumeTreatment.STRATIFIED:
            parameters.update(
                band_count=rng.uniform(2.5, 6.5),
                density_contrast=rng.uniform(0.55, 0.9),
            )
        case VolumeTreatment.RECURSIVE:
            parameters.update(
                levels=rng.randint(3, 7),
                inset=tuple(rng.uniform(0.68, 0.9) for _ in AXES),
                drift=tuple(rng.uniform(-0.035, 0.035) for _ in AXES),
                spacing_decay=rng.uniform(0.8, 0.98),
                jitter=rng.uniform(0.01, 0.07),
            )
        case _:
            raise ValueError(f"unsupported secondary treatment: {treatment}")
    return tuple(parameters.items())


def _fit_to_page(
    volumes: tuple[VolumeSpec, ...],
    offset: Vector2,
) -> tuple[tuple[VolumeSpec, ...], float]:
    bounds = projected_bounds(volumes, (0.0, 0.0))
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    usable_width = PAGE_WIDTH - 2.0 * (MARGIN + abs(offset[0]))
    usable_height = PAGE_HEIGHT - 2.0 * (MARGIN + abs(offset[1]))
    fit_scale = min(1.0, usable_width / width, usable_height / height)
    if fit_scale >= 1.0:
        return volumes, 1.0

    return (
        tuple(
            replace(
                volume,
                center=tuple(coordinate * fit_scale for coordinate in volume.center),
                size=tuple(dimension * fit_scale for dimension in volume.size),
                penetration=volume.penetration * fit_scale,
            )
            for volume in volumes
        ),
        fit_scale,
    )


def _volume_vertices(volume: VolumeSpec) -> tuple[Vector3, ...]:
    x, y, z = volume.center
    hx, hy, hz = (dimension / 2.0 for dimension in volume.size)
    return (
        (x - hx, y - hy, z - hz),
        (x + hx, y - hy, z - hz),
        (x + hx, y + hy, z - hz),
        (x - hx, y + hy, z - hz),
        (x - hx, y - hy, z + hz),
        (x + hx, y - hy, z + hz),
        (x + hx, y + hy, z + hz),
        (x - hx, y + hy, z + hz),
    )


def _project_point(point: Vector3, origin: Vector2) -> Vector2:
    x, y, z = point
    return (
        origin[0] + (x - y) * PROJECTION_SCALE * math.cos(PROJECTION_ANGLE),
        origin[1]
        - (x + y) * PROJECTION_SCALE * math.sin(PROJECTION_ANGLE)
        - z * PROJECTION_SCALE,
    )
