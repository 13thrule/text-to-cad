"""Compact keys preserve exact allocation sharing independently of creation order."""
from __future__ import annotations

import json
import unittest

from cadgen._document.core import Document, GeometryHandle
from cadgen._document.identities import EvaluationKey, allocation_provenance


def node(document, inputs=(), operation="value"):
    key = EvaluationKey.create(operation, "1", (),
                               tuple(handle.evaluation_id for handle in inputs),
                               alias_provenance=allocation_provenance(inputs, document._allocations))
    identity = key.identity
    handle = GeometryHandle(document.owner_id, identity, identity.value,
                            str(document._next_allocation_rank + 1))
    document._register_allocation(handle, inputs)
    return handle, key


class ProvenanceTests(unittest.TestCase):
    def test_interleaved_disjoint_dags_match_dependency_order_reconstruction(self):
        first, second = Document("first"), Document("second")
        a, _ = node(first)
        b, _ = node(first)
        x, _ = node(first, (a,), "unary")
        y, _ = node(first, (b,), "unary")
        a2, _ = node(second)
        x2, _ = node(second, (a2,), "unary")
        b2, _ = node(second)
        y2, _ = node(second, (b2,), "unary")
        self.assertEqual((1, 3), first._allocations[x.allocation_id].ancestry_interval)
        self.assertEqual((2, 4), first._allocations[y.allocation_id].ancestry_interval)
        self.assertEqual(("disjoint-input-dags-v1",),
                         allocation_provenance((x, y), first._allocations))
        self.assertEqual(node(first, (x, y), "pair")[1].identity,
                         node(second, (x2, y2), "pair")[1].identity)

    def test_shared_ancestor_repeated_root_and_independent_equal_inputs_differ(self):
        document = Document("aliases")
        a, _ = node(document)
        b, _ = node(document)
        x, _ = node(document, (a,), "unary")
        y, _ = node(document, (a,), "unary")
        z, _ = node(document, (b,), "unary")
        self.assertEqual(x.evaluation_id, y.evaluation_id)
        self.assertEqual(y.evaluation_id, z.evaluation_id)
        repeated = node(document, (x, x), "pair")[1].identity
        shared = node(document, (x, y), "pair")[1].identity
        independent = node(document, (x, z), "pair")[1].identity
        self.assertEqual(3, len({repeated, shared, independent}))

    def test_long_disjoint_builder_chain_has_constant_provenance_and_no_ancestor_reads(self):
        document = Document("chain")
        previous, _ = node(document)
        for _ in range(2048):
            primitive, _ = node(document)
            previous, key = node(document, (previous, primitive), "effect")
            self.assertLess(len(json.dumps(key.alias_provenance)), 100)
        primitive, _ = node(document)

        class Counted(dict):
            reads = 0
            def __getitem__(self, key):
                self.reads += 1
                return super().__getitem__(key)

        rows = Counted(document._allocations)
        self.assertEqual(("disjoint-input-dags-v1",),
                         allocation_provenance((previous, primitive), rows))
        self.assertEqual(2, rows.reads)
        # Shared fallback also handles deep histories without recursive DFS.
        provenance = allocation_provenance((previous, previous), rows)
        self.assertEqual((0, 0), provenance[0])
        self.assertEqual(4097, len(provenance[1]))


if __name__ == "__main__":
    unittest.main()
