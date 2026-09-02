import math

import vsketch

PAGE_WIDTH = 21.0
PAGE_HEIGHT = 29.7


class ErodeSketch(vsketch.SketchClass):
    margin = vsketch.Param(2.0, 0.5, 5.0, step=0.1)
    grid_spacing_x = vsketch.Param(0.0, 0.1, 5.0, step=0.1)
    grid_spacing_y = vsketch.Param(0.4, 0.0, 5.0, step=0.1)
    line_spacing = vsketch.Param(0.3, 0.0, 5.0, step=0.1)
    line_inset = vsketch.Param(0.3, 0.0, 1.0, step=0.05)
    grid_count = vsketch.Param(5, 1, 10, step=1)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False)
        vsk.scale("cm")

        grid_count = int(self.grid_count)
        available_width = PAGE_WIDTH - 2 * self.margin
        available_height = PAGE_HEIGHT - 2 * self.margin
        grid_spacing_x_total = (grid_count - 1) * self.grid_spacing_x
        grid_spacing_y_total = (grid_count - 1) * self.grid_spacing_y

        cell_width = (available_width - grid_spacing_x_total) / grid_count
        cell_height = (available_height - grid_spacing_y_total) / grid_count
        square_size = min(cell_width, cell_height)

        # Adjust the spacing slightly so the last line reaches the bottom edge.
        line_interval_count = max(1, math.ceil(square_size / self.line_spacing))
        actual_line_spacing = square_size / line_interval_count

        # Draw non-adjacent cells first so wet neighbouring areas have time to dry.
        for parity in (0, 1):
            for row in range(grid_count):
                for column in range(grid_count):
                    if (row + column) % 2 != parity:
                        continue

                    cell_x = self.margin + column * (
                        square_size + self.grid_spacing_x
                    )
                    cell_y = self.margin + row * (
                        square_size + self.grid_spacing_y
                    )

                    x_min = cell_x
                    x_max = cell_x + square_size
                    square = []
                    for line_index in range(line_interval_count + 1):
                        y = cell_y + line_index * actual_line_spacing
                        inset_ratio = 1.0 - line_index / line_interval_count
                        inset = min(
                            self.line_inset * inset_ratio,
                            square_size / 2,
                        )
                        line_x_min = x_min + inset
                        line_x_max = x_max - inset
                        is_even = line_index % 2 == 0
                        x_start = line_x_min if is_even else line_x_max
                        x_end = line_x_max if is_even else line_x_min
                        square.extend(((x_start, y), (x_end, y)))

                    vsk.polygon(square, close=False)

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        # Preserve creation order for the future ink-reload movements.
        vsk.vpype("linemerge linesimplify reloop")


if __name__ == "__main__":
    ErodeSketch.display()
