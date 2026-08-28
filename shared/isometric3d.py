from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Protocol

import shapely
from shapely.geometry import LineString, MultiLineString, MultiPoint, Polygon


Vector2 = tuple[float, float]
Vector3 = tuple[float, float, float]


class Axis(Enum):
    X = "x"
    Y = "y"
    Z = "z"


class CuboidFace(Enum):
    BOTTOM = "bottom"
    TOP = "top"
    FRONT = "front"
    RIGHT = "right"
    BACK = "back"
    LEFT = "left"


class FaceStyle(Enum):
    HATCHED = "hatched"
    OUTLINE = "outline"
    HIDDEN = "hidden"


@dataclass(frozen=True)
class Rotation:
    axis: Axis
    angle: float
    origin: Vector3 = (0.0, 0.0, 0.0)


@dataclass
class RenderableGeometry:
    geometry: shapely.Geometry
    layer: int = 1


@dataclass
class RenderContext:
    frame: Polygon
    scale: float
    angle: float = math.radians(30)
    origin: Vector2 | str = "centroid"

    @property
    def resolved_origin(self) -> Vector2:
        if self.origin == "centroid":
            centroid = self.frame.centroid
            return (centroid.x, centroid.y)

        return self.origin


class Renderable(Protocol):
    def compile(self, render_context: RenderContext) -> list[RenderableGeometry]:
        ...


class Cube:
    EDGES = (
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),
        (0, 4),
        (1, 5),
        (2, 6),
        (3, 7),
    )
    FACES = (
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    )

    def __init__(
        self,
        center: Vector3 = (0.0, 0.0, 0.0),
        size: float = 1.0,
        rotations: list[Rotation] | None = None,
        layer: int = 1,
        solid: bool = False,
    ) -> None:
        self.center = center
        self.size = size
        self.rotations = rotations or []
        self.layer = layer
        self.solid = solid

    def compile(self, render_context: RenderContext) -> list[RenderableGeometry]:
        vertices = self._vertices()
        for rotation in self.rotations:
            vertices = [_rotate_point(vertex, rotation) for vertex in vertices]

        if self.solid:
            return self._compile_solid(vertices, render_context)

        lines = [
            (
                project_point(vertices[start], render_context),
                project_point(vertices[end], render_context),
            )
            for start, end in self.EDGES
        ]

        return [RenderableGeometry(MultiLineString(lines), self.layer)]

    def _compile_solid(
        self, vertices: list[Vector3], render_context: RenderContext
    ) -> list[RenderableGeometry]:
        visible_edges = set()

        for face in self.FACES:
            normal = _face_normal([vertices[index] for index in face])
            if _dot(normal, _camera_direction(render_context)) <= 0:
                continue

            for start, end in zip(face, face[1:] + face[:1]):
                visible_edges.add(tuple(sorted((start, end))))

        lines = [
            (
                project_point(vertices[start], render_context),
                project_point(vertices[end], render_context),
            )
            for start, end in sorted(visible_edges)
        ]

        return [RenderableGeometry(MultiLineString(lines), self.layer)]

    def _vertices(self) -> list[Vector3]:
        x, y, z = self.center
        h = self.size / 2.0

        return [
            (x - h, y - h, z - h),
            (x + h, y - h, z - h),
            (x + h, y + h, z - h),
            (x - h, y + h, z - h),
            (x - h, y - h, z + h),
            (x + h, y - h, z + h),
            (x + h, y + h, z + h),
            (x - h, y + h, z + h),
        ]


class HatchedPlane:
    """A quadrilateral filled with evenly spaced, plotter-friendly lines.

    ``corners`` must follow the perimeter of the plane. Hatches use a shared
    projected angle, defaulting to the projected Y axis, so separate planes
    can participate in one continuous field of parallel lines.
    """

    def __init__(
        self,
        corners: tuple[Vector3, Vector3, Vector3, Vector3],
        hatch_spacing: float = 0.05,
        rotations: list[Rotation] | None = None,
        layer: int = 1,
        include_outline: bool = False,
        hatch_angle: float | None = None,
    ) -> None:
        if hatch_spacing <= 0:
            raise ValueError("hatch_spacing must be greater than zero")

        self.corners = corners
        self.hatch_spacing = hatch_spacing
        self.rotations = rotations or []
        self.layer = layer
        self.include_outline = include_outline
        self.hatch_angle = hatch_angle

    def compile(self, render_context: RenderContext) -> list[RenderableGeometry]:
        corners = list(self.corners)
        for rotation in self.rotations:
            corners = [_rotate_point(corner, rotation) for corner in corners]

        lines = _screen_hatched_quad_lines(
            corners,
            self.hatch_spacing,
            render_context,
            self.include_outline,
            self.hatch_angle,
        )
        return [RenderableGeometry(MultiLineString(_unique_lines(lines)), self.layer)]


