VPYPE_CONFIG := calibration/ly_drawbot.toml

.PHONY: gcode gcode-layers length

gcode:
	@test -n "$(SVG)" || { echo "Usage: make gcode SVG=chemin/vers/dessin.svg"; exit 2; }
	uv run vpype -c $(VPYPE_CONFIG) \
		read "$(SVG)" \
		pagerotate -o landscape \
		gwrite "$(basename $(SVG)).gcode"

gcode-layers:
	@test -n "$(SVG)" || { echo "Usage: make gcode-layers SVG=chemin/vers/dessin.svg"; exit 2; }
	uv run vpype -c $(VPYPE_CONFIG) \
		read "$(SVG)" \
		pagerotate -o landscape \
		forlayer \
			gwrite "$(basename $(SVG))_layer_%_lid%.gcode" \
		end

length:
	@test -n "$(SVG)" || { echo "Usage: make length SVG=chemin/vers/dessin.svg"; exit 2; }
	uv run python shared/measure.py "$(SVG)"
