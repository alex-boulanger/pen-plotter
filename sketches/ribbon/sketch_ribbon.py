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

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False)

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

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")

        length_m = vsk.document.length() / vp.convert_length("1m")
        print(f"Longueur tracée : {length_m:.2f} m")


if __name__ == "__main__":
    RibbonSketch.display()