class Cuboid:
    """A rectangular solid with independently styled faces.

    Only camera-facing sides are emitted. Each visible side is hatched in its
    own plane, giving a dense isometric mass while keeping the result entirely
    vector-based and suitable for a pen plotter. ``face_styles`` can override
    individual local faces with an outline or hide them entirely. Unspecified
    faces default to ``FaceStyle.HATCHED``.

    Front/back are the negative/positive Y faces, while left/right are the
    negative/positive X faces. These names remain attached to the cuboid when
    rotations are applied. ``flow_strength`` bends the hatch field coherently
    across all visible faces; its default of zero preserves straight hatches.
    """

    FACES = dict(zip(CuboidFace, Cube.FACES, strict=True))

    def __init__(
        self,
        center: Vector3 = (0.0, 0.0, 0.0),
        size: Vector3 = (1.0, 1.0, 1.0),
        hatch_spacing: float = 0.05,
        rotations: list[Rotation] | None = None,
        layer: int = 1,
        include_outline: bool = False,
        face_styles: Mapping[CuboidFace, FaceStyle] | None = None,
        hatch_angle: float | None = None,
        flow_strength: float = 0.0,
        flow_frequency: float = 1.4,
        flow_seed: int = 0,
    ) -> None:
        if any(dimension <= 0 for dimension in size):
            raise ValueError("all cuboid dimensions must be greater than zero")
        if hatch_spacing <= 0:
            raise ValueError("hatch_spacing must be greater than zero")
        if face_styles and any(
            not isinstance(face, CuboidFace) or not isinstance(style, FaceStyle)
            for face, style in face_styles.items()
        ):
            raise ValueError("face_styles must map CuboidFace to FaceStyle")
        if flow_strength < 0:
            raise ValueError("flow_strength cannot be negative")
        if flow_frequency <= 0:
            raise ValueError("flow_frequency must be greater than zero")

        self.center = center
        self.size = size
        self.hatch_spacing = hatch_spacing
        self.rotations = rotations or []
        self.layer = layer
        self.include_outline = include_outline
        self.face_styles = dict(face_styles or {})
        self.hatch_angle = hatch_angle
        self.flow_strength = flow_strength
        self.flow_frequency = flow_frequency
        self.flow_seed = flow_seed

    def compile(self, render_context: RenderContext) -> list[RenderableGeometry]:
        vertices = self._vertices()
        for rotation in self.rotations:
            vertices = [_rotate_point(vertex, rotation) for vertex in vertices]

        camera = _camera_direction(render_context)
        visible_faces: list[tuple[list[Vector3], FaceStyle]] = []
        for face_name, face in self.FACES.items():
            corners = [vertices[index] for index in face]
            if _dot(_face_normal(corners), camera) <= 0:
                continue

            visible_faces.append(
                (corners, self.face_styles.get(face_name, FaceStyle.HATCHED))
            )

        if self.flow_strength > 0:
            return self._compile_flow(vertices, visible_faces, render_context)

        lines: list[tuple[Vector2, Vector2]] = []
        for corners, style in visible_faces:
            match style:
                case FaceStyle.HATCHED:
                    lines.extend(
                        _screen_hatched_quad_lines(
                            corners,
                            self.hatch_spacing,
                            render_context,
                            self.include_outline,
                            self.hatch_angle,
                        )
                    )
                case FaceStyle.OUTLINE:
                    lines.extend(
                        _quad_outline_lines(
                            corners,
                            render_context,
                        )
                    )
                case FaceStyle.HIDDEN:
                    continue

        return [RenderableGeometry(MultiLineString(_unique_lines(lines)), self.layer)]

    def _compile_flow(
        self,
        vertices: list[Vector3],
        visible_faces: list[tuple[list[Vector3], FaceStyle]],
        render_context: RenderContext,
    ) -> list[RenderableGeometry]:
        projected = [project_point(vertex, render_context) for vertex in vertices]
        silhouette = MultiPoint(projected).convex_hull
        angle = (
            render_context.angle if self.hatch_angle is None else self.hatch_angle
        )
        flow_paths = _flow_hatched_polygon_lines(
            silhouette,
            self.hatch_spacing * render_context.scale,
            angle,
            self.flow_strength * render_context.scale,
            self.flow_frequency,
            self.flow_seed,
        )
        paths: list[list[Vector2]] = []

        for corners, style in visible_faces:
            match style:
                case FaceStyle.HATCHED:
                    face = Polygon(
                        [project_point(corner, render_context) for corner in corners]
                    )
                    for path in flow_paths:
                        paths.extend(
                            _geometry_polyline_coordinates(
                                face.intersection(LineString(path))
                            )
                        )
                    if self.include_outline:
                        paths.extend(
                            [list(line) for line in _quad_outline_lines(corners, render_context)]
                        )
                case FaceStyle.OUTLINE:
                    paths.extend(
                        [list(line) for line in _quad_outline_lines(corners, render_context)]
                    )
                case FaceStyle.HIDDEN:
                    continue

        return [RenderableGeometry(MultiLineString(paths), self.layer)]

    def _vertices(self) -> list[Vector3]:
        x, y, z = self.center
        width, depth, height = self.size
        hx, hy, hz = width / 2.0, depth / 2.0, height / 2.0

        return [
            (x - hx, y - hy, z - hz),
            (x + hx, y - hy, z - hz),
            (x + hx, y + hy, z - hz),
            (x - hx, y + hy, z - hz),
            (x - hx, y - hy, z + hz),
            (x + hx, y - hy, z + hz),
            (x + hx, y + hy, z + hz),
            (x - hx, y + hy, z + hz),
        ]


class SlicedCuboid:
    """A translucent-looking volume built from parallel cross-sections.

    Unlike ``Cuboid``, this component does not remove rear geometry. Every
    slice is a rectangular outline by default, so overlapping front, back,
    and internal lines create density while preserving transparency. Set
    ``line_axis`` to retain only the two edges parallel to that local axis.
    """

    def __init__(
        self,
        center: Vector3 = (0.0, 0.0, 0.0),
        size: Vector3 = (1.0, 1.0, 1.0),
        slice_spacing: float = 0.1,
        slice_axis: Axis = Axis.Z,
        line_axis: Axis | None = None,
        rotations: list[Rotation] | None = None,
        layer: int = 1,
    ) -> None:
        if any(dimension <= 0 for dimension in size):
            raise ValueError("all cuboid dimensions must be greater than zero")
        if slice_spacing <= 0:
            raise ValueError("slice_spacing must be greater than zero")
        if not isinstance(slice_axis, Axis):
            raise ValueError("slice_axis must be an Axis")
        if line_axis is not None and (
            not isinstance(line_axis, Axis) or line_axis == slice_axis
        ):
            raise ValueError("line_axis must be perpendicular to slice_axis")

        self.center = center
        self.size = size
        self.slice_spacing = slice_spacing
        self.slice_axis = slice_axis
        self.line_axis = line_axis
        self.rotations = rotations or []
        self.layer = layer

    def compile(self, render_context: RenderContext) -> list[RenderableGeometry]:
        axis_length = self.size[_axis_index(self.slice_axis)]
        interval_count = max(1, math.ceil(axis_length / self.slice_spacing))
        lines: list[tuple[Vector2, Vector2]] = []

        for index in range(interval_count + 1):
            amount = index / interval_count - 0.5
            corners = self._slice_corners(amount)
            for rotation in self.rotations:
                corners = [_rotate_point(corner, rotation) for corner in corners]
            lines.extend(
                _slice_projected_lines(
                    corners,
                    self.slice_axis,
                    self.line_axis,
                    render_context,
                )
            )

        return [RenderableGeometry(MultiLineString(_unique_lines(lines)), self.layer)]

    def _slice_corners(self, amount: float) -> list[Vector3]:
        return _cuboid_slice_corners(
            self.center,
            self.size,
            self.slice_axis,
            amount,
        )


