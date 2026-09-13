"""Structural native results must be immutable and survive resident recovery."""
from pathlib import Path
import tempfile
import unittest

from cadgen._document import Document, GeometryLeaf, NativeResult, OperatorSpec
from cadgen._document.checkpoint import CheckpointCodec, CheckpointCorrupt, _decode_value, checkpoint_engine_version
from cadgen._document.core import _freeze_auxiliary
from cadgen._document.storage import Catalog


def shape():
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

    return BRepPrimAPI_MakeBox(2., 3., 4.).Shape()


class AuxiliaryTests(unittest.TestCase):
    def test_mutable_input_is_snapshotted_and_recovery_retains_effect_data_on_hit(self):
        source = {"schema": 1, "slots": ["part", {"last": [2, 4]}], "buffer": b"layout"}
        document = Document("auxiliary")
        operation = OperatorSpec("test.auxiliary")
        with document.begin() as transaction:
            handle = transaction.evaluate(operation, (), (),
                                          lambda *_: NativeResult(shape(), auxiliary=source))
            transaction.bind_root(GeometryLeaf("part", handle), unrepresented_metadata=())
            revision = transaction.commit()
        source["slots"][1]["last"].append(5)
        retained = document._get(handle).auxiliary
        self.assertEqual((2, 4), retained["slots"][1]["last"])
        with self.assertRaises(TypeError):
            retained["schema"] = 2
        with tempfile.TemporaryDirectory() as directory:
            with Catalog(Path(directory), engine_version=checkpoint_engine_version()) as catalog:
                codec = CheckpointCodec(catalog)
                stage = codec.stage(document, revision.revision_id)
                self.assertTrue(codec.commit(stage, expected_head=None))
                recovered = codec.recover(document.document_id).document
        with recovered.begin() as transaction:
            def must_reuse(*_):
                raise AssertionError("native compute repeated after recovery")
            reused = transaction.evaluate(operation, (), (), must_reuse)
            self.assertEqual(retained, recovered._get(reused).auxiliary)
            self.assertEqual(1, transaction.stats.reused)

    def test_invalid_auxiliary_cannot_install_a_native_cache_entry(self):
        cyclic = []
        cyclic.append(cyclic)
        for value in (shape(), float("nan"), {1: "not a string key"}, cyclic):
            with self.subTest(kind=type(value).__name__):
                document = Document("invalid-auxiliary")
                with document.begin() as transaction:
                    with self.assertRaises((TypeError, ValueError)):
                        transaction.evaluate(OperatorSpec("test.invalid-auxiliary"), (), (),
                                             lambda *_: NativeResult(shape(), auxiliary=value))
                    self.assertEqual(0, document.prototype_count)
                    self.assertEqual({}, document._allocations)

    def test_compact_shared_dag_cannot_expand_without_a_size_bound(self):
        shared = ("leaf",)
        for _ in range(32):
            shared = (shared, shared)
        with self.assertRaisesRegex(ValueError, "size limit"):
            _freeze_auxiliary(shared)
        with self.assertRaisesRegex(CheckpointCorrupt, "encoded float"):
            _decode_value(["float", "0x1p99999999"])


if __name__ == "__main__":
    unittest.main()
