# Erode

Erode explores ink depletion as part of the drawing rather than as a defect to
hide. Each cell is a square filled from top to bottom by one continuous
serpentine path. Before starting the next square, the LY DrawBot returns to an
ink reservoir located at machine coordinate `(0, 0)`.

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

The main parameters control the page margin, the gap between cells, the pitch
of each serpentine, and the number of rows and columns in the grid.

## Generate reload G-code

```bash
make gcode-reload erode/output/erode
```

The reload behaviour is implemented by the `ly_drawbot_reload` profile in
`calibration/ly_drawbot.toml`. Every square must remain an independent path and
their creation order must be preserved, so this drawing must not be processed
with the regular `optimize` target before G-code generation.

Review the repository's [hardware and safety notes](../../docs/hardware.md)
before running the result on a plotter.