class HatchedVolume:
    """The complete projected silhouette of a cuboid filled on one axis."""

    def __init__(
        self,
        center: Vector3 = (0.0, 0.0, 0.0),
        size: Vector3 = (1.0, 1.0, 1.0),
        hatch_spacing: float = 0.15,
        hatch_axis: Axis = Axis.Y,
        rotations: list[Rotation] | None = None,
        layer: int = 1,
    ) -> None:
        if any(dimension <= 0 for dimension in size):
            raise ValueError("all volume dimensions must be greater than zero")
        if hatch_spacing <= 0:
            raise ValueError("hatch_spacing must be greater than zero")
        if not isinstance(hatch_axis, Axis):
            raise ValueError("hatch_axis must be an Axis")

        self.center = center
        self.size = size
        self.hatch_spacing = hatch_spacing
        self.hatch_axis = hatch_axis
        self.rotations = rotations or []
        self.layer = layer

    def compile(self, render_context: RenderContext) -> list[RenderableGeometry]:
        vertices = _cuboid_vertices(self.center, self.size)
        for rotation in self.rotations:
            vertices = [_rotate_point(vertex, rotation) for vertex in vertices]

        projected = [project_point(vertex, render_context) for vertex in vertices]
        silhouette = MultiPoint(projected).convex_hull
        lines = _screen_hatched_polygon_lines(
            silhouette,
            self.hatch_spacing * render_context.scale,
            _projected_axis_angle(self.hatch_axis, render_context),
        )
        return [RenderableGeometry(MultiLineString(_unique_lines(lines)), self.layer)]


class RandomizedHatchedVolume:
    """A translucent volume with a loose cloud of denser interior hatches.

    Sparse lines cross the complete silhouette. Additional parallel segments
    gather toward its center, with independent positions and endpoints, so the
    density suggests an inner cloud without describing another cuboid.
    """

    def __init__(
        self,
        center: Vector3 = (0.0, 0.0, 0.0),
        size: Vector3 = (1.0, 1.0, 1.0),
        hatch_spacing: float = 0.15,
        hatch_axis: Axis = Axis.Y,
        spacing_jitter: float = 0.65,
        cloud_density: int = 5,
        cloud_spread: float = 0.78,
        cloud_length: float = 0.72,
        seed: int = 12,
        rotations: list[Rotation] | None = None,
        layer: int = 1,
    ) -> None:
        if any(dimension <= 0 for dimension in size):
            raise ValueError("all volume dimensions must be greater than zero")
        if hatch_spacing <= 0:
            raise ValueError("hatch_spacing must be greater than zero")
        if not isinstance(hatch_axis, Axis):
            raise ValueError("hatch_axis must be an Axis")
        if spacing_jitter < 0 or spacing_jitter >= 1:
            raise ValueError("spacing_jitter must be between zero and one")
        if not isinstance(cloud_density, int) or cloud_density < 0:
            raise ValueError("cloud_density must be a non-negative integer")
        if cloud_spread <= 0 or cloud_spread > 1:
            raise ValueError("cloud_spread must be between zero and one")
        if cloud_length <= 0 or cloud_length > 1:
            raise ValueError("cloud_length must be between zero and one")

        self.center = center
        self.size = size
        self.hatch_spacing = hatch_spacing
        self.hatch_axis = hatch_axis
        self.spacing_jitter = spacing_jitter
        self.cloud_density = cloud_density
        self.cloud_spread = cloud_spread
        self.cloud_length = cloud_length
        self.seed = seed
        self.rotations = rotations or []
        self.layer = layer

    def compile(self, render_context: RenderContext) -> list[RenderableGeometry]:
        vertices = _cuboid_vertices(self.center, self.size)
        for rotation in self.rotations:
            vertices = [_rotate_point(vertex, rotation) for vertex in vertices]

        projected = [project_point(vertex, render_context) for vertex in vertices]
        silhouette = MultiPoint(projected).convex_hull
        lines = _randomized_screen_hatched_polygon_lines(
            silhouette,
            self.hatch_spacing * render_context.scale,
            _projected_axis_angle(self.hatch_axis, render_context),
            self.spacing_jitter,
            self.seed,
        )
        lines.extend(
            _cloud_hatched_polygon_lines(
                silhouette,
                self.hatch_spacing * render_context.scale,
                _projected_axis_angle(self.hatch_axis, render_context),
                self.cloud_density,
                self.cloud_spread,
                self.cloud_length,
                self.seed + 1,
            )
        )
        return [RenderableGeometry(MultiLineString(_unique_lines(lines)), self.layer)]


