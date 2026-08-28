import unittest

import vpype as vp
from shapely import union_all
from shapely.geometry import box

from shared.isometric3d import RenderContext
from sketches.studies_monument.composition import (
    AXIS_INDEX,
    MARGIN,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    PROJECTION_ANGLE,
    PROJECTION_SCALE,
    VolumeTreatment,
    plan_composition,
    projected_bounds,
)
from sketches.studies_monument.sketch_studies_monument import (
    StudiesMonumentSketch,
    renderables_for_volume,
)


class StudiesMonumentPlannerTest(unittest.TestCase):
    def test_same_seed_produces_identical_plan(self) -> None:
        for seed in range(100):
            self.assertEqual(plan_composition(seed), plan_composition(seed))

    def test_seed_batch_obeys_composition_grammar(self) -> None:
        observed_counts: set[int] = set()
        observed_treatments: set[VolumeTreatment] = set()
        signatures = set()

        for seed in range(1000):
            composition = plan_composition(seed)
            volumes = composition.volumes
            observed_counts.add(len(volumes))
            observed_treatments.update(volume.treatment for volume in volumes[1:])
            signatures.add(volumes)

            self.assertGreaterEqual(len(volumes), 2)
            self.assertLessEqual(len(volumes), 5)
            self.assertEqual(volumes[0].treatment, VolumeTreatment.OPAQUE)
            self.assertEqual(volumes[0].layer, 1)
            self.assertEqual(sum(volume.layer == 2 for volume in volumes), 1)
            self.assertIsNotNone(
                next(volume for volume in volumes if volume.layer == 2).parent_index
            )
            self.assertGreater(
                volumes[0].volume,
                max(volume.volume for volume in volumes[1:]),
            )
            core_parameters = volumes[0].parameter_map
            flow_strength = float(core_parameters["flow_strength"])
            flow_frequency = float(core_parameters["flow_frequency"])
            self.assertEqual(flow_strength, 0.0)
            self.assertEqual(flow_frequency, 1.4)

            for attribute in ("primary_axis", "hatch_axis"):
                axes = [getattr(volume, attribute) for volume in volumes]
                unique_prefix_length = min(3, len(axes))
                self.assertEqual(
                    len(set(axes[:unique_prefix_length])),
                    unique_prefix_length,
                )
                self.assertTrue(
                    all(first != second for first, second in zip(axes, axes[1:]))
                )

            treatments = [volume.treatment for volume in volumes[1:]]
            if len(volumes) < 5:
                self.assertEqual(len(treatments), len(set(treatments)))
            else:
                repetitions = len(treatments) - len(set(treatments))
                self.assertLessEqual(repetitions, 1)

            for index, child in enumerate(volumes[1:], start=1):
                self.assertIsNotNone(child.parent_index)
                self.assertLess(child.parent_index, index)
                self.assertTrue(all(dimension > 0 for dimension in child.size))
                parent = volumes[child.parent_index]
                axis_index = AXIS_INDEX[child.attachment_axis]
                overlap = (
                    parent.size[axis_index] + child.size[axis_index]
                ) / 2.0 - abs(
                    parent.center[axis_index] - child.center[axis_index]
                )
                self.assertAlmostEqual(overlap, child.penetration)

            bounds = projected_bounds(volumes, composition.origin)
            self.assertGreaterEqual(bounds[0], MARGIN - 1e-9)
            self.assertGreaterEqual(bounds[1], MARGIN - 1e-9)
            self.assertLessEqual(bounds[2], PAGE_WIDTH - MARGIN + 1e-9)
            self.assertLessEqual(bounds[3], PAGE_HEIGHT - MARGIN + 1e-9)

        self.assertEqual(observed_counts, {2, 3, 4, 5})
        self.assertEqual(
            observed_treatments,
            {
                VolumeTreatment.RANDOMIZED,
                VolumeTreatment.FLOW,
                VolumeTreatment.ERODED,
                VolumeTreatment.STRATIFIED,
                VolumeTreatment.RECURSIVE,
            },
        )
        self.assertGreater(len(signatures), 990)

    def test_opaque_flow_switch_changes_only_core_hatching(self) -> None:
        for seed in range(100):
            straight = plan_composition(seed, opaque_flow=False)
            flowing = plan_composition(
                seed,
                opaque_flow=True,
                opaque_flow_intensity=0.23,
            )
            straight_parameters = straight.volumes[0].parameter_map
            flowing_parameters = flowing.volumes[0].parameter_map

            self.assertEqual(float(straight_parameters["flow_strength"]), 0.0)
            self.assertEqual(float(flowing_parameters["flow_strength"]), 0.23)
            self.assertGreaterEqual(float(flowing_parameters["flow_frequency"]), 0.7)
            self.assertLessEqual(float(flowing_parameters["flow_frequency"]), 1.8)
            self.assertEqual(straight.volumes[1:], flowing.volumes[1:])
            self.assertEqual(straight.origin, flowing.origin)

    def test_opaque_flow_intensity_must_be_non_negative(self) -> None:
        with self.assertRaises(ValueError):
            plan_composition(0, opaque_flow=True, opaque_flow_intensity=-0.01)

    def test_rendered_geometry_is_valid_nonempty_and_inside_frame(self) -> None:
        frame = box(
            MARGIN,
            MARGIN,
            PAGE_WIDTH - MARGIN,
            PAGE_HEIGHT - MARGIN,
        )
        observed_treatments: set[VolumeTreatment] = set()

        for seed in range(100):
            composition = plan_composition(seed)
            context = RenderContext(
                frame,
                PROJECTION_SCALE,
                PROJECTION_ANGLE,
                composition.origin,
            )
            geometries = []
            layers = set()
            for volume in composition.volumes:
                observed_treatments.add(volume.treatment)
                for renderable in renderables_for_volume(volume):
                    compiled = renderable.compile(context)
                    self.assertTrue(compiled)
                    for item in compiled:
                        self.assertFalse(item.geometry.is_empty)
                        self.assertTrue(item.geometry.is_valid)
                        geometries.append(item.geometry)
                        layers.add(item.layer)

            bounds = union_all(geometries).bounds
            self.assertGreaterEqual(bounds[0], MARGIN - 1e-7)
            self.assertGreaterEqual(bounds[1], MARGIN - 1e-7)
            self.assertLessEqual(bounds[2], PAGE_WIDTH - MARGIN + 1e-7)
            self.assertLessEqual(bounds[3], PAGE_HEIGHT - MARGIN + 1e-7)
            self.assertEqual(layers, {1, 2})

        self.assertEqual(observed_treatments, set(VolumeTreatment))

    def test_preview_and_finalized_sketch_map_black_and_red_pen_layers(self) -> None:
        for finalize in (False, True):
            sketch = StudiesMonumentSketch.execute(seed=2, finalize=finalize)
            self.assertEqual(
                str(sketch.vsk.document.layers[1].property(vp.METADATA_FIELD_COLOR)),
                "#000000",
            )
            self.assertEqual(
                str(sketch.vsk.document.layers[2].property(vp.METADATA_FIELD_COLOR)),
                "#ff0000",
            )


if __name__ == "__main__":
    unittest.main()
