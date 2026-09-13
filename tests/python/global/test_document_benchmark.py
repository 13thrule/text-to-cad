"""Benchmark edits must retain the real assembly and detect collateral changes."""

import ast
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "document_benchmark", ROOT / "scripts/bench/cadgen-performance/document-engine/harness.py")
BENCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BENCH)


def iris_oracle():
    labels = [BENCH.IRIS_BASE_LABEL, *(f"component-{index}" for index in range(117))]
    return {
        "occurrences": 118, "valid": True,
        "parts": [{"label": label, "volume": 100.0, "area": 50.0,
                   "bounds": [[-2.0, -2.0, 0.0], [2.0, 2.0, 10.0]],
                   "counts": {"solids": 1, "faces": 6, "edges": 12, "vertices": 8},
                   "valid": True} for label in labels],
    }


class DocumentBenchmarkTests(unittest.TestCase):
    def test_iris_adaptation_preserves_all_modeling_helpers(self):
        original = BENCH.IRIS_SOURCE.read_text()
        BENCH.validate_full_fixture(original)
        adapted = BENCH.full_source_variant("iris118", original, geometry=5.1, placement=0.75)
        original_ast, adapted_ast = ast.parse(original), ast.parse(adapted)
        helpers = lambda tree: {node.name: ast.dump(node) for node in tree.body
                                if isinstance(node, ast.FunctionDef) and node.name.startswith("_")}
        self.assertEqual(helpers(original_ast), helpers(adapted_ast))
        assignments = {node.targets[0].id: ast.literal_eval(node.value)
                       for node in adapted_ast.body if isinstance(node, ast.Assign)
                       and isinstance(node.targets[0], ast.Name)
                       and node.targets[0].id in {"BASE_MOUNT_HOLE_DIAMETER", "BENCH_PLACEMENT_Z"}}
        self.assertEqual({"BASE_MOUNT_HOLE_DIAMETER": 5.1, "BENCH_PLACEMENT_Z": 0.75}, assignments)
        self.assertIn('@step(out="mechanical_iris_aperture.step")', adapted)
        self.assertEqual(1, adapted.count('stream.write("{}\\n")'))
        with self.assertRaisesRegex(RuntimeError, "edit markers changed"):
            BENCH.full_source_variant("iris118", original.replace("BASE_MOUNT_HOLE_DIAMETER = 5.0", "BASE_MOUNT_HOLE_DIAMETER = 6.0"),
                                      geometry=5.1, placement=0.0)

    def test_hole_edit_oracle_rejects_unchanged_target_or_collateral_change(self):
        prime = iris_oracle()
        changed = deepcopy(prime)
        changed["parts"][0]["volume"] -= 1
        row = {"oracle": changed, "placementValue": 0.0}
        BENCH.validate_oracle("iris118", "local_geometry", prime, row)
        changed["parts"][1]["volume"] -= 1
        with self.assertRaises(AssertionError):
            BENCH.validate_oracle("iris118", "local_geometry", prime, row)
        with self.assertRaisesRegex(AssertionError, "did not remove"):
            BENCH.validate_oracle("iris118", "local_geometry", prime, {"oracle": prime})

    def test_placement_oracle_requires_exact_translation_and_unchanged_geometry(self):
        prime = iris_oracle()
        changed = deepcopy(prime)
        for corner in changed["parts"][0]["bounds"]:
            corner[2] += 0.75
        row = {"oracle": changed, "placementValue": 0.75}
        BENCH.validate_oracle("iris118", "placement", prime, row)
        row["placementValue"] = 1.0
        with self.assertRaises(AssertionError):
            BENCH.validate_oracle("iris118", "placement", prime, row)
        row["placementValue"] = 0.75
        changed["parts"][0]["volume"] -= 1
        with self.assertRaises(AssertionError):
            BENCH.validate_oracle("iris118", "placement", prime, row)

    def test_small_default_fixtures_and_variants_remain_unchanged(self):
        self.assertEqual({"plate", "assembly24"}, set(BENCH.OUTPUTS))
        for model in BENCH.OUTPUTS:
            original = BENCH.full_fixture_path(model).read_text()
            self.assertEqual(BENCH.source_variant(original, geometry=3.2, placement=0.5),
                             BENCH.full_source_variant(model, original, geometry=3.2, placement=0.5))


if __name__ == "__main__":
    unittest.main()