class FlowHatchedVolume:
    """A translucent volume filled with gently flowing parallel paths."""

    def __init__(
        self,
        center: Vector3 = (0.0, 0.0, 0.0),
        size: Vector3 = (1.0, 1.0, 1.0),
        hatch_spacing: float = 0.15,
        hatch_axis: Axis = Axis.Y,
        flow_strength: float = 0.18,
        flow_frequency: float = 1.4,
        seed: int = 12,
        rotations: list[Rotation] | None = None,
        layer: int = 1,
    ) -> None:
        _validate_volume_hatching(size, hatch_spacing, hatch_axis)
        if flow_strength < 0:
            raise ValueError("flow_strength cannot be negative")
        if flow_frequency <= 0:
            raise ValueError("flow_frequency must be greater than zero")

        self.center = center
        self.size = size
        self.hatch_spacing = hatch_spacing
        self.hatch_axis = hatch_axis
        self.flow_strength = flow_strength
        self.flow_frequency = flow_frequency
        self.seed = seed
        self.rotations = rotations or []
        self.layer = layer

    def compile(self, render_context: RenderContext) -> list[RenderableGeometry]:
        silhouette = _projected_cuboid_silhouette(
            self.center, self.size, self.rotations, render_context
        )
        paths = _flow_hatched_polygon_lines(
            silhouette,
            self.hatch_spacing * render_context.scale,
            _projected_axis_angle(self.hatch_axis, render_context),
            self.flow_strength * render_context.scale,
            self.flow_frequency,
            self.seed,
        )
        return [RenderableGeometry(MultiLineString(paths), self.layer)]


class ErodedHatchedVolume:
    """A parallel hatch field interrupted by coherent, weathered gaps."""

    def __init__(
        self,
        center: Vector3 = (0.0, 0.0, 0.0),
        size: Vector3 = (1.0, 1.0, 1.0),
        hatch_spacing: float = 0.15,
        hatch_axis: Axis = Axis.Y,
        erosion: float = 0.42,
        erosion_scale: float = 2.4,
        seed: int = 12,
        rotations: list[Rotation] | None = None,
        layer: int = 1,
    ) -> None:
        _validate_volume_hatching(size, hatch_spacing, hatch_axis)
        if erosion < 0 or erosion > 1:
            raise ValueError("erosion must be between zero and one")
        if erosion_scale <= 0:
            raise ValueError("erosion_scale must be greater than zero")

        self.center = center
        self.size = size
        self.hatch_spacing = hatch_spacing
        self.hatch_axis = hatch_axis
        self.erosion = erosion
        self.erosion_scale = erosion_scale
        self.seed = seed
        self.rotations = rotations or []
        self.layer = layer

    def compile(self, render_context: RenderContext) -> list[RenderableGeometry]:
        silhouette = _projected_cuboid_silhouette(
            self.center, self.size, self.rotations, render_context
        )
        lines = _eroded_hatched_polygon_lines(
            silhouette,
            self.hatch_spacing * render_context.scale,
            _projected_axis_angle(self.hatch_axis, render_context),
            self.erosion,
            self.erosion_scale,
            self.seed,
        )
        return [RenderableGeometry(MultiLineString(_unique_lines(lines)), self.layer)]


class StratifiedVolume:
    """A volume whose parallel hatches gather into irregular density bands."""

    def __init__(
        self,
        center: Vector3 = (0.0, 0.0, 0.0),
        size: Vector3 = (1.0, 1.0, 1.0),
        hatch_spacing: float = 0.15,
        hatch_axis: Axis = Axis.Y,
        band_count: float = 4.0,
        density_contrast: float = 0.78,
        seed: int = 12,
        rotations: list[Rotation] | None = None,
        layer: int = 1,
    ) -> None:
        _validate_volume_hatching(size, hatch_spacing, hatch_axis)
        if band_count <= 0:
            raise ValueError("band_count must be greater than zero")
        if density_contrast < 0 or density_contrast > 1:
            raise ValueError("density_contrast must be between zero and one")

        self.center = center
        self.size = size
        self.hatch_spacing = hatch_spacing
        self.hatch_axis = hatch_axis
        self.band_count = band_count
        self.density_contrast = density_contrast
        self.seed = seed
        self.rotations = rotations or []
        self.layer = layer

    def compile(self, render_context: RenderContext) -> list[RenderableGeometry]:
        silhouette = _projected_cuboid_silhouette(
            self.center, self.size, self.rotations, render_context
        )
        lines = _stratified_hatched_polygon_lines(
            silhouette,
            self.hatch_spacing * render_context.scale,
            _projected_axis_angle(self.hatch_axis, render_context),
            self.band_count,
            self.density_contrast,
            self.seed,
        )
        return [RenderableGeometry(MultiLineString(_unique_lines(lines)), self.layer)]


