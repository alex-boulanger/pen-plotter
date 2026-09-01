# LY DrawBot setup

This repository can generate and inspect SVG files without a plotter. The
G-code profiles in `calibration/ly_drawbot.toml`, however, are specific to the
LY DrawBot used to develop this project. Review and adapt them before sending
commands to another machine.

## Coordinate systems

The sketches use portrait A4 coordinates with their origin at the top-left of
the page. The LY DrawBot is physically operated in landscape orientation and
uses its bottom-left corner as machine coordinate `(0, 0)`.

The G-code pipeline reconciles these coordinate systems in two steps:

1. `pagerotate -o landscape` rotates a portrait document to landscape.
2. `vertical_flip = true` adapts SVG coordinates to the machine's Y axis.

Blender exports receive an additional `layout` operation. Their geometry is
proportionally fitted to an A4 landscape page with the margin configured by
`BLENDER_PAGE_MARGIN`.

## Pen control

The current machine profile uses the spindle commands as servo controls:

| Command | Effect on this machine |
|---|---|
| `M3 S0` | pen up |
| `M3 S1000` | pen down |

The `ly_drawbot_reload` profile returns to machine coordinate `(0, 0)` before
every independent path, lowers the pen into the ink for one second, raises it,
and travels to the next path. This assumes that the ink reservoir is safely
positioned at the machine origin.

## Setting the work origin in UGS

After positioning the carriage manually at the physical origin, the following
GRBL command defines that position as `(0, 0)` in the persistent G54 work
coordinate system:

```gcode
G10 L20 P1 X0 Y0
```

To test the return slowly, first raise the pen and then use absolute millimetre
coordinates:

```gcode
M3 S0
G21
G90
G1 X0 Y0 F500
```

Only use GRBL homing (`$H`) when limit switches and homing direction are known
to be correctly configured.

## Safety checklist

Before running generated G-code:

- inspect the SVG and G-code preview;
- confirm the page orientation and dimensions;
- verify the physical origin and available travel;
- test pen-up and pen-down commands away from the paper;
- keep a hand near pause or emergency stop during the first run;
- start with a low feed rate after changing calibration;
- never assume this profile is safe for a different plotter.

## Serial port on macOS

Connect the plotter and list available serial ports:

```bash
ls /dev/cu.*
```

The LY DrawBot port usually contains `usbserial`, for example
`/dev/cu.usbserial-21220`. Use the `/dev/cu.*` device in Universal Gcode Sender
instead of its `/dev/tty.*` counterpart. The suffix may change after reconnecting
the plotter or using another USB port.
