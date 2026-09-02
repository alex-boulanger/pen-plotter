"""Seeded moire field.

Closely spaced horizontal rules are bent by local twist and pinch fields into
dark interference caustics. Each rule remains an independent plotter path so
the row transitions do not accumulate into heavy lines along the page edges.
"""

from dataclasses import dataclass
from math import ceil, cos, exp, hypot, pi, radians, sin, tan

import vsketch


PAGE_WIDTH = 21.0
PAGE_HEIGHT = 29.7


@dataclass(frozen=True)
class FocusField:
    x: float
    y: float
    radius_scale: float
    direction: float
    phase: float
    pinch_scale: float


class MoireSketch(vsketch.SketchClass):
    margin = vsketch.Param(1.4, 0.5, 4.0, step=0.1)
    line_density = vsketch.Param(6.5, 2.0, 12.0, step=0.25)
    sample_step = vsketch.Param(0.055, 0.02, 0.25, step=0.005)

    field_radius = vsketch.Param(5.6, 2.0, 10.0, step=0.1)
    twist = vsketch.Param(0.9, 0.0, 2.5, step=0.05)
    pinch = vsketch.Param(0.82, 0.0, 0.97, step=0.01)
    edge_fade = vsketch.Param(1.2, 0.2, 4.0, step=0.1)
    field_count = vsketch.Param(4, 2, 8)
    layout_candidates = vsketch.Param(12, 1, 40)

    secondary_density = vsketch.Param(0.38, 0.1, 0.8, step=0.02)
    secondary_angle = vsketch.Param(3.0, -10.0, 10.0, step=0.25)
    secondary_strength = vsketch.Param(0.55, 0.1, 1.0, step=0.05)
    secondary_color = vsketch.Param(
        "red", choices=("red", "blue", "black")
    )

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False, center=False)
        vsk.scale("cm")
        vsk.noFill()
        vsk.penWidth("0.3mm", 1)
        vsk.penWidth("0.25mm", 2)

        x_min = self.margin
        x_max = PAGE_WIDTH - self.margin
        y_min = self.margin
        y_max = PAGE_HEIGHT - self.margin

        fields = self.make_fields(vsk)
        bounds = (x_min, y_min, x_max, y_max)

        vsk.stroke(1)
        self.draw_line_family(
            vsk,
            fields,
            bounds=bounds,
            density=self.line_density,
            angle_degrees=0.0,
            strength=1.0,
            phase_offset=0.0,
        )

        vsk.stroke(2)
        self.draw_line_family(
            vsk,
            fields,
            bounds=bounds,
            density=self.line_density * self.secondary_density,
            angle_degrees=self.secondary_angle,
            strength=self.secondary_strength,
            phase_offset=pi / 2.0,
        )

        # Set preview colors as well as physical plotter-layer metadata.
        vsk.vpype(
            f"color --layer 1 black color --layer 2 {self.secondary_color}"
        )

    def draw_line_family(
        self,
        vsk: vsketch.Vsketch,
        fields: tuple[FocusField, ...],
        *,
        bounds: tuple[float, float, float, float],
        density: float,
        angle_degrees: float,
        strength: float,
        phase_offset: float,
    ) -> None:
        """Draw an angled family of lines, clipped before deformation."""
        x_min, y_min, x_max, y_max = bounds
        center_x = (x_min + x_max) / 2.0
        slope = tan(radians(angle_degrees))
        half_rise = abs(slope) * (x_max - x_min) / 2.0
        baseline_min = y_min - half_rise
        baseline_max = y_max + half_rise
        row_count = max(2, int((baseline_max - baseline_min) * density) + 1)

        for row in range(row_count):
            baseline = baseline_min + (baseline_max - baseline_min) * row / (
                row_count - 1
            )
            x_start, x_end = self.clipped_x_extent(
                baseline,
                slope,
                center_x,
                bounds,
            )
            if x_end - x_start < self.sample_step:
                continue

            point_count = max(2, ceil((x_end - x_start) / self.sample_step) + 1)
            points: list[tuple[float, float]] = []

            for column in range(point_count):
                x = x_start + (x_end - x_start) * column / (point_count - 1)
                y = baseline + slope * (x - center_x)
                px, py = self.warp_point(
                    x,
                    y,
                    fields,
                    bounds=bounds,
                    twist_scale=strength,
                    pinch_scale=strength,
                    phase_offset=phase_offset,
                )
                points.append((px, py))

            vsk.polygon(points)

    @staticmethod
    def clipped_x_extent(
        baseline: float,
        slope: float,
        center_x: float,
        bounds: tuple[float, float, float, float],
    ) -> tuple[float, float]:
        """Return the portion of an angled baseline inside the frame."""
        x_min, y_min, x_max, y_max = bounds
        if abs(slope) < 1e-9:
            if y_min <= baseline <= y_max:
                return x_min, x_max
            return x_min, x_min

        at_y_min = center_x + (y_min - baseline) / slope
        at_y_max = center_x + (y_max - baseline) / slope
        return (
            max(x_min, min(at_y_min, at_y_max)),
            min(x_max, max(at_y_min, at_y_max)),
        )

    def make_fields(
        self, vsk: vsketch.Vsketch
    ) -> tuple[FocusField, ...]:
        """Choose the strongest of several repeatable seeded arrangements."""
        candidates = [
            self.random_field_layout(vsk)
            for _ in range(int(self.layout_candidates))
        ]
        return max(candidates, key=self.layout_score)

    def random_field_layout(
        self, vsk: vsketch.Vsketch
    ) -> tuple[FocusField, ...]:
        fields = []
        field_count = int(self.field_count)
        direction = -1.0 if vsk.random(1.0) < 0.5 else 1.0

        for index in range(field_count):
            # One focus per horizontal band preserves full-page coverage.
            band_y = index / max(1, field_count - 1)
            fy = max(-0.04, min(1.04, band_y + vsk.random(-0.09, 0.09)))
            fields.append(
                FocusField(
                    x=vsk.random(0.16, 0.84),
                    y=fy,
                    radius_scale=vsk.random(0.72, 1.10),
                    direction=direction * vsk.random(0.72, 1.12),
                    phase=vsk.random(-pi, pi),
                    pinch_scale=vsk.random(0.78, 1.12),
                )
            )
            direction *= -1.0

        return tuple(fields)

    @staticmethod
    def layout_score(fields: tuple[FocusField, ...]) -> float:
        """Favor separated foci with useful horizontal and zig-zag coverage."""
        if len(fields) < 2:
            return 0.0

        separations = [
            hypot(a.x - b.x, 0.72 * (a.y - b.y))
            for index, a in enumerate(fields)
            for b in fields[index + 1 :]
        ]
        x_spread = max(field.x for field in fields) - min(
            field.x for field in fields
        )
        zig_zag = sum(
            abs(a.x - b.x) for a, b in zip(fields, fields[1:])
        ) / (len(fields) - 1)
        return 2.0 * min(separations) + 0.65 * x_spread + 0.4 * zig_zag

    def warp_point(
        self,
        x: float,
        y: float,
        fields: tuple[FocusField, ...],
        *,
        bounds: tuple[float, float, float, float],
        twist_scale: float,
        pinch_scale: float,
        phase_offset: float,
    ) -> tuple[float, float]:
        """Apply smooth, localized rotations while pinning the page edges."""
        x_min, y_min, x_max, y_max = bounds
        px, py = x, y

        for field in fields:
            cx = x_min + field.x * (x_max - x_min)
            cy = y_min + field.y * (y_max - y_min)
            radius = self.field_radius * field.radius_scale
            dx = px - cx
            dy = py - cy
            distance_squared = dx * dx + dy * dy

            # A narrow horizontal envelope pulls many neighboring rows toward
            # the focus, producing a dark, sharp caustic rather than a broad
            # whirlpool. It weakens before the twist to avoid tiny closed loops.
            pinch_radius_x = radius * 0.48
            pinch_radius_y = radius * 0.88
            pinch_envelope = exp(
                -0.5
                * (
                    dx * dx / (pinch_radius_x * pinch_radius_x)
                    + dy * dy / (pinch_radius_y * pinch_radius_y)
                )
            )
            contraction = (
                self.pinch
                * field.pinch_scale
                * pinch_envelope
                * pinch_scale
            )
            contraction = min(0.96, contraction)
            py = cy + dy * (1.0 - contraction)

            # A weak radial ripple makes neighboring fields beat against one
            # another while the reduced core rotation keeps the knot legible.
            dx = px - cx
            dy = py - cy
            distance_squared = dx * dx + dy * dy
            distance = distance_squared**0.5
            envelope = exp(-distance_squared / (2.0 * radius * radius))
            ripple = 0.76 + 0.24 * sin(
                pi * distance / radius + field.phase + phase_offset
            )
            core_relief = 1.0 - 0.42 * pinch_envelope
            angle = (
                field.direction
                * self.twist
                * twist_scale
                * envelope
                * ripple
                * core_relief
            )

            ca = cos(angle)
            sa = sin(angle)
            px = cx + dx * ca - dy * sa
            py = cy + dx * sa + dy * ca

        # Fade the deformation at all four edges. This both frames the piece
        # cleanly and guarantees that adjacent rows meet at identical x values.
        edge_distance = min(x - x_min, x_max - x, y - y_min, y_max - y)
        fade = self.smoothstep(edge_distance / self.edge_fade)

        # A twist can carry a point farther than the edge fade anticipates.
        # Cap its travel analytically, retaining a sliver of paper between the
        # deformed line and the frame instead of hard-clipping the curve.
        delta_x = px - x
        delta_y = py - y
        clearance = 0.96
        if delta_x > 0.0:
            fade = min(fade, clearance * (x_max - x) / delta_x)
        elif delta_x < 0.0:
            fade = min(fade, clearance * (x_min - x) / delta_x)
        if delta_y > 0.0:
            fade = min(fade, clearance * (y_max - y) / delta_y)
        elif delta_y < 0.0:
            fade = min(fade, clearance * (y_min - y) / delta_y)

        return x + delta_x * fade, y + delta_y * fade

    @staticmethod
    def smoothstep(value: float) -> float:
        value = max(0.0, min(1.0, value))
        return value * value * (3.0 - 2.0 * value)

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype(
            "linesimplify linesort "
            f"color --layer 1 black color --layer 2 {self.secondary_color}"
        )


if __name__ == "__main__":
    MoireSketch.display()
