"""Nested circles distorted by a continuous noise field."""

from math import cos, pi, radians, sin, sqrt

import vsketch


PAGE_WIDTH = 21.0
PAGE_HEIGHT = 29.7
FULL_TURN = 2.0 * pi


class CirclesSketch(vsketch.SketchClass):
    margin = vsketch.Param(0.0, 0.0, 5.0, step=0.1)
    circle_count = vsketch.Param(96, 1, 240)
    sample_count = vsketch.Param(240, 12, 720)
    noise_amplitude = vsketch.Param(0.75, 0.0, 3.0, step=0.05)
    noise_frequency = vsketch.Param(1.35, 0.1, 6.0, step=0.05)
    noise_evolution = vsketch.Param(1.1, 0.0, 5.0, step=0.05)
    center_drift = vsketch.Param(0.9, 0.0, 3.0, step=0.05)
    spherical_spacing = vsketch.Param(0.85, 0.0, 1.0, step=0.05)
    noise_octaves = vsketch.Param(4, 1, 8)
    noise_falloff = vsketch.Param(0.5, 0.1, 0.9, step=0.05)
    moire_layer = vsketch.Param(False)
    moire_offset = vsketch.Param(0.18, 0.0, 1.0, step=0.01)
    moire_tilt = vsketch.Param(0.0, -90.0, 90.0, step=5.0)
    moire_spacing_shift = vsketch.Param(0.04, -0.25, 0.15, step=0.01)
    moire_color = vsketch.Param("red", choices=("red", "blue", "black"))

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False, center=False)
        vsk.scale("cm")
        vsk.noFill()

        vsk.noiseDetail(int(self.noise_octaves), self.noise_falloff)

        center_x = PAGE_WIDTH / 2.0
        center_y = PAGE_HEIGHT / 2.0
        max_radius = (
            min(PAGE_WIDTH, PAGE_HEIGHT) / 2.0
            - self.margin
            - self.noise_amplitude
            - self.center_drift
            - (self.moire_offset if self.moire_layer else 0.0)
        )

        vsk.stroke(1)
        self.draw_circle_family(
            vsk,
            center_x,
            center_y,
            max_radius,
            spherical_spacing=self.spherical_spacing,
        )

        if self.moire_layer:
            # Zero tilt points toward the bottom of the page. Positive values
            # rotate the interference axis clockwise.
            offset_angle = radians(90.0 + self.moire_tilt)
            vsk.stroke(2)
            self.draw_circle_family(
                vsk,
                center_x + self.moire_offset * cos(offset_angle),
                center_y + self.moire_offset * sin(offset_angle),
                max_radius,
                spherical_spacing=max(
                    0.0,
                    min(1.0, self.spherical_spacing + self.moire_spacing_shift),
                ),
            )

        self.color_layers(vsk)

    def draw_circle_family(
        self,
        vsk: vsketch.Vsketch,
        center_x: float,
        center_y: float,
        max_radius: float,
        *,
        spherical_spacing: float,
    ) -> None:
        """Draw one related family of noise-warped rings."""
        circle_count = int(self.circle_count)
        for circle_index in range(circle_count):
            progress = (circle_index + 1) / circle_count
            spherical_progress = sin(progress * pi / 2.0)
            radius_progress = vsk.lerp(
                progress,
                spherical_progress,
                spherical_spacing,
            )
            radius = max_radius * radius_progress
            drift_x, drift_y = self.circle_drift(vsk, progress)
            points = self.distorted_circle(
                vsk,
                center_x + drift_x,
                center_y + drift_y,
                radius,
                max_radius,
                progress,
            )
            vsk.polygon(points, close=True)

    def circle_drift(
        self,
        vsk: vsketch.Vsketch,
        progress: float,
    ) -> tuple[float, float]:
        """Move successive ring centers along a smooth, asymmetric path."""
        path_position = progress * 1.7
        drift_envelope = sin(progress * pi)
        drift_x = drift_envelope * vsk.map(
            vsk.noise(path_position + 2.17, 7.31, 13.43),
            0.0,
            1.0,
            -self.center_drift,
            self.center_drift,
        )
        drift_y = drift_envelope * vsk.map(
            vsk.noise(path_position + 19.61, 3.73, 29.17),
            0.0,
            1.0,
            -self.center_drift,
            self.center_drift,
        )
        return drift_x, drift_y

    def distorted_circle(
        self,
        vsk: vsketch.Vsketch,
        center_x: float,
        center_y: float,
        radius: float,
        max_radius: float,
        progress: float,
    ) -> list[tuple[float, float]]:
        """Warp one ring through a continuous two-dimensional vector field."""
        points = []
        sample_count = int(self.sample_count)

        # Keep the silhouette calm so the compressed outer rings describe a
        # sphere. A small residual avoids turning it into a perfect circle.
        distortion_envelope = 0.08 + 0.92 * sin(progress * pi)
        amplitude = min(
            self.noise_amplitude * sqrt(progress) * distortion_envelope,
            radius * 0.45,
        )
        noise_z = progress * self.noise_evolution

        for sample_index in range(sample_count):
            angle = sample_index / sample_count * FULL_TURN
            base_x = center_x + radius * cos(angle)
            base_y = center_y + radius * sin(angle)

            # Page-space sampling stops neighboring rings from sharing radial
            # peaks. Two offset fields bend x and y independently.
            noise_x = base_x / max_radius * self.noise_frequency
            noise_y = base_y / max_radius * self.noise_frequency
            x_displacement = vsk.map(
                vsk.noise(noise_x + 5.23, noise_y + 11.71, noise_z),
                0.0,
                1.0,
                -amplitude,
                amplitude,
            )
            y_displacement = vsk.map(
                vsk.noise(
                    noise_x + 23.47,
                    noise_y + 17.89,
                    noise_z + 31.13,
                ),
                0.0,
                1.0,
                -amplitude,
                amplitude,
            )
            points.append((base_x + x_displacement, base_y + y_displacement))

        return points

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")
        self.color_layers(vsk)

    def color_layers(self, vsk: vsketch.Vsketch) -> None:
        command = "color --layer 1 black"
        if self.moire_layer:
            command += f" color --layer 2 {self.moire_color}"
        vsk.vpype(command)


if __name__ == "__main__":
    CirclesSketch.display()
