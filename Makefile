VPYPE_CONFIG ?= calibration/ly_drawbot.toml
SKETCHES_DIR ?= sketches
BLENDER_SVG_DIR ?= $(HOME)/Documents/Blender/svg-output
BLENDER_GCODE_OUTPUT_DIR ?= $(HOME)/Documents/Blender/optimized-gcode
BLENDER_PAGE_MARGIN ?= 10mm
GCODE_OUTPUT_DIR ?= $(HOME)/Documents/Pen Plotter/optimized-gcode

ifneq (,$(wildcard config.mk))
include config.mk
endif

COMMANDS := render preview optimize gcode gcode-reload length \
	blender-preview blender-optimize blender-gcode
COMMAND := $(firstword $(MAKECMDGOALS))

ifneq ($(filter $(COMMAND),$(COMMANDS)),)
DRAWING := $(word 2,$(MAKECMDGOALS))
endif

SKETCH := $(SKETCHES_DIR)/$(DRAWING)
BLENDER_SVG := $(BLENDER_SVG_DIR)/$(DRAWING)

# Make treats the positional argument as a second target. Declare only that
# exact argument as a no-op target so unknown targets still produce an error.
ifneq ($(strip $(DRAWING)),)
.PHONY: $(DRAWING)
$(DRAWING):
	@:
endif

.PHONY: help test $(COMMANDS)

MEASURE = uv run python shared/measure.py "$(1).svg"

define SHOW
uv run vpype \
	read "$(1).svg" \
	show
endef

define OPTIMIZE
uv run vpype \
	read "$(1).svg" \
	linemerge \
	linesimplify \
	reloop \
	linesort \
	write "$(1)-optimized.svg"
endef

define BLENDER_OPTIMIZE
uv run vpype \
	read "$(1).svg" \
	linemerge \
	linesimplify \
	reloop \
	linesort \
	layout --landscape --fit-to-margins $(BLENDER_PAGE_MARGIN) a4 \
	write "$(1)-optimized.svg"
endef

define GCODE
mkdir -p "$(2)"
uv run vpype -c $(VPYPE_CONFIG) \
	read "$(1).svg" \
	pagerotate -o landscape \
	gwrite "$(2)/$(notdir $(1)).gcode"
endef

define GCODE_RELOAD
mkdir -p "$(GCODE_OUTPUT_DIR)"
uv run vpype -c $(VPYPE_CONFIG) \
	read "$(1).svg" \
	pagerotate -o landscape \
	gwrite --profile ly_drawbot_reload "$(GCODE_OUTPUT_DIR)/$(notdir $(1)).gcode"
endef

help:
	@echo "Pen Plotter commands"
	@echo ""
	@echo "  make render NAME                 Render sketches/NAME to SVG"
	@echo "  make preview PATH                Preview sketches/PATH.svg"
	@echo "  make optimize PATH               Optimize sketches/PATH.svg"
	@echo "  make length PATH                 Measure plotting distances"
	@echo "  make gcode PATH                  Generate LY DrawBot G-code"
	@echo "  make gcode-reload PATH           Generate G-code with ink reloads"
	@echo "  make blender-preview NAME        Preview a Blender SVG export"
	@echo "  make blender-optimize NAME       Fit and optimize it to A4 landscape"
	@echo "  make blender-gcode NAME          Optimize and generate its G-code"
	@echo "  make test                        Run the automated test suite"
	@echo ""
	@echo "Paths omit the .svg extension. Override defaults in config.mk."

test:
	uv run python -m unittest discover -s tests -v

render:
	@test -n "$(DRAWING)" || { echo "Usage: make render sketch-name"; exit 2; }
	uv run vsk save "$(SKETCHES_DIR)/$(DRAWING)" --name "$(notdir $(DRAWING))"

preview:
	@test -n "$(DRAWING)" || { echo "Usage: make preview path/to/drawing"; exit 2; }
	$(call MEASURE,$(SKETCH))
	$(call SHOW,$(SKETCH))

optimize:
	@test -n "$(DRAWING)" || { echo "Usage: make optimize path/to/drawing"; exit 2; }
	$(call OPTIMIZE,$(SKETCH))
	$(call MEASURE,$(SKETCH)-optimized)

gcode:
	@test -n "$(DRAWING)" || { echo "Usage: make gcode path/to/drawing"; exit 2; }
	$(call MEASURE,$(SKETCH))
	$(call GCODE,$(SKETCH),$(GCODE_OUTPUT_DIR))

gcode-reload:
	@test -n "$(DRAWING)" || { echo "Usage: make gcode-reload path/to/drawing"; exit 2; }
	$(call MEASURE,$(SKETCH))
	$(call GCODE_RELOAD,$(SKETCH))

length:
	@test -n "$(DRAWING)" || { echo "Usage: make length path/to/drawing"; exit 2; }
	$(call MEASURE,$(SKETCH))

blender-preview:
	@test -n "$(DRAWING)" || { echo "Usage: make blender-preview 0001"; exit 2; }
	$(call MEASURE,$(BLENDER_SVG))
	$(call SHOW,$(BLENDER_SVG))

blender-optimize:
	@test -n "$(DRAWING)" || { echo "Usage: make blender-optimize 0001"; exit 2; }
	$(call BLENDER_OPTIMIZE,$(BLENDER_SVG))
	$(call MEASURE,$(BLENDER_SVG)-optimized)

blender-gcode:
	@test -n "$(DRAWING)" || { echo "Usage: make blender-gcode 0001"; exit 2; }
	$(call BLENDER_OPTIMIZE,$(BLENDER_SVG))
	$(call MEASURE,$(BLENDER_SVG)-optimized)
	$(call GCODE,$(BLENDER_SVG)-optimized,$(BLENDER_GCODE_OUTPUT_DIR))