class RecursiveHatchedVolume:
    """Nested filled silhouettes whose accumulated density creates a soft core."""

    def __init__(
        self,
        center: Vector3 = (0.0, 0.0, 0.0),
        size: Vector3 = (1.0, 1.0, 1.0),
        hatch_spacing: float = 0.15,
        hatch_axis: Axis = Axis.Y,
        levels: int = 6,
        inset: Vector3 = (0.84, 0.78, 0.82),
        drift: Vector3 = (0.0, -0.1, -0.18),
        spacing_decay: float = 0.88,
        jitter: float = 0.035,
        seed: int = 12,
        rotations: list[Rotation] | None = None,
        layer: int = 1,
    ) -> None:
        if any(dimension <= 0 for dimension in size):
            raise ValueError("all volume dimensions must be greater than zero")
        if hatch_spacing <= 0:
            raise ValueError("hatch_spacing must be greater than zero")
        if not isinstance(hatch_axis, Axis):
            raise ValueError("hatch_axis must be an Axis")
        if not isinstance(levels, int) or levels < 1:
            raise ValueError("levels must be a positive integer")
        if any(factor <= 0 or factor >= 1 for factor in inset):
            raise ValueError("inset factors must be between zero and one")
        if spacing_decay <= 0:
            raise ValueError("spacing_decay must be greater than zero")
        if jitter < 0:
            raise ValueError("jitter cannot be negative")

        self.center = center
        self.size = size
        self.hatch_spacing = hatch_spacing
        self.hatch_axis = hatch_axis
        self.levels = levels
        self.inset = inset
        self.drift = drift
        self.spacing_decay = spacing_decay
        self.jitter = jitter
        self.seed = seed
        self.rotations = rotations or []
        self.layer = layer

    def compile(self, render_context: RenderContext) -> list[RenderableGeometry]:
        lines: list[tuple[Vector2, Vector2]] = []

        for level in range(1, self.levels + 1):
            level_size = tuple(
                dimension * factor**level
                for dimension, factor in zip(self.size, self.inset, strict=True)
            )
            level_center = tuple(
                coordinate + displacement * level
                for coordinate, displacement in zip(
                    self.center,
                    self.drift,
                    strict=True,
                )
            )
            level_spacing = self.hatch_spacing * self.spacing_decay**level
            phase = (self.seed * 0.61803398875) % 1.0
            amount = level / (self.levels + 1) - 0.5
            offset = _coherent_slice_offset(
                self.hatch_axis,
                amount,
                self.jitter,
                phase,
            )
            displaced_center = tuple(
                coordinate + displacement
                for coordinate, displacement in zip(
                    level_center,
                    offset,
                    strict=True,
                )
            )
            vertices = _cuboid_vertices(displaced_center, level_size)
            for rotation in self.rotations:
                vertices = [_rotate_point(vertex, rotation) for vertex in vertices]

            projected = [project_point(vertex, render_context) for vertex in vertices]
            silhouette = MultiPoint(projected).convex_hull
            lines.extend(
                _screen_hatched_polygon_lines(
                    silhouette,
                    level_spacing * render_context.scale,
                    _projected_axis_angle(self.hatch_axis, render_context),
                )
            )

        return [RenderableGeometry(MultiLineString(_unique_lines(lines)), self.layer)]


class Scene:
    def __init__(
        self,
        frame: Polygon,
        scale: float,
        children: list[Renderable],
        origin: Vector2 | str = "centroid",
        angle: float = math.radians(30),
        clip_to_frame: bool = True,
    ) -> None:
        self.render_context = RenderContext(frame, scale, angle, origin)
        self.children = children
        self.clip_to_frame = clip_to_frame

    def compile(self) -> list[RenderableGeometry]:
        renderables = []

        for child in self.children:
            for renderable in child.compile(self.render_context):
                if self.clip_to_frame:
                    renderable.geometry = self.render_context.frame.intersection(
                        renderable.geometry
                    )

                renderables.append(renderable)

        return renderables

    def render(self, vsk) -> None:
        for renderable in self.compile():
            if renderable.layer == 0:
                vsk.noStroke()
            else:
                vsk.stroke(renderable.layer)

            vsk.geometry(renderable.geometry)


def project_point(point: Vector3, render_context: RenderContext) -> Vector2:
    origin_x, origin_y = render_context.resolved_origin
    x, y, z = point
    angle_cos = math.cos(render_context.angle)
    angle_sin = math.sin(render_context.angle)

    return (
        origin_x + (x - y) * render_context.scale * angle_cos,
        origin_y - (x + y) * render_context.scale * angle_sin - z * render_context.scale,
    )


def _screen_hatched_quad_lines(
    corners: list[Vector3],
    hatch_spacing: float,
    render_context: RenderContext,
    include_outline: bool,
    hatch_angle: float | None,
) -> list[tuple[Vector2, Vector2]]:
    projected = [project_point(corner, render_context) for corner in corners]
    polygon = Polygon(projected)
    angle = render_context.angle if hatch_angle is None else hatch_angle
    lines = _screen_hatched_polygon_lines(
        polygon,
        hatch_spacing * render_context.scale,
        angle,
    )

    if include_outline:
        lines.extend(_quad_outline_lines(corners, render_context))

    return lines


def _screen_hatched_polygon_lines(
    polygon: Polygon,
    projected_spacing: float,
    angle: float,
) -> list[tuple[Vector2, Vector2]]:
    direction = (math.cos(angle), math.sin(angle))
    normal = (-direction[1], direction[0])
    coordinates = list(polygon.exterior.coords)[:-1]
    normal_positions = [point[0] * normal[0] + point[1] * normal[1] for point in coordinates]
    direction_positions = [
        point[0] * direction[0] + point[1] * direction[1] for point in coordinates
    ]
    normal_min, normal_max = min(normal_positions), max(normal_positions)
    direction_min, direction_max = min(direction_positions), max(direction_positions)
    padding = max(normal_max - normal_min, direction_max - direction_min, 1.0)
    first_offset = math.floor(normal_min / projected_spacing) * projected_spacing
    last_offset = math.ceil(normal_max / projected_spacing) * projected_spacing

    lines: list[tuple[Vector2, Vector2]] = []
    offset = first_offset
    while offset <= last_offset + projected_spacing * 1e-9:
        start = (
            direction[0] * (direction_min - padding) + normal[0] * offset,
            direction[1] * (direction_min - padding) + normal[1] * offset,
        )
        end = (
            direction[0] * (direction_max + padding) + normal[0] * offset,
            direction[1] * (direction_max + padding) + normal[1] * offset,
        )
        clipped = polygon.intersection(LineString((start, end)))
        lines.extend(_geometry_line_endpoints(clipped))
        offset += projected_spacing

    return lines


