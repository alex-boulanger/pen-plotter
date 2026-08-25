import math
from pathlib import Path
import sys

import vsketch
from shapely import box as shapely_box

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.isometric3d import Axis, Cube, Rotation, Scene


class Isometric3dSketch(vsketch.SketchClass):
    columns = vsketch.Param(5, min_value=1)
    rows = vsketch.Param(5, min_value=1)
    cube_size = vsketch.Param(1.0, min_value=0.1)
    spacing = vsketch.Param(2.5, min_value=0.1)
    rotate_x = vsketch.Param(0, step=10)
    rotate_y = vsketch.Param(0, step=10)
    rotate_z = vsketch.Param(0, step=10)
    layer_displacement = vsketch.Param(2.0, step=0.2)
    grid_xy_rotation = vsketch.Param(5.0, step=0.2)
    layer_count= vsketch.Param(1, 1, 3, step=1)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False)
        vsk.scale("cm")

        frame = shapely_box(0, 0, vsk.width, vsk.height)
        grid_width = (self.columns - 1) * self.spacing
        grid_height = (self.rows - 1) * self.spacing
        start_x = (vsk.width - grid_width) / 2
        start_y = (vsk.height - grid_height) / 2

        solid = self.layer_count == 1
        for z in range(self.layer_count):
            layer = z + 1
            for y in range(self.rows):
                for x in range(self.columns):
                    cell_x = start_x + x * self.spacing
                    cell_y = start_y + y * self.spacing
                    shape = Cube(
                        size=self.cube_size+(layer/20),
                        layer=layer,
                        solid=solid,
                        rotations=[
                            Rotation(Axis.X, math.radians(self.rotate_x + ((x + y + (layer * self.layer_displacement)) *self.grid_xy_rotation))),
                            Rotation(Axis.Y, math.radians(self.rotate_y + ((x + y + (layer * self.layer_displacement)) *self.grid_xy_rotation))),
                            Rotation(Axis.Z, math.radians(self.rotate_z + ((x + y + (layer * self.layer_displacement)) *self.grid_xy_rotation))),
                        ],
                    )
                    scene = Scene(frame, 1, [shape], origin=(cell_x, cell_y))
                    scene.render(vsk)

        vsk.vpype(
            "color --layer 1 black "
            "color --layer 2 red "
            "color --layer 3 blue "
            "alpha --layer 1 0.7 "
            "alpha --layer 2 0.7 "
            "alpha --layer 3 0.7"
        )

    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    Isometric3dSketch.display()
