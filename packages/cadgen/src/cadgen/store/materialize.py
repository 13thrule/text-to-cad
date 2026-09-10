"""``materialize(tree)``: a model's geometry from its tree — the contract a parent
composes against.

Rebuilds a build123d ``Compound`` from a tree: canonical component bytes are
cached within a fixed budget, each independent consumer reconstructs fresh
TShapes, and each object is decoded once per descriptor. Components are placed
per the flattened structure, nested
grouping preserved. The result is TAGGED with the tree hash
(``__cadgen_tree__``) so the packager can recognize it intact in a parent's
result and emit a link instead of copying components. The tag is metadata for
the packager, not part of the contract.

The contract a parent may rely on: tree and child order, labels, colors,
placements, exact geometry. Nothing else exists on the returned object — no
sidecar content, no mates, no kinematics.

This module is INTERNAL. Users compose by calling a decorated child; the
wrapper calls this.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any

from cadgen.store.objects import has_object, read_object
from cadgen.store.trees import flatten

TREE_TAG = "__cadgen_tree__"
PARTNER_TAG = "__cadgen_tree_shape__"
# The materialized compound's OWN location, as a row-major 4x4. A part whose model
# returned a placed shape (``Pos(0, 0, 10) * body``, ``body.moved(...)``) has that
# placement as its tree's root occurrence transform, and materialize reproduces it
# as the compound's location. A parent that places the child composes onto it, so
# the placed compound's location is ``placement * root``; the packager divides the
# root back out when it records the LINK, because the child's tree applies the root
# itself when the link is expanded. Without this the root placement was applied
# twice in every parent that linked such a part.
ROOT_LOC_TAG = "__cadgen_tree_root_loc__"


class _Partner:
    """The materialized shape's ``TopoDS_Shape`` handle, IDENTITY-preserving
    under copy: build123d's ``moved()`` (and ``Location * shape``) copies the
    Python wrapper and re-places the same TShape, and a copied ``TopoDS_Shape``
    attribute would be a NEW handle that no longer partners the result's
    ``wrapped``. This holder copies to itself, so ``IsPartner`` still asks the
    right question: same TShape (placed) or a different one (modified by a
    boolean, a mirror — or ``located()``, which deep-copies the geometry with
    ``BRepBuilderAPI_Copy`` and so yields new bytes, new cids and a component;
    that is the same cost it always had, and the skill says to place with
    ``moved()``)."""

    __slots__ = ("shape",)

    def __init__(self, shape: Any) -> None:
        self.shape = shape

    def __copy__(self) -> "_Partner":
        return self

    def __deepcopy__(self, memo: dict) -> "_Partner":
        return self

# A process-local cache of immutable canonical BREP bytes. Live OCCT prototypes
# cannot cross materialize() calls: build123d's moved() deliberately shares a
# TShape, whose meshing and bookkeeping are mutable. The old live-shape memo
# let one independent consumer alter another. Keeping bytes saves object reads
# while every consumer receives a fresh reconstruction; on the nine-component
# warm-build fixture that boundary costs about 4 ms per materialization.
#
# 64 MiB is a conservative fraction of the daemon worker's default 2 GiB
# reservation. It bounds Python-owned retention independently of persistent
# store GC; memory-pressure worker recycling reclaims the whole process.
_BREP_BYTES_MEMO_CAPACITY = 64 * 1024 * 1024
_BREP_BYTES_MEMO: OrderedDict[str, bytes] = OrderedDict()
_BREP_BYTES_MEMO_SIZE = 0
_SHAPE_MEMO_LOCK = threading.Lock()


def reset_memo() -> None:
    """Release process-owned materialization cache bytes.

    Active consumers own their reconstructed TShapes and remain valid.
    """
    global _BREP_BYTES_MEMO_SIZE
    with _SHAPE_MEMO_LOCK:
        _BREP_BYTES_MEMO.clear()
        _BREP_BYTES_MEMO_SIZE = 0


def _bytes_for_object(digest: str) -> bytes:
    """Canonical bytes for an object that still exists in the store.

    A cached payload never masks manual deletion: a new materialize call must
    fail when its pinned object is gone. Already materialized consumers remain
    self-contained through their own OCCT handles.
    """
    global _BREP_BYTES_MEMO_SIZE
    if not has_object(digest):
        with _SHAPE_MEMO_LOCK:
            stale = _BREP_BYTES_MEMO.pop(digest, None)
            if stale is not None:
                _BREP_BYTES_MEMO_SIZE -= len(stale)
        return read_object(digest)  # raises the store's ordinary missing-object error
    with _SHAPE_MEMO_LOCK:
        cached = _BREP_BYTES_MEMO.get(digest)
        if cached is not None:
            _BREP_BYTES_MEMO.move_to_end(digest)
    if cached is not None:
        return cached
    payload = read_object(digest)
    if len(payload) > _BREP_BYTES_MEMO_CAPACITY:
        return payload
    with _SHAPE_MEMO_LOCK:
        existing = _BREP_BYTES_MEMO.get(digest)
        if existing is not None:
            _BREP_BYTES_MEMO.move_to_end(digest)
            return existing
        _BREP_BYTES_MEMO[digest] = payload
        _BREP_BYTES_MEMO_SIZE += len(payload)
        while _BREP_BYTES_MEMO_SIZE > _BREP_BYTES_MEMO_CAPACITY:
            _old_digest, old_payload = _BREP_BYTES_MEMO.popitem(last=False)
            _BREP_BYTES_MEMO_SIZE -= len(old_payload)
    return payload


def _shape_for_object(digest: str) -> Any:
    from cadgen._internal.component_package import _build123d_shape_from_brep_bytes

    return _build123d_shape_from_brep_bytes(_bytes_for_object(digest))


def _location_from_matrix(matrix: list[float]):
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Trsf
    from build123d import Location

    trsf = gp_Trsf()
    if isinstance(matrix, (list, tuple)) and len(matrix) >= 12:
        trsf.SetValues(*[float(v) for v in matrix[:12]])
    return Location(TopLoc_Location(trsf))


def _color_from_entry(entry: dict[str, Any]):
    values = entry.get("color")
    if not isinstance(values, (list, tuple)) or len(values) < 3:
        return None
    try:
        from build123d import Color

        return Color(*[float(v) for v in values[:4]])
    except Exception:  # noqa: BLE001 - an unreadable color is no color
        return None


def tree_tag(shape: Any) -> str | None:
    """The tree hash a materialized compound carries, or None."""
    tag = getattr(shape, TREE_TAG, None)
    return str(tag) if tag else None


def materialize(tree_hash: str, *, label: str | None = None) -> Any:
    """A ``Compound`` for the tree. Raises FileNotFoundError when the tree or a
    component object is missing (the gate should have said stale)."""
    descriptor = flatten(tree_hash)
    if descriptor is None:
        raise FileNotFoundError(f"tree object missing: {tree_hash}")
    return materialize_descriptor(descriptor, label=label, tree_hash=tree_hash)


def materialize_descriptor(
    descriptor: dict[str, Any],
    *,
    shapes: dict[str, Any] | None = None,
    label: str | None = None,
    tree_hash: str | None = None,
) -> Any:
    """:func:`materialize` of a FLATTENED descriptor (``flatten``/``flatten_tree``).

    ``shapes`` supplies unlocated build123d shapes by cid for components that
    are not in the store yet — the build's own, before it publishes them
    (``cadgen.store.build`` assembles the STEP it writes from exactly this);
    every other component is read from its ``brep`` object. The result is
    tagged as a materialized tree only when ``tree_hash`` names one."""
    from build123d import Compound

    components = descriptor.get("components") or {}
    shapes = dict(shapes or {})
    decoded_by_object: dict[str, Any] = {}
    for cid, entry in components.items():
        if cid in shapes:
            continue
        brep = str((entry or {}).get("brep") or "")
        if not brep:
            raise FileNotFoundError(f"tree {tree_hash}: component {cid} has no brep object")
        shape = decoded_by_object.get(brep)
        if shape is None:
            shape = _shape_for_object(brep)
            decoded_by_object[brep] = shape
        shapes[cid] = shape

    placed_by_id: dict[str, Any] = {}
    for occurrence in descriptor.get("occurrences") or []:
        cid = str(occurrence.get("component") or "")
        base = shapes.get(cid)
        if base is None:
            raise FileNotFoundError(f"tree {tree_hash}: missing component {cid}")
        child = base.moved(_location_from_matrix(occurrence.get("transform")))
        child.label = str(occurrence.get("name") or occurrence.get("id") or "")
        color = _color_from_entry(occurrence) or _color_from_entry(components.get(cid) or {})
        if color is not None:
            child.color = color
        placed_by_id[str(occurrence.get("id") or "")] = child

    def build_node(node: dict[str, Any]):
        node_type = str(node.get("nodeType") or "")
        node_id = str(node.get("id") or "")
        if node_type == "part" or (not node.get("children") and node_id in placed_by_id):
            return placed_by_id.get(node_id)
        children = [built for child in node.get("children") or [] if (built := build_node(child)) is not None]
        if not children:
            return None
        group = Compound(children=children)
        group.label = str(node.get("name") or node_id)
        return group

    root_node = (descriptor.get("assembly") or {}).get("root")
    compound = build_node(root_node) if isinstance(root_node, dict) else None
    if compound is None:
        children = list(placed_by_id.values())
        compound = children[0] if len(children) == 1 else Compound(children=children)
    compound.label = str(label or descriptor.get("label") or descriptor.get("rootName") or getattr(compound, "label", "") or "model")
    color = _color_from_entry(descriptor)
    if color is not None and getattr(compound, "color", None) is None:
        compound.color = color
    if tree_hash is None:
        return compound
    # The tag names the tree; the partner handle lets the build tell "placed"
    # (same TShape, different location: IsPartner) from "modified" (a boolean,
    # a mirror — a new TShape). Both survive moved()/located(), which copy the
    # wrapper's attributes.
    setattr(compound, TREE_TAG, tree_hash)
    setattr(compound, PARTNER_TAG, _Partner(compound.wrapped))
    setattr(compound, ROOT_LOC_TAG, _matrix_from_location(getattr(compound, "location", None)))
    return compound


def _matrix_from_location(location: Any) -> list[float]:
    from cadgen._internal.component_package import _transform_from_location

    if location is None:
        return [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    return [float(v) for v in _transform_from_location(location)]
