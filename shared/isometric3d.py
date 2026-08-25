from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import shapely
from shapely.geometry import MultiLineString, Polygon


Vector2 = tuple[float, float]
Vector3 = tuple[float, float, float]


class Axis(Enum):
    X = "x"
    Y = "y"
    Z = "z"


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
