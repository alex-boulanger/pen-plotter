# Reliefs

A series of plotter-printed relief portraits, one per remembered place.

Each print is a deterministic function of a real terrain tile. Topographic data
drives the whole composition, but the image does not represent altitude, a
summit silhouette, contour lines, shading, or a viewpoint. The terrain only
provides derived fields: slope, aspect, curvature, and roughness.

The project is about remembered places rather than a catalog of summits:
mountains, passes, ridges, urban hills, and inhabited terrain. Altitude is kept
as provenance, not as the visual subject.

## Usage

```bash
# 1. Populate the cache. This is the only step that touches the network.
uv run python sketches/reliefs/fetch_all.py

# 2. Explore in the viewer.
uv run vsk run sketches/reliefs

# 3. Render the full SVG series.
uv run python sketches/reliefs/render_series.py
```

`fetch_all.py` is resumable. Running it again skips cached places and resumes
an interrupted `.partial.npz` cache where it stopped.

## Structure

| File | Role |
|---|---|
| `data/places.json` | place catalog |
| `data/cache/*.npz` | raw elevation tile cache, one file per place |
| `terrain.py` | acquisition, cache, derived fields |
| `marks.py` | mark system, the only part meant to be iterated |
| `sketch_reliefs.py` | vsketch sketch |
| `fetch_all.py` | cache population |
| `render_series.py` | SVG series rendering |
| `debug.py` | control layers, never exported as prints |
| `inspect_terrain.py` | inspect input data outside vsketch |

`marks.generate(terrain, params, rng) -> [(layer, geometry)]` is the stable
interface. Changing the visual language should not require touching
`terrain.py` or the sketch wrapper.

## Fixed Grammar

`SERIES_PARAMS` and the default vsketch parameters form the grammar of the
series. They define the shared language: format, pen width, hatch density,
thresholds, partition detail, and debug controls.

The viewer exposes `empty_threshold`, `exposure`, and `cut_spread` to develop
that grammar, in addition to choosing a place and showing control layers. The
final series renderer uses their defaults, so prints still share one protocol
rather than being tuned place by place.

If one print exceeds the plotter budget, the grammar is too dense and must be
changed for the whole series, never for one place only.

Key fixed choices:

- `hatch_min = 0.03 cm` is the full-black pitch. With a 0.3 mm pen, adjacent
  strokes touch and fill the surface.
- `level_edges` defines the six tonal marks explicitly. A single response
  curve did not distribute the marks well enough across the slope range.
- `detail` controls partition fineness. Larger facets average slope too much
  and erase the extremes.

## Marks

| Level | Pitch | Coverage with 0.3 mm pen |
|---|---:|---:|
| empty | - | 0% |
| sparse | 0.60 cm | 5% |
| dense | 0.30 cm | 10% |
| tight | 0.15 cm | 20% |
| flat | 0.075 cm | 40% |
| full black | 0.03 cm | 100% |

Light and dark areas do not encode altitude. They encode local terrain
agitation. White means the terrain does not force a mark. Dense ink means
stronger local slope or tension. Hatch direction follows terrain aspect.
Layer color separates concave and convex curvature.

A crossed hatch was tried and rejected. It used more ink, covered less surface,
and read as a different texture instead of a darker value. Full black keeps the
scale tonal.

## Exposure

`exposure` balances only the boundary between empty and inked facets. At `0`,
`empty_threshold` is applied directly and the total ink coverage may vary
strongly between places. At `1`, the boundary targets 72% of empty page by area.
The current grammar uses `exposure = 0.9`: enough to give the series a common
visual weight without forcing every relief into the same tonal histogram.

The five ink densities are deliberately not quantile-normalized. Their relative
presence remains free to express the local distribution of slopes, while facet
size, hatch direction, pen layer, and erosion continue to express slope
dispersion, aspect, curvature, and roughness.

This is not an altitude correction. `slope` is normalized within each tile, so
raising, lowering, or scaling the whole elevation field would not make a place
darker or lighter. The image follows the form of the relief, not its height.

## Facets

There is no fixed drawing grid. A regular grid makes every boundary step at the
same interval, which immediately reads as pixelation.

The page is recursively split into facets using the same quantized directions
as the hatch system. Cut directions and hatch directions share one vocabulary,
so the page reads like a cleaved mineral object rather than a filled-in grid.

The split roles are strict:

| Source | Decides |
|---|---|
| seed | cut direction and cut position |
| terrain | whether a facet is split, plus angle, density, and pen layer |

A facet is split while slope remains dispersed inside it. A calm slope can stay
large. A disturbed ridge subdivides deeply. Facet size therefore becomes a
measure of local terrain agitation.

The seed always derives from the place, so a place renders identically across
machines. It composes the partition without adding arbitrary per-print tuning.

## Control Layers

`debug` overlays non-printing control layers:

| Layer | Content |
|---|---|
| 3 | partition, plus a diagonal on empty facets |
| 4 | selected field as half-tone markers |
| 5 | gradient vectors |
| 6 | frame, hypsometry, numeric caption |

`render_series.py` always forces `debug=False`, so control layers cannot leak
into exported prints.

## Inspecting Data

The cache only stores raw elevation grids and metadata. Slope, aspect,
curvature, roughness, hypsometry, and the 256 x 256 working grid are recomputed
on load. The acquired data is a fact; the derived fields are an interpretation.

```bash
python inspect_terrain.py                     # numeric summary for all places
python inspect_terrain.py cervin --png out/   # one PNG per field + sheet
python inspect_terrain.py cervin --asc out/   # Esri ASCII grids
python inspect_terrain.py cervin --csv out/   # lat, lon, elevation
```

## Adding A Place

Add an entry to `data/places.json`:

```json
{
  "slug": "kongmaru-la",
  "name": "Kongmaru La",
  "lat": 33.79039,
  "lon": 77.61739,
  "alt_m": 5260
}
```

Then run:

```bash
uv run python sketches/reliefs/fetch_all.py --only kongmaru-la
```

`alt_m` is used as a plausibility check for the tile center. It is not used in
the drawing.

## Data Source

[Open Topo Data](https://www.opentopodata.org/), public `srtm30m` API.

The script respects the public limits: 100 points per request, 1 request per
second, 1000 requests per day. A 48 x 48 grid costs 24 requests per place.

## Pitfalls Already Handled

- `hashlib`, not `hash()`, for stable seeds.
- `cos(lat)` in degree-to-meter conversion.
- NaN values filled before gradient computation.
- Per-place percentile normalization, never global min/max.
- No network call in `draw()`.
- `vp.write_svg(set_date=False)`, not `vsk.save()`, for byte-stable SVGs.
- No `linemerge` in `finalize()`, because it would destroy hatch texture.
- Quantized angles, never continuous ones, otherwise the relief becomes too
  legible by eye.
