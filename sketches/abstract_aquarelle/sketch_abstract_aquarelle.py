import math

import vsketch


class AbstractAquarelleSketch(vsketch.SketchClass):
    hatch_spacing = vsketch.Param(0.25, 0.05, 1.0, step=0.05)
    layers = vsketch.Param(7, 1, 20, step=1)

    def draw_split_line(
        self,
        vsk: vsketch.Vsketch,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        square_cx: float,
        square_cy: float,
        half_size: float,
    ) -> None:
        line_cx = (x1 + x2) / 2.0
        line_cy = (y1 + y2) / 2.0

        end1 = self.faded_endpoint(
            vsk,
            line_cx,
            line_cy,
            x1,
            y1,
            square_cx,
            square_cy,
            half_size,
        )
        end2 = self.faded_endpoint(
            vsk,
            line_cx,
            line_cy,
            x2,
            y2,
            square_cx,
            square_cy,
            half_size,
        )

        if end1 is None or end2 is None:
            return

        vsk.line(end1[0], end1[1], end2[0], end2[1])

    def faded_endpoint(
        self,
        vsk: vsketch.Vsketch,
        start_x: float,
        start_y: float,
        target_x: float,
        target_y: float,
        square_cx: float,
        square_cy: float,
        half_size: float,
    ) -> tuple[float, float] | None:
        """Trouve le bord arrondi puis recule aléatoirement sur la ligne."""
        roundness = 6.0
        fade_depth = 0.6

        def rounded_distance(px: float, py: float) -> float:
            nx = abs((px - square_cx) / half_size)
            ny = abs((py - square_cy) / half_size)
            return (nx**roundness + ny**roundness) ** (1.0 / roundness)

        # Les petites diagonales situées entièrement dans les coins disparaissent.
        if rounded_distance(start_x, start_y) >= 1.0:
            return None

        # Recherche du point où la diagonale rencontre le carré arrondi.
        inside_t = 0.0
        outside_t = 1.0
        for _ in range(20):
            middle_t = (inside_t + outside_t) / 2.0
            px = start_x + middle_t * (target_x - start_x)
            py = start_y + middle_t * (target_y - start_y)

            if rounded_distance(px, py) < 1.0:
                inside_t = middle_t
            else:
                outside_t = middle_t

        half_length = math.hypot(target_x - start_x, target_y - start_y)
        if half_length == 0.0:
            return None

        # Le même coefficient déplace x et y : le point reste sur la diagonale.
        random_retraction = vsk.random(0.0, fade_depth) / half_length
        end_t = max(0.0, inside_t - random_retraction)

        return (
            start_x + end_t * (target_x - start_x),
            start_y + end_t * (target_y - start_y),
        )

    def hatch_square(
        self, vsk: vsketch.Vsketch, x: float, y: float, size: float
    ) -> None:
        spacing = float(self.hatch_spacing)
        offset = 0.0
        square_cx = x + size / 2.0
        square_cy = y + size / 2.0
        half_size = size / 2.0

        # Coupe chaque hachure aux deux bords doux du carré.
        while offset < size:
            self.draw_split_line(
                vsk,
                x + offset,
                y,
                x + size,
                y + size - offset,
                square_cx,
                square_cy,
                half_size,
            )

            if offset > 0.0:
                self.draw_split_line(
                    vsk,
                    x,
                    y + offset,
                    x + size - offset,
                    y + size,
                    square_cx,
                    square_cy,
                    half_size,
                )

            offset += spacing

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False)
        vsk.scale("cm")

        for layer in range(int(self.layers)):
            vsk.stroke(layer + 1)
            size = vsk.random(4, 12)
            x = vsk.random(-5.0, 5.0)
            y = vsk.random(-9.0, 9.0)
            self.hatch_square(vsk, x, y, size)

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    AbstractAquarelleSketch.display()
