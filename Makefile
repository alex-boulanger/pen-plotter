VPYPE_CONFIG := calibration/ly_drawbot.toml
SKETCHES_DIR := sketches
BLENDER_SVG_DIR := $(HOME)/Documents/Blender/svg-output

COMMANDS := preview optimize gcode length \
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

.PHONY: $(COMMANDS)

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

define GCODE
uv run vpype -c $(VPYPE_CONFIG) \
	read "$(1).svg" \
	pagerotate -o landscape \
	gwrite "$(1).gcode"
endef

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
	$(call GCODE,$(SKETCH))

length:
	@test -n "$(DRAWING)" || { echo "Usage: make length path/to/drawing"; exit 2; }
	$(call MEASURE,$(SKETCH))

blender-preview:
	@test -n "$(DRAWING)" || { echo "Usage: make blender-preview 0001"; exit 2; }
	$(call MEASURE,$(BLENDER_SVG))
	$(call SHOW,$(BLENDER_SVG))

blender-optimize:
	@test -n "$(DRAWING)" || { echo "Usage: make blender-optimize 0001"; exit 2; }
	$(call OPTIMIZE,$(BLENDER_SVG))
	$(call MEASURE,$(BLENDER_SVG)-optimized)

blender-gcode:
	@test -n "$(DRAWING)" || { echo "Usage: make blender-gcode 0001"; exit 2; }
	$(call OPTIMIZE,$(BLENDER_SVG))
	$(call MEASURE,$(BLENDER_SVG)-optimized)
	$(call GCODE,$(BLENDER_SVG)-optimized)
