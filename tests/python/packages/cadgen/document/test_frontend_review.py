"""Adversarial behavior checks for the bounded build123d document frontend."""

from __future__ import annotations

import copy
import unittest

import build123d as bd

from cadgen._document import Document
from cadgen._document.frontend import FrontendSession


def _compound_with_copied_child(mode: str) -> bd.Compound:
    base = bd.Box(10, 4, 2)
    base.label = "original"
    base.material = "steel"
    clone = copy.copy(base)
    clone.label = "copy"
    clone.material = "brass"
    relative = bd.Location((20, 3, 0), (0, 0, 90))
    absolute = bd.Location((7, -8, 0), (0, 0, 180))
    if mode == "methods":
        clone = clone.moved(relative).located(absolute)
    elif mode == "wrapped":
        clone.wrapped = clone.wrapped.Moved(relative.wrapped)
        clone.wrapped.Location(absolute.wrapped)
    else:
        raise ValueError(mode)
    return bd.Compound(children=(base, clone), label="assembly", material="wood")


def _facts(compound: bd.Compound) -> tuple:
    children = []
    for child in compound.children:
        bounds = child.bounding_box()
        children.append((
            child.label,
            child.material,
            tuple(round(value, 6) for value in bounds.min),
            tuple(round(value, 6) for value in bounds.max),
        ))
    return compound.label, compound.material, tuple(children)


class FrontendOwnershipReview(unittest.TestCase):
    def test_copied_private_children_keep_native_placement_in_materialized_hierarchy(self):
        """A copied wrapper can become private before a managed compound is exported.

        The compound must use that wrapper's current native value rather than
        the stale resident handle captured before its native placement changed.
        """
        for mode in ("methods", "wrapped"):
            with self.subTest(mode=mode):
                expected = _facts(_compound_with_copied_child(mode))
                document = Document(f"frontend-copy-{mode}")
                with document.begin() as transaction:
                    with FrontendSession(transaction) as frontend:
                        result = frontend.materialize(_compound_with_copied_child(mode))
                    transaction.commit()

                # The returned result must remain usable after the frontend
                # restores its process-global build123d patches.
                self.assertEqual(expected, _facts(result))


if __name__ == "__main__":
    unittest.main()
