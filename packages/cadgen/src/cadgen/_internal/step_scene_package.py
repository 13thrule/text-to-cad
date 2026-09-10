"""Reconstruct a loaded STEP scene from its tree.

The tree (store-primary, content-keyed) already stores everything a
scene holds: each unique prototype as an exact ``components/<cid>.brep`` object
(the same BinTools serialization the old scene cache wrote), the occurrence
tree with names/transforms/colors in ``assembly.json``, and per-face colors in
each component's ``.surf`` index. So the tree IS the warm-load cache —
there is no second geometry store. ``load_step_scene_cached`` keeps its name
and contract (warm loads skip the text-STEP parse) but now reads the tree;
a STEP with no current tree pays one full parse, and the canonical document
tree then makes the next load warm. This tree holds the prototypes read from
the saved STEP; authored source result trees never participate. Saved readback
uses the same verified reconstruction when those exact emitted bytes already
have a canonical document tree.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from cadgen._internal.step_scene_loader import (
    _location_from_transform_matrix,
    _shape_hash,
    load_step_scene as _load_step_scene_text,
)
from cadgen._internal.step_scene_types import ColorRGBA, LoadedStepScene, OccurrenceNode

_IDENTITY_TRANSFORM = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


def _shape_from_brep(payload: bytes) -> Any | None:
    from OCP.BinTools import BinTools
    from OCP.TopoDS import TopoDS_Shape

    shape = TopoDS_Shape()
    try:
        BinTools.Read_s(shape, io.BytesIO(payload))
    except Exception:  # noqa: BLE001 - unreadable component object -> reparse the STEP instead
        return None
    return None if shape.IsNull() else shape


def _face_colors_from_surf(payload: bytes, shape: Any) -> dict[int, ColorRGBA] | None:
    """Hash-keyed per-face colors from the component's .surf index.

    The surf keys colors by face ORDINAL (TopExp.MapShapes order), which the
    BinTools round-trip preserves, so mapping ordinal -> loaded face -> hash
    reproduces the scene loader's hash-keyed dict for downstream consumers
    (3MF/GLB export materials)."""
    from cadgen._internal.surface_extract import read_surf

    try:
        index, _ = read_surf(payload)
    except Exception:  # noqa: BLE001 - unreadable surface metadata is a cache miss
        return None
    colors_by_ordinal: dict[int, ColorRGBA] = {}
    for face in index.get("faces") or []:
        color = face.get("color")
        if isinstance(color, list) and len(color) == 4:
            colors_by_ordinal[int(face.get("ord", 0))] = tuple(float(c) for c in color)
    if not colors_by_ordinal:
        return {}
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    face_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_ShapeEnum.TopAbs_FACE, face_map)
    face_colors: dict[int, ColorRGBA] = {}
    for ordinal, color in colors_by_ordinal.items():
        if 1 <= ordinal <= face_map.Extent():
            face_colors[_shape_hash(face_map.FindKey(ordinal))] = color
    return face_colors


def _transform_tuple(raw: object) -> tuple[float, ...]:
    if isinstance(raw, list) and len(raw) == 16:
        return tuple(float(value) for value in raw)
    return _IDENTITY_TRANSFORM


def _path_from_occurrence_id(occurrence_id: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in occurrence_id.lstrip("o").split("."))
    except ValueError:
        return (1,)


def lookup_document_scene(step_path: Path, *, step_hash: str) -> tuple[LoadedStepScene | None, bool]:
    """Return a private canonical scene and whether an indexed closure failed.

    Only the current document-byte index participates. A missing index is an
    ordinary miss; a missing, damaged or unreadable indexed object requires
    derivation during saved-file republishing, never deleting the object that
    another writer may already have repaired.
    """
    from cadgen.store.records import tree_for_document_hash

    tree = tree_for_document_hash(step_hash)
    if not tree:
        return None, False
    try:
        scene = _scene_from_document_tree(step_path, step_hash=step_hash, tree_hash=tree)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        scene = None
    return scene, scene is None


def scene_from_render_package(step_path: Path, *, step_hash: str) -> LoadedStepScene | None:
    """A private scene from verified document objects, or None on a cache miss."""
    return lookup_document_scene(step_path, step_hash=step_hash)[0]


def _scene_from_document_tree(step_path: Path, *, step_hash: str, tree_hash: str) -> LoadedStepScene | None:
    from cadgen.store.objects import read_verified_object
    from cadgen.store.trees import TREE_KIND, flatten_tree

    # Verify and flatten the SAME snapshot. Canonical byte-derived document
    # trees have no source links, so no second tree lookup may occur here.
    tree = json.loads(read_verified_object(tree_hash))
    if not isinstance(tree, dict) or tree.get("kind") != TREE_KIND or tree.get("links"):
        return None
    assembly = tree.get("assembly")
    if not isinstance(assembly, dict) or not isinstance(assembly.get("root"), dict):
        return None
    pending = [assembly["root"]]
    while pending:
        node = pending.pop()
        if not isinstance(node, dict) or node.get("nodeType") == "link":
            return None
        children = node.get("children") or []
        if not isinstance(children, list):
            return None
        pending.extend(children)
    descriptor = flatten_tree(tree, tree_hash=tree_hash)
    if not isinstance(descriptor, dict) or descriptor.get("kind") != "assembly-package":
        return None
    components = descriptor.get("components")
    occurrences = descriptor.get("occurrences")
    if not isinstance(components, dict) or not isinstance(occurrences, list) or not occurrences:
        return None

    prototype_shapes: dict[int, Any] = {}
    prototype_names: dict[int, str | None] = {}
    prototype_colors: dict[int, ColorRGBA] = {}
    prototype_face_colors: dict[int, dict[int, ColorRGBA]] = {}
    key_by_cid: dict[str, int] = {}
    for cid, entry in components.items():
        if not isinstance(entry, dict):
            return None
        shape = _shape_from_brep(read_verified_object(str(entry.get("brep") or "")))
        if shape is None:
            return None
        key = _shape_hash(shape)
        key_by_cid[str(cid)] = key
        prototype_shapes[key] = shape
        color = entry.get("color")
        if isinstance(color, list) and len(color) == 4:
            prototype_colors[key] = tuple(float(c) for c in color)
        face_colors = _face_colors_from_surf(read_verified_object(str(entry.get("surf") or "")), shape)
        if face_colors is None:
            return None
        if face_colors:
            prototype_face_colors[key] = face_colors

    occurrence_by_id: dict[str, dict[str, Any]] = {
        str(occ.get("id")): occ for occ in occurrences if isinstance(occ, dict)
    }
    if len(occurrence_by_id) != len(occurrences):
        return None

    def leaf_node(occ: dict[str, Any]) -> OccurrenceNode | None:
        key = key_by_cid.get(str(occ.get("component")))
        if key is None:
            return None
        transform = _transform_tuple(occ.get("transform"))
        name = str(occ.get("name") or "") or None
        color = occ.get("color")
        node = OccurrenceNode(
            path=_path_from_occurrence_id(str(occ.get("id") or "o1")),
            name=name,
            source_name=name,
            transform=transform,
            prototype_key=key,
            local_transform=transform,
            color=tuple(float(c) for c in color) if isinstance(color, list) and len(color) == 4 else None,
            location=_location_from_transform_matrix(transform),
        )
        if name and prototype_names.get(key) is None:
            prototype_names[key] = name
        return node

    assembly = descriptor.get("assembly")
    roots: list[OccurrenceNode]
    if isinstance(assembly, dict) and isinstance(assembly.get("root"), dict):
        def build(tree_node: dict[str, Any]) -> OccurrenceNode | None:
            children_meta = tree_node.get("children") or []
            node_id = str(tree_node.get("id") or "o1")
            if not children_meta:
                occ = occurrence_by_id.get(node_id)
                return leaf_node(occ) if occ is not None else None
            children = [build(c) for c in children_meta]
            if not children or any(child is None for child in children):
                return None
            name = str(tree_node.get("name") or "") or None
            return OccurrenceNode(
                path=_path_from_occurrence_id(node_id),
                name=name,
                source_name=name,
                transform=_IDENTITY_TRANSFORM,
                prototype_key=None,
                local_transform=_IDENTITY_TRANSFORM,
                color=None,
                location=None,
                children=children,
            )

        root = build(assembly["root"])
        if root is None:
            return None
        roots = [root]
    else:
        # Part-kind package: one occurrence holding the whole geometry.
        roots = [node for node in (leaf_node(occ) for occ in occurrences if isinstance(occ, dict)) if node]
        if not roots:
            return None

    scene = LoadedStepScene(
        step_path=step_path,
        roots=roots,
        prototype_shapes=prototype_shapes,
        prototype_names=prototype_names,
        prototype_colors=prototype_colors,
        prototype_face_colors=prototype_face_colors,
        step_hash=step_hash,
        source_kind="step",
    )
    return scene


def load_step_scene_exact(step_path: Path) -> LoadedStepScene:
    """Parse one immutable snapshot of ``step_path`` and bind its exact digest.

    OCCT accepts a path rather than an in-memory byte buffer.  Read the authored
    document once, parse a private temporary copy of those bytes, then restore
    the authored path on the returned scene.  Replacing the authored file at
    any point cannot make the scene's digest describe different bytes.
    """
    resolved_step_path = step_path.expanduser().resolve()
    if not resolved_step_path.is_file():
        raise FileNotFoundError(f"STEP file does not exist: {resolved_step_path}")
    payload = resolved_step_path.read_bytes()
    step_hash = hashlib.sha256(payload).hexdigest()
    snapshot_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="cadgen-step-import-",
            suffix=resolved_step_path.suffix,
            delete=False,
        ) as snapshot:
            snapshot.write(payload)
            snapshot_path = Path(snapshot.name)
        scene = _load_step_scene_text(snapshot_path, record_read=False)
    finally:
        if snapshot_path is not None:
            try:
                os.unlink(snapshot_path)
            except OSError:
                pass
    scene.step_path = resolved_step_path
    scene.step_hash = step_hash
    return scene


def _record_consumed_hash(step_path: Path, step_hash: str) -> None:
    from cadgen.store.closure import note_consumed_file_hash

    note_consumed_file_hash(step_path, step_hash)


def load_step_scene_cached(step_path: Path) -> LoadedStepScene:
    """Load a STEP scene through its document-addressed canonical tree.

    A hit reconstructs binary BREP objects.  A miss submits the ordinary
    document compile job, yields any parent build slot while waiting, and then
    reconstructs that same representation.  The caller never returns the
    mutable scene used to publish the tree.
    """
    resolved_step_path = step_path.expanduser().resolve()
    if not resolved_step_path.is_file():
        raise FileNotFoundError(f"STEP file does not exist: {resolved_step_path}")
    # Hash the same byte buffer used to select the artifact.  The compile worker
    # takes its own immutable snapshot; if the authored path changed between
    # these reads, its tree has a different digest and this loop selects again.
    attempts_by_hash: dict[str, int] = {}
    while True:
        payload = resolved_step_path.read_bytes()
        step_hash = hashlib.sha256(payload).hexdigest()
        from_package, damaged_document = lookup_document_scene(resolved_step_path, step_hash=step_hash)
        if from_package is not None:
            _record_consumed_hash(resolved_step_path, step_hash)
            return from_package

        # A document entry whose tree or component closure is incomplete must
        # not make the compile worker's current-artifact gate take its reuse
        # path. Dropping this derived pointer is recovery, not invalidation of
        # any authored input; the compile republishes it atomically.
        from cadgen.store.index import remove_entry

        remove_entry("document", step_hash)

        from cadgen.daemon import broker
        from cadgen.daemon.executors import submit_compile

        # A hash-valid object can still be unreadable (for example, a bad SURF
        # container). Preserve that failed-closure verdict after removing its
        # index pointer so compilation derives the canonical components again.
        job = submit_compile(resolved_step_path, force=damaged_document)
        with broker.yielded():
            code = job.wait()
        if code != 0:
            detail = job.output().rstrip()
            if detail:
                # The compile worker captures the CAD kernel's C-level output so
                # it cannot corrupt a caller's structured stdout.  Preserve that
                # diagnostic stream for people and put only the worker's concise
                # failure reason in the caller's exception/JSON result.
                print(detail, file=sys.stderr)
            from cadgen.daemon.jobs import failure_message

            reason, _error_type = failure_message(detail)
            suffix = f": {reason}" if reason else ""
            raise RuntimeError(f"Could not compile STEP cache for {resolved_step_path}{suffix}")
        from_package = scene_from_render_package(resolved_step_path, step_hash=step_hash)
        if from_package is not None:
            _record_consumed_hash(resolved_step_path, step_hash)
            return from_package
        # A replacement raced the submit: the worker correctly published the
        # bytes it snapshotted. A concurrent waiter can also remove an entry
        # after the job it joined published but before that job reported done;
        # retry the same digest in that case rather than turning legal duplicate
        # work into a correctness failure.
        current_hash = hashlib.sha256(resolved_step_path.read_bytes()).hexdigest()
        attempts_by_hash[step_hash] = attempts_by_hash.get(step_hash, 0) + 1
        if current_hash == step_hash and attempts_by_hash[step_hash] >= 3:
            raise RuntimeError(
                f"STEP compile completed without a complete canonical tree for {resolved_step_path}"
            )
