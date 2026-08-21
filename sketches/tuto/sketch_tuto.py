import vsketch
import numpy as np

class TutoSketch(vsketch.SketchClass):
    rows = vsketch.Param(20)
    cols = vsketch.Param(25)
    xRnd = vsketch.Param(0.1)
    yRnd = vsketch.Param(0.1)
    interpolateSteps = vsketch.Param(9)
    perspective = vsketch.Param(True)
    top_inset = vsketch.Param(0.0, 0.0, 10.0, step=0.25)     
    bottom_inset = vsketch.Param(0.0, 0.0, 10.0, step=0.25)
    tilt = vsketch.Param(0.0, -8.0, 8.0, step=0.25)          

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("a4", landscape=False)
        vsk.scale("cm")

        points = []
        for row in range(self.rows):
            currPoints = []
            for col in range(self.cols):
                x = row + vsk.random(self.xRnd)
                y = col + vsk.random(self.yRnd)
                # vsk.point(x, y)
                currPoints.append((x, y))
                
            points.append(currPoints)


        for i in range(len(points) -1):
            currPoints = points[i]
            nextPoints = points[i + 1]
            currPointsUnzip = list(zip(*currPoints))
            nextPointsUnzip = list(zip(*nextPoints))
            xTuples = currPointsUnzip[0]
            yTuples = currPointsUnzip[1]
            xCoords = np.array(xTuples)
            yCoords = np.array(yTuples)

            xNextTuples = nextPointsUnzip[0]
            yNextTuples = nextPointsUnzip[1]
            xNextCoords = np.array(xNextTuples)
            yNextCoords = np.array(yNextTuples)

            for step in range(self.interpolateSteps):
                t = step / self.interpolateSteps
                xInterp = (1 - t) * xCoords + t * xNextCoords
                yInterp = (1 - t) * yCoords + t * yNextCoords
                vsk.polygon(xInterp, yInterp)


    def finalize(self, vsk: vsketch.Vsketch) -> None:
        pipeline = "linemerge linesimplify"

        if self.perspective:
            w, h = 21.0, 29.7
            t, b, k = self.top_inset, self.bottom_inset, self.tilt
            corners = (
                f"{t}cm {0 + k}cm "        # haut-gauche
                f"{w - t}cm 0cm "          # haut-droit
                f"{w - b}cm {h}cm "        # bas-droit
                f"{b}cm {h - k}cm"         # bas-gauche
            )
            pipeline += f" perspective {corners}"

        vsk.vpype(pipeline + " linesort")

if __name__ == "__main__":
    TutoSketch.display()
