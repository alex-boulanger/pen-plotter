# Erode

Erode explores ink depletion as part of the drawing rather than as a defect to
hide. Each cell is a square filled from top to bottom by one continuous
serpentine path. Before starting the next square, the LY DrawBot returns to an
ink reservoir located at machine coordinate `(0, 0)`. The cells are plotted in
checkerboard order, giving each wet area more time to dry before an adjacent
cell is drawn.

## Render

From the repository root:

```bash
make render erode
```

This creates `sketches/erode/output/erode.svg`. To explore the parameters in
the interactive viewer:

```bash
uv run vsk run sketches/erode
```

The main parameters control the page margin, the horizontal and vertical gaps
between cells (`grid_spacing_x` and `grid_spacing_y`), the pitch of each
serpentine, and the number of rows and columns in the grid.
`first_line_inset` shortens both ends of every square's first line to compensate
for its wider, wetter plotted mark. The inset then decreases linearly to zero
at the bottom of the square, widening each successive line as the ink runs out.
Its default value is `0.1` cm (1 mm per side); set it to `0` to restore
full-width lines throughout.

## Generate Ink based G-code

```bash
make gcode-ink-reload erode/output/erode
```

The reload behaviour is implemented by the `ly_drawbot_reload` profile in
`calibration/ly_drawbot.toml`. Every square must remain an independent path and
their creation order must be preserved, so this drawing must not be processed
with the regular `optimize` target before G-code generation.

---

Review the repository's [hardware and safety notes](../../docs/hardware.md)
before running the result on a plotter.
