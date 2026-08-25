import vsketch
from shapely import box as shapely_box
from pysometric import Box, Scene


class Isometric3dSketch(vsketch.SketchClass):
    # Sketch parameters:
    # radius = vsketch.Param(2.0)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False)
        vsk.scale("cm")

        shape = Box((0, 0, 0))
        frame = shapely_box(0, 0, vsk.width, vsk.height)
        scene = Scene(frame, 1, [shape])

        scene.render(vsk)


    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    Isometric3dSketch.display()
