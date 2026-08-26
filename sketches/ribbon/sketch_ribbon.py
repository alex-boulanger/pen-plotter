import math

import vpype as vp
import vsketch


class RibbonSketch(vsketch.SketchClass):
    x_step_size = vsketch.Param(2, step=1)
    y_step_size = vsketch.Param(2, 1, step=1)
    y_margin = vsketch.Param(5.0, 0.0, 140.0, step=0.5, unit="mm")
    line_count = vsketch.Param(150, step=1)
    amplitude = vsketch.Param(150, step=10)
    ribbon_width = vsketch.Param(60.0, 0.0, 150.0, step=5.0, unit="mm")
    fold_count = vsketch.Param(1, 1, 20, step=0.5)
    phase_span = vsketch.Param(1.5, 0.0, 12.0, step=0.5)

    red_size = vsketch.Param(90.0, 35.0, 140.0, step=5.0, unit="mm")
    red_outline_count = vsketch.Param(14, 1, 30, step=1)
    red_outline_spacing = vsketch.Param(
        2.2, 0.5, 6.0, step=0.1, unit="mm"
    )
    red_max_rotation = vsketch.Param(20.0, 0.0, 45.0, step=1.0)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        # Layout is explicit because centering the combined layers can push a
        # wide composition beyond the page once the red square is added.
        vsk.size("a4", landscape=False, center=False)

        # Create the red geometry first so the black ribbon is visually on top
        # at crossings, while retaining red as plotter layer 2.
        self.draw_red_square(vsk)

        vsk.stroke(1)
        x_steps = self.line_count
        drawing_height = vsk.height - 2 * self.y_margin
        y_steps = max(2, int(drawing_height / self.y_step_size) + 1)

        noise_x_frequency = 0.02
        noise_y_frequency = 0.003

        for x_step in range(x_steps):
            row_data = []
            for y_step in range(y_steps):
                y = vsk.map(
                    y_step,
                    0,
                    y_steps - 1,
                    self.y_margin,
                    vsk.height - self.y_margin,
                )
                noise_value = vsk.noise(
                    x_step * noise_x_frequency,
                    y * noise_y_frequency,
                )
                x_offset = vsk.map(
                    noise_value,
                    0,
                    1,
                    -self.amplitude,
                    self.amplitude,
                )
                osc = vsk.map(
                    y_step,
                    0,
                    y_steps - 1,
                    0,
                    math.pi * self.fold_count,
                )
                phase = vsk.map(
                    x_step,
                    0,
                    x_steps - 1,
                    0,
                    math.pi * self.phase_span,
                )
                x = (
                    x_step * self.x_step_size
                    + math.sin(osc + phase) * self.ribbon_width
                    + x_offset
                )

                row_data.append((x, y))

            vsk.polygon(row_data)

        ribbon = vsk.document.layers[1]
        ribbon_bounds = ribbon.bounds()
        if ribbon_bounds is not None:
            ribbon_center_x = (ribbon_bounds[0] + ribbon_bounds[2]) / 2
            ribbon.translate(vsk.width / 2 - ribbon_center_x, 0)

    def draw_red_square(self, vsk: vsketch.Vsketch) -> None:
        """Draw a deterministic stack of empty, concentric red squares."""
        angle = math.radians(
            vsk.random(-self.red_max_rotation, self.red_max_rotation)
        )

        # Account for rotation while placing the square behind the ribbon in
        # the lower-middle portion of the composition.
        half_size = self.red_size / 2
        extent = half_size * (abs(math.cos(angle)) + abs(math.sin(angle)))
        margin = vp.convert_length("5mm")

        safe_x_min = extent + margin
        safe_x_max = vsk.width - extent - margin
        center_x_min = max(safe_x_min, vsk.width * 0.62)
        center_x_max = min(safe_x_max, vsk.width * 0.82)
        center_x = vsk.random(center_x_min, center_x_max)

        safe_y_min = extent + margin
        safe_y_max = vsk.height - extent - margin
        center_y_min = max(safe_y_min, vsk.height * 0.62)
        center_y_max = min(safe_y_max, vsk.height * 0.74)
        center_y = vsk.random(center_y_min, center_y_max)

        vsk.stroke(2)
        cos_angle = math.cos(angle)
        sin_angle = math.sin(angle)

        for index in range(int(self.red_outline_count)):
            size = self.red_size - 2 * index * self.red_outline_spacing
            if size <= 0:
                break

            half = size / 2
            corners = []
            for x, y in (
                (-half, -half),
                (half, -half),
                (half, half),
                (-half, half),
            ):
                corners.append(
                    (
                        center_x + x * cos_angle - y * sin_angle,
                        center_y + x * sin_angle + y * cos_angle,
                    )
                )
            vsk.polygon(corners, close=True)

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype(
            "linemerge linesimplify reloop linesort "
            "color --layer 1 black color --layer 2 red"
        )

        length_m = vsk.document.length() / vp.convert_length("1m")
        print(f"Longueur tracée : {length_m:.2f} m")


if __name__ == "__main__":
    RibbonSketch.display()
