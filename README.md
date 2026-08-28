# Pen Plotter

Personal pen-plotting environment built with Python, `vsketch`, and `vpype`.

## Project structure

```text
.
├── examples/   # vsketch examples
└── sketches/   # personal sketches
```

## Installation

This repository uses `uv`.

```bash
uv sync
```

Add a dependency:

```bash
uv add <package>
```

Remove a dependency:

```bash
uv remove <package>
```

## Create a sketch

From the repository root:

```bash
uv run vsk init sketches/{name}
```

## Run a sketch

From the repository root:

```bash
uv run vsk run sketches/{name}
```

## Work with repository drawings

Repository drawing paths are relative to `sketches/` and omit the `.svg`
extension. For example, these commands operate on
`sketches/fade/output/fade_liked_1.svg`:

```bash
make preview fade/output/fade_liked_1
make optimize fade/output/fade_liked_1
make gcode fade/output/fade_liked_1
make length fade/output/fade_liked_1
```

`preview` and `gcode` display drawing statistics before continuing. `optimize`
creates `sketches/fade/output/fade_liked_1-optimized.svg` and displays its
statistics.

## Preview and optimize a Blender SVG

Pass SVG names and paths as positional arguments without the `.svg` extension.

Blender exports are read from `~/Documents/Blender/svg-output`. To open an SVG
in the `vpype` viewer:

```bash
make blender-preview 0001
```

The terminal displays the drawn length, pen-up travel, path count, and segment
count before opening the preview.

To prepare the SVG for plotting and G-code generation:

```bash
make blender-optimize 0001
```

This command merges contiguous paths, simplifies their geometry, moves the
starting point of closed loops, and sorts paths to reduce pen-up travel. The
source file remains unchanged. The result is saved alongside it as
`0001-optimized.svg`, and the same statistics are displayed for the optimized
file.

To optimize a Blender export and convert it to G-code in one command:

```bash
make blender-gcode 0001
```

## Generate G-code for the LY DrawBot

The plotter profile is located at `calibration/ly_drawbot.toml`. To convert an
A4 SVG under `sketches/`, provide its path relative to that directory:

```bash
make gcode fade/output/fade_liked_1
```

`pagerotate -o landscape` leaves landscape SVGs unchanged and automatically
rotates portrait SVGs. The `.gcode` file is created alongside the SVG with the
same base name. The `ly_drawbot` profile is used by default.

## Measure plotting length

To display the total path length of an SVG in meters:

```bash
make length fade/output/fade_liked_1
```

The `Drawn` column represents travel with the pen down. `Pen-up` reports travel
between paths without drawing.

## Find the LY DrawBot serial port on macOS

Connect the plotter, then list the available serial ports:

```bash
ls /dev/cu.*
```

The LY DrawBot port usually contains `usbserial`, for example:

```text
/dev/cu.usbserial-21220
```

Use the `/dev/cu.*` port in UGS instead of its `/dev/tty.*` counterpart. The
suffix (`21220` in this example) may change after reconnecting the plotter or
switching USB ports. If it does, refresh the port list in UGS.
