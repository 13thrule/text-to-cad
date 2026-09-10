"""A failed or superseded build must not replace the last saved document."""

from __future__ import annotations

import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


class StepPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = generated_cad_directory(prefix="step-publication-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = self.root / "part.py"
        self.step = self.root / "part.step"
        self.sidecar = self.root / "part.step.json"
        env = mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": str(self.root / "store"),
            "CADGEN_DAEMON": "0", "CADGEN_JOBS": "1",
        })
        env.start()
        self.addCleanup(env.stop)
        from cadgen.store.closure import forget_model_files

        forget_model_files()
        self.addCleanup(forget_model_files)

    def build(self, size: int, *, force: bool = False) -> int:
        from cadgen.cli._run_model import run_model_argv

        self.model.write_text(
            "from cadgen import step\nfrom cadgen import build123d as bd\n"
            f"SIZE = {size}\n@step\ndef part():\n    return bd.Box(SIZE, 8, 6)\n"
            "if __name__ == '__main__':\n    part()\n",
            encoding="utf-8",
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = run_model_argv([str(self.model), *(["--force"] if force else [])])
        self.output = output.getvalue()
        return result

    def test_rejected_publication_keeps_document_sidecar_and_record(self) -> None:
        from cadgen.store.publish import PublishDecision
        from cadgen.store.records import read_record

        self.assertEqual(self.build(10), 0, self.output)
        before = self.step.read_bytes()
        self.sidecar.write_text('{"kinematics":{"authored":"previous"}}', encoding="utf-8")
        annotation = self.sidecar.read_bytes()
        record = read_record(f"{self.model}::part")

        def reject(*args, **kwargs):
            self.assertEqual(self.step.read_bytes(), before, "the decision must precede target replacement")
            self.assertEqual(self.sidecar.read_bytes(), annotation)
            return PublishDecision(False, "a newer result is current")

        with mock.patch("cadgen.store.publish.decide", side_effect=reject) as decide:
            self.assertNotEqual(self.build(12), 0, "a superseded explicit save must not report success")
        decide.assert_called_once()
        self.assertEqual(self.step.read_bytes(), before)
        self.assertEqual(self.sidecar.read_bytes(), annotation)
        self.assertEqual(read_record(f"{self.model}::part"), record)
        self.assertEqual(list(self.root.glob(".part-*")), [], "private stages are cleaned")

    def test_failed_readback_keeps_the_saved_pair(self) -> None:
        self.assertEqual(self.build(10), 0, self.output)
        before = self.step.read_bytes()
        self.sidecar.write_text('{"kinematics":{"authored":"previous"}}', encoding="utf-8")
        annotation = self.sidecar.read_bytes()
        with mock.patch("cadgen.store.build._reread_component", side_effect=RuntimeError("injected read-back failure")):
            self.assertNotEqual(self.build(12), 0)
        self.assertEqual(self.step.read_bytes(), before)
        self.assertEqual(self.sidecar.read_bytes(), annotation)
        self.assertEqual(list(self.root.glob(".part-*")), [])

    def test_preview_is_complete_before_readback_and_saved_file_is_still_previous(self) -> None:
        from cadgen.store import build as store_build
        from cadgen.store.trees import tree_complete

        self.assertEqual(self.build(10), 0, self.output)
        before = self.step.read_bytes()
        events = []
        original = store_build._reread_component

        def reread(*args, **kwargs):
            previews = [event["preview"] for event in events if "preview" in event]
            self.assertTrue(previews, "preview must precede STEP read-back")
            self.assertTrue(tree_complete(previews[-1]["tree"]))
            self.assertEqual(self.step.read_bytes(), before)
            return original(*args, **kwargs)

        with mock.patch("cadgen.daemon.executors.sink_installed", return_value=True), \
                mock.patch("cadgen.daemon.executors.emit_event", side_effect=events.append), \
                mock.patch.object(store_build, "_reread_component", side_effect=reread):
            self.assertEqual(self.build(12), 0, self.output)
        saved = [event["saved"] for event in events if "saved" in event]
        self.assertEqual(len(saved), 1)
        self.assertTrue(tree_complete(saved[0]["tree"]))
        self.assertNotEqual(self.step.read_bytes(), before)

    def test_external_document_edit_during_build_is_not_overwritten(self) -> None:
        from cadgen._internal import generation
        from cadgen.store.records import read_record

        self.assertEqual(self.build(10), 0, self.output)
        record = read_record(f"{self.model}::part")
        original = generation.run_script_generator

        def generate(*args, **kwargs):
            result = original(*args, **kwargs)
            self.step.write_bytes(b"externally replaced STEP")
            return result

        with mock.patch.object(generation, "run_script_generator", side_effect=generate):
            self.assertNotEqual(self.build(12), 0)
        self.assertEqual(self.step.read_bytes(), b"externally replaced STEP")
        self.assertIn("changed during the build", self.output)
        self.assertEqual(read_record(f"{self.model}::part"), record)

    def test_incomplete_saved_tree_keeps_last_document(self) -> None:
        from cadgen.store import build as store_build
        from cadgen.store import trees

        self.assertEqual(self.build(10), 0, self.output)
        before = self.step.read_bytes()
        original = store_build.build_tree_through_step

        def lose_component(*args, **kwargs):
            result = original(*args, **kwargs)
            # Simulate cache deletion after the prepared STEP has been read
            # back, before the saved root is admitted for publication.
            from cadgen.store.objects import object_path
            tree = trees.get_tree(result[0])
            component = next(iter(tree["components"].values()))
            object_path(component["brep"]).unlink()
            return result

        with mock.patch.object(store_build, "build_tree_through_step", side_effect=lose_component):
            self.assertNotEqual(self.build(12), 0)
        self.assertEqual(self.step.read_bytes(), before)
        self.assertIn("pinned geometry disappeared", self.output)

    def test_random_staging_names_do_not_change_saved_bytes(self) -> None:
        from cadgen.catalog import result_tree_for
        from cadgen.store.trees import tree_complete

        self.assertEqual(self.build(10), 0, self.output)
        before = self.step.read_bytes()
        tree = result_tree_for(self.step)
        self.assertTrue(tree_complete(tree))
        self.assertEqual(self.build(10, force=True), 0, self.output)
        self.assertEqual(self.step.read_bytes(), before)
        self.assertEqual(result_tree_for(self.step), tree)


if __name__ == "__main__":
    unittest.main()