def _randomized_screen_hatched_polygon_lines(
    polygon: Polygon,
    projected_spacing: float,
    angle: float,
    spacing_jitter: float,
    seed: int,
) -> list[tuple[Vector2, Vector2]]:
    direction = (math.cos(angle), math.sin(angle))
    normal = (-direction[1], direction[0])
    coordinates = list(polygon.exterior.coords)[:-1]
    normal_positions = [
        point[0] * normal[0] + point[1] * normal[1] for point in coordinates
    ]
    direction_positions = [
        point[0] * direction[0] + point[1] * direction[1]
        for point in coordinates
    ]
    normal_min, normal_max = min(normal_positions), max(normal_positions)
    direction_min, direction_max = min(direction_positions), max(direction_positions)
    padding = max(normal_max - normal_min, direction_max - direction_min, 1.0)

    rng = random.Random(seed)
    offset = normal_min - rng.random() * projected_spacing
    lines: list[tuple[Vector2, Vector2]] = []

    while offset <= normal_max + projected_spacing * 1e-9:
        start = (
            direction[0] * (direction_min - padding) + normal[0] * offset,
            direction[1] * (direction_min - padding) + normal[1] * offset,
        )
        end = (
            direction[0] * (direction_max + padding) + normal[0] * offset,
            direction[1] * (direction_max + padding) + normal[1] * offset,
        )
        clipped = polygon.intersection(LineString((start, end)))
        lines.extend(_geometry_line_endpoints(clipped))

        step_factor = 1.0 + rng.uniform(-spacing_jitter, spacing_jitter)
        offset += projected_spacing * step_factor

    return lines


def _cloud_hatched_polygon_lines(
    polygon: Polygon,
    projected_spacing: float,
    angle: float,
    density: int,
    spread: float,
    maximum_length: float,
    seed: int,
) -> list[tuple[Vector2, Vector2]]:
    """Scatter parallel segments toward the middle of a silhouette."""
    if density == 0:
        return []

    direction = (math.cos(angle), math.sin(angle))
    normal = (-direction[1], direction[0])
    coordinates = list(polygon.exterior.coords)[:-1]
    normal_positions = [
        point[0] * normal[0] + point[1] * normal[1] for point in coordinates
    ]
    direction_positions = [
        point[0] * direction[0] + point[1] * direction[1]
        for point in coordinates
    ]
    normal_min, normal_max = min(normal_positions), max(normal_positions)
    direction_min, direction_max = min(direction_positions), max(direction_positions)
    normal_center = (normal_min + normal_max) / 2.0
    normal_radius = (normal_max - normal_min) / 2.0
    padding = max(normal_max - normal_min, direction_max - direction_min, 1.0)
    line_count = math.ceil((normal_max - normal_min) / projected_spacing) * density

    rng = random.Random(seed)
    lines: list[tuple[Vector2, Vector2]] = []
    for _ in range(line_count):
        offset = rng.gauss(normal_center, normal_radius * spread / 2.0)
        while offset < normal_min or offset > normal_max:
            offset = rng.gauss(normal_center, normal_radius * spread / 2.0)
        start = (
            direction[0] * (direction_min - padding) + normal[0] * offset,
            direction[1] * (direction_min - padding) + normal[1] * offset,
        )
        end = (
            direction[0] * (direction_max + padding) + normal[0] * offset,
            direction[1] * (direction_max + padding) + normal[1] * offset,
        )
        chords = _geometry_line_endpoints(
            polygon.intersection(LineString((start, end)))
        )

        distance_from_center = abs(offset - normal_center) / normal_radius
        centrality = max(0.0, 1.0 - distance_from_center)
        length_limit = maximum_length * (0.55 + 0.45 * math.sqrt(centrality))
        length_fraction = rng.uniform(0.18, 1.0) * length_limit
        center_shift = rng.uniform(-0.35, 0.35) * (1.0 - length_fraction)
        segment_center = 0.5 + center_shift
        segment_start = segment_center - length_fraction / 2.0
        segment_end = segment_center + length_fraction / 2.0

        for chord_start, chord_end in chords:
            dx = chord_end[0] - chord_start[0]
            dy = chord_end[1] - chord_start[1]
            lines.append(
                (
                    (
                        chord_start[0] + dx * segment_start,
                        chord_start[1] + dy * segment_start,
                    ),
                    (
                        chord_start[0] + dx * segment_end,
                        chord_start[1] + dy * segment_end,
                    ),
                )
            )

    return lines


def _flow_hatched_polygon_lines(
    polygon: Polygon,
    projected_spacing: float,
    angle: float,
    strength: float,
    frequency: float,
    seed: int,
) -> list[list[Vector2]]:
    direction, normal, bounds = _polygon_axis_frame(polygon, angle)
    normal_min, normal_max, direction_min, direction_max = bounds
    rng = random.Random(seed)
    first_phase = rng.random()
    second_phase = rng.random()
    offset = normal_min - rng.random() * projected_spacing
    path_padding = projected_spacing + strength
    path_min = direction_min - path_padding
    path_max = direction_max + path_padding
    path_length = path_max - path_min
    sample_count = max(32, math.ceil(path_length / (projected_spacing * 0.45)))
    paths: list[list[Vector2]] = []
    line_index = 0

    while offset <= normal_max + projected_spacing * 1e-9:
        points: list[Vector2] = []
        line_phase = first_phase + line_index * 0.017
        for sample in range(sample_count + 1):
            amount = sample / sample_count
            position = path_min + path_length * amount
            displacement = strength * (
                0.68 * math.sin(math.tau * (frequency * amount + line_phase))
                + 0.32
                * math.sin(
                    math.tau * (frequency * 0.47 * amount + second_phase)
                )
            )
            points.append(
                (
                    direction[0] * position + normal[0] * (offset + displacement),
                    direction[1] * position + normal[1] * (offset + displacement),
                )
            )

        clipped = polygon.intersection(LineString(points))
        paths.extend(_geometry_polyline_coordinates(clipped))
        offset += projected_spacing
        line_index += 1

    return paths


