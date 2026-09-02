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
    phase_variation = vsketch.Param(0.35, 0.0, 1.0, step=0.05)
    width_variation = vsketch.Param(0.25, 0.0, 0.6, step=0.05)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        # Layout is explicit because the noise-driven width is unknown until
        # every line has been generated.
        vsk.size("a4", landscape=False, center=False)

        vsk.stroke(1)
        x_steps = self.line_count
        drawing_height = vsk.height - 2 * self.y_margin
        y_steps = max(2, int(drawing_height / self.y_step_size) + 1)

        noise_x_frequency = 0.02
        noise_y_frequency = 0.003

        for x_step in range(x_steps):
            row_data = []
            for y_step in range(y_steps):
                y_progress = y_step / (y_steps - 1)
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
                base_phase = vsk.map(
                    x_step,
                    0,
                    x_steps - 1,
                    0,
                    math.pi * self.phase_span,
                )
                # Slowly open and close the phase fan. The two harmonics avoid
                # a mechanically repeating rhythm while remaining continuous
                # across every neighbouring line.
                phase_breath = (
                    0.65
                    * math.sin(2 * math.pi * 1.15 * y_progress + 0.4)
                    + 0.35
                    * math.sin(2 * math.pi * 2.35 * y_progress + 1.7)
                )
                phase = base_phase * (
                    1 + self.phase_variation * phase_breath
                )
                # Breathe at a different rhythm from the phase fan so both
                # variations do not repeatedly peak at the same heights.
                width_breath = (
                    0.7
                    * math.sin(2 * math.pi * 0.7 * y_progress + 2.1)
                    + 0.3
                    * math.sin(2 * math.pi * 1.85 * y_progress + 0.8)
                )
                width_scale = 1 + self.width_variation * width_breath
                x = (
                    x_step * self.x_step_size
                    + math.sin(osc + phase)
                    * self.ribbon_width
                    * width_scale
                    + x_offset
                )

                row_data.append((x, y))

            vsk.polygon(row_data)

        ribbon = vsk.document.layers[1]
        ribbon_bounds = ribbon.bounds()
        if ribbon_bounds is not None:
            ribbon_center_x = (ribbon_bounds[0] + ribbon_bounds[2]) / 2
            ribbon.translate(vsk.width / 2 - ribbon_center_x, 0)

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype(
            "linemerge linesimplify reloop linesort "
            "color --layer 1 black color --layer 2 red"
        )

        length_m = vsk.document.length() / vp.convert_length("1m")
        print(f"Longueur tracée : {length_m:.2f} m")


if __name__ == "__main__":
    RibbonSketch.display()