def _eroded_hatched_polygon_lines(
    polygon: Polygon,
    projected_spacing: float,
    angle: float,
    erosion: float,
    erosion_scale: float,
    seed: int,
) -> list[tuple[Vector2, Vector2]]:
    direction, normal, bounds = _polygon_axis_frame(polygon, angle)
    normal_min, normal_max, direction_min, direction_max = bounds
    normal_span = normal_max - normal_min
    direction_span = direction_max - direction_min
    rng = random.Random(seed)
    phases = (rng.random(), rng.random(), rng.random())
    source_lines = _screen_hatched_polygon_lines(polygon, projected_spacing, angle)
    lines: list[tuple[Vector2, Vector2]] = []

    for start, end in source_lines:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = math.hypot(dx, dy)
        interval_count = max(18, math.ceil(length / (projected_spacing * 0.45)))
        normal_position = start[0] * normal[0] + start[1] * normal[1]
        v = (normal_position - normal_min) / normal_span
        run_start: float | None = None

        for interval in range(interval_count):
            midpoint = (interval + 0.5) / interval_count
            x = start[0] + dx * midpoint
            y = start[1] + dy * midpoint
            direction_position = x * direction[0] + y * direction[1]
            u = (direction_position - direction_min) / direction_span
            field = _erosion_field(u, v, erosion_scale, phases)
            retained = field >= erosion

            if retained and run_start is None:
                run_start = interval / interval_count
            elif not retained and run_start is not None:
                run_end = interval / interval_count
                lines.append(_line_subsegment(start, end, run_start, run_end))
                run_start = None

        if run_start is not None:
            lines.append(_line_subsegment(start, end, run_start, 1.0))

    return lines


def _stratified_hatched_polygon_lines(
    polygon: Polygon,
    projected_spacing: float,
    angle: float,
    band_count: float,
    density_contrast: float,
    seed: int,
) -> list[tuple[Vector2, Vector2]]:
    direction, normal, bounds = _polygon_axis_frame(polygon, angle)
    normal_min, normal_max, direction_min, direction_max = bounds
    normal_span = normal_max - normal_min
    padding = max(normal_span, direction_max - direction_min, 1.0)
    rng = random.Random(seed)
    first_phase = rng.random()
    second_phase = rng.random()
    offset = normal_min - rng.random() * projected_spacing
    lines: list[tuple[Vector2, Vector2]] = []

    while offset <= normal_max + projected_spacing * 1e-9:
        start = (
            direction[0] * (direction_min - padding) + normal[0] * offset,
            direction[1] * (direction_min - padding) + normal[1] * offset,
        )
        end = (
            direction[0] * (direction_max + padding) + normal[0] * offset,
            direction[1] * (direction_max + padding) + normal[1] * offset,
        )
        lines.extend(_geometry_line_endpoints(polygon.intersection(LineString((start, end)))))

        amount = (offset - normal_min) / normal_span
        warped_amount = amount + 0.08 * math.sin(
            math.tau * (amount * 1.7 + second_phase)
        )
        band = 0.5 + 0.5 * math.sin(
            math.tau * (band_count * warped_amount + first_phase)
        )
        band_spacing = 1.65 - 1.3 * band
        spacing_factor = 1.0 + density_contrast * (band_spacing - 1.0)
        spacing_factor *= rng.uniform(0.92, 1.08)
        offset += projected_spacing * spacing_factor

    return lines


def _polygon_axis_frame(
    polygon: Polygon,
    angle: float,
) -> tuple[Vector2, Vector2, tuple[float, float, float, float]]:
    direction = (math.cos(angle), math.sin(angle))
    normal = (-direction[1], direction[0])
    coordinates = list(polygon.exterior.coords)[:-1]
    normal_positions = [
        point[0] * normal[0] + point[1] * normal[1] for point in coordinates
    ]
    direction_positions = [
        point[0] * direction[0] + point[1] * direction[1]
        for point in coordinates
    ]
    return (
        direction,
        normal,
        (
            min(normal_positions),
            max(normal_positions),
            min(direction_positions),
            max(direction_positions),
        ),
    )


def _erosion_field(
    u: float,
    v: float,
    scale: float,
    phases: tuple[float, float, float],
) -> float:
    first = math.sin(math.tau * (u * scale + phases[0])) * math.sin(
        math.tau * (v * scale * 0.73 + phases[1])
    )
    second = math.sin(
        math.tau * (u * scale * 0.43 + v * scale * 0.31 + phases[2])
    )
    third = math.cos(
        math.tau * (u * scale * 1.71 - v * scale * 0.89 + phases[0])
    )
    return 0.5 + 0.5 * (0.55 * first + 0.3 * second + 0.15 * third)


def _line_subsegment(
    start: Vector2,
    end: Vector2,
    start_amount: float,
    end_amount: float,
) -> tuple[Vector2, Vector2]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    return (
        (start[0] + dx * start_amount, start[1] + dy * start_amount),
        (start[0] + dx * end_amount, start[1] + dy * end_amount),
    )


def _geometry_line_endpoints(
    geometry: shapely.Geometry,
) -> list[tuple[Vector2, Vector2]]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        coordinates = list(geometry.coords)
        if len(coordinates) < 2 or geometry.length <= 1e-12:
            return []
        return [(coordinates[0], coordinates[-1])]

    lines: list[tuple[Vector2, Vector2]] = []
    for part in getattr(geometry, "geoms", ()):
        lines.extend(_geometry_line_endpoints(part))
    return lines


def _geometry_polyline_coordinates(geometry: shapely.Geometry) -> list[list[Vector2]]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        coordinates = list(geometry.coords)
        if len(coordinates) < 2 or geometry.length <= 1e-12:
            return []
        return [coordinates]

    paths: list[list[Vector2]] = []
    for part in getattr(geometry, "geoms", ()):
        paths.extend(_geometry_polyline_coordinates(part))
    return paths


def _quad_outline_lines(
    corners: list[Vector3],
    render_context: RenderContext,
) -> list[tuple[Vector2, Vector2]]:
    projected = [project_point(corner, render_context) for corner in corners]
    return list(zip(projected, projected[1:] + projected[:1]))


def _cuboid_vertices(center: Vector3, size: Vector3) -> list[Vector3]:
    x, y, z = center
    width, depth, height = size
    hx, hy, hz = width / 2.0, depth / 2.0, height / 2.0
    return [
        (x - hx, y - hy, z - hz),
        (x + hx, y - hy, z - hz),
        (x + hx, y + hy, z - hz),
        (x - hx, y + hy, z - hz),
        (x - hx, y - hy, z + hz),
        (x + hx, y - hy, z + hz),
        (x + hx, y + hy, z + hz),
        (x - hx, y + hy, z + hz),
    ]


def _validate_volume_hatching(
    size: Vector3,
    hatch_spacing: float,
    hatch_axis: Axis,
) -> None:
    if any(dimension <= 0 for dimension in size):
        raise ValueError("all volume dimensions must be greater than zero")
    if hatch_spacing <= 0:
        raise ValueError("hatch_spacing must be greater than zero")
    if not isinstance(hatch_axis, Axis):
        raise ValueError("hatch_axis must be an Axis")


def _projected_cuboid_silhouette(
    center: Vector3,
    size: Vector3,
    rotations: list[Rotation],
    render_context: RenderContext,
) -> Polygon:
    vertices = _cuboid_vertices(center, size)
    for rotation in rotations:
        vertices = [_rotate_point(vertex, rotation) for vertex in vertices]
    projected = [project_point(vertex, render_context) for vertex in vertices]
    return MultiPoint(projected).convex_hull


def _slice_projected_lines(
    corners: list[Vector3],
    slice_axis: Axis,
    line_axis: Axis | None,
    render_context: RenderContext,
) -> list[tuple[Vector2, Vector2]]:
    if line_axis is None:
        return _quad_outline_lines(corners, render_context)

    first_edge_axis = {
        Axis.X: Axis.Y,
        Axis.Y: Axis.X,
        Axis.Z: Axis.X,
    }[slice_axis]
    edge_indices = (
        ((0, 1), (2, 3))
        if line_axis == first_edge_axis
        else ((1, 2), (3, 0))
    )
    return [
        (
            project_point(corners[start], render_context),
            project_point(corners[end], render_context),
        )
        for start, end in edge_indices
    ]


def _cuboid_slice_corners(
    center: Vector3,
    size: Vector3,
    axis: Axis,
    amount: float,
) -> list[Vector3]:
    x, y, z = center
    width, depth, height = size
    hx, hy, hz = width / 2.0, depth / 2.0, height / 2.0

    match axis:
        case Axis.X:
            slice_x = x + amount * width
            return [
                (slice_x, y - hy, z - hz),
                (slice_x, y + hy, z - hz),
                (slice_x, y + hy, z + hz),
                (slice_x, y - hy, z + hz),
            ]
        case Axis.Y:
            slice_y = y + amount * depth
            return [
                (x - hx, slice_y, z - hz),
                (x + hx, slice_y, z - hz),
                (x + hx, slice_y, z + hz),
                (x - hx, slice_y, z + hz),
            ]
        case Axis.Z:
            slice_z = z + amount * height
            return [
                (x - hx, y - hy, slice_z),
                (x + hx, y - hy, slice_z),
                (x + hx, y + hy, slice_z),
                (x - hx, y + hy, slice_z),
            ]


def _coherent_slice_offset(
    axis: Axis,
    amount: float,
    jitter: float,
    phase: float,
) -> Vector3:
    first = jitter * (
        0.72 * math.sin(math.tau * (amount * 0.85 + phase))
        + 0.28 * math.sin(math.tau * (amount * 1.7 + phase * 0.61))
    )
    second = jitter * (
        0.7 * math.cos(math.tau * (amount * 1.1 + phase * 1.37))
        + 0.3 * math.sin(math.tau * (amount * 1.9 - phase * 0.43))
    )

    match axis:
        case Axis.X:
            return (0.0, first, second)
        case Axis.Y:
            return (first, 0.0, second)
        case Axis.Z:
            return (first, second, 0.0)


def _axis_index(axis: Axis) -> int:
    match axis:
        case Axis.X:
            return 0
        case Axis.Y:
            return 1
        case Axis.Z:
            return 2


def _projected_axis_angle(axis: Axis, render_context: RenderContext) -> float:
    match axis:
        case Axis.X:
            return -render_context.angle
        case Axis.Y:
            return render_context.angle
        case Axis.Z:
            return -math.pi / 2


def _unique_lines(
    lines: list[tuple[Vector2, Vector2]],
) -> list[tuple[Vector2, Vector2]]:
    unique: dict[tuple[Vector2, Vector2], tuple[Vector2, Vector2]] = {}
    for line in lines:
        start = (round(line[0][0], 12), round(line[0][1], 12))
        end = (round(line[1][0], 12), round(line[1][1], 12))
        key = tuple(sorted((start, end)))
        unique[key] = line

    return list(unique.values())


def _rotate_point(point: Vector3, rotation: Rotation) -> Vector3:
    px, py, pz = point
    ox, oy, oz = rotation.origin
    x = px - ox
    y = py - oy
    z = pz - oz
    c = math.cos(rotation.angle)
    s = math.sin(rotation.angle)

    match rotation.axis:
        case Axis.X:
            rotated = (x, y * c - z * s, y * s + z * c)
        case Axis.Y:
            rotated = (x * c + z * s, y, -x * s + z * c)
        case Axis.Z:
            rotated = (x * c - y * s, x * s + y * c, z)

    return (rotated[0] + ox, rotated[1] + oy, rotated[2] + oz)


def _face_normal(vertices: list[Vector3]) -> Vector3:
    edge_a = _subtract(vertices[1], vertices[0])
    edge_b = _subtract(vertices[2], vertices[1])
    return _cross(edge_a, edge_b)


def _camera_direction(render_context: RenderContext) -> Vector3:
    angle_cos = math.cos(render_context.angle)
    angle_sin = math.sin(render_context.angle)
    return (-angle_cos, -angle_cos, 2 * angle_cos * angle_sin)


def _subtract(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Vector3, b: Vector3) -> Vector3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: Vector3, b: Vector3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
