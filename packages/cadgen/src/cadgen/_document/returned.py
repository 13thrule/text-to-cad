"""Bind the authored return value without publishing intermediate tools.

This bridge is engine-private. Local ordinal keys describe this exact revision;
they are not persistent topology or occurrence names across source edits.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .frontend import _state, _matrix
from .roots import AssemblyGroup, GeometryLeaf, IDENTITY_TRANSFORM, RootNode
from .appearance import appearance, authored_face_recipe, native_faces


@dataclass(frozen=True)
class ReturnedShape:
    root: RootNode
    unrepresented_metadata: tuple[str, ...]


def capture_returned_shape(frontend: Any, shape: Any) -> ReturnedShape:
    """Capture the returned hierarchy before the exporter's private escape.

    Supported managed leaves retain their prototype and separate placement.
    Opaque leaves are captured from their actual native value. Their native
    location is part of that captured geometry, so it is not applied twice.
    """
    if not isinstance(shape, frontend._bd.Shape):
        raise TypeError("a document-backed model must return a build123d Shape")
    unrepresented = set()
    face_counts = {}

    def metadata(value):
        result = {}
        color = value._color
        if color is not None:
            result["color"] = tuple(float(channel) for channel in color)
        if value.material:
            result["material"] = value.material
        raw = object.__getattribute__(value, "__dict__")
        for field, target in (("cad_material", "pbr"),):
            # Exact ordinary stored metadata has no author callback to replay.
            # A descriptor/custom private wrapper is observed normally, once.
            descriptor = any(field in cls.__dict__ for cls in type(value).__mro__)
            if descriptor:
                frontend._escape_shape(value)
                data = getattr(value, field, None)
            else:
                data = raw.get(field)
            if data is not None:
                result[target] = data
        return result

    def node(value, key, ancestors):
        if id(value) in ancestors:
            raise ValueError("returned shape hierarchy contains a cycle")
        ancestors = ancestors | {id(value)}
        # These fields carry real authored appearance/assembly data outside
        # build123d's ordinary hierarchy. Until bound into the root, a publisher
        # must fail explicitly rather than emit an apparently complete model.
        raw = object.__getattribute__(value, "__dict__")
        for field in ("_occurrence_tree",):
            if (raw.get(field) is not None
                    or any(field in cls.__dict__ for cls in type(value).__mro__)):
                unrepresented.add(field)
        own = metadata(value)
        face_field = "cad_face_ordinal_colors"
        if any(face_field in cls.__dict__ for cls in type(value).__mro__):
            frontend._escape_shape(value)
            face_colors = getattr(value, face_field, None)
        else:
            face_colors = raw.get(face_field)
        state = _state(value)
        children = state.children if state is not None and state.children is not None else tuple(value.children)
        if children:
            if face_colors is not None:
                raise ValueError("authored face colors require a geometry leaf")
            if state is not None and not state.private:
                transform = state.transform
            else:
                native = frontend._native_originals["wrapped"].fget(value)
                transform = _matrix(frontend._bd.Location(native.Location()))
            return AssemblyGroup(key, tuple(node(child, str(index), ancestors)
                                           for index, child in enumerate(children)),
                                 transform=transform, label=value.label,
                                 appearance=appearance(own, allow_faces=False))
        if state is not None and not state.private and state.handle is not None:
            handle = state.handle
            transform = state.transform
        else:
            native = frontend._native_originals["wrapped"].fget(value)
            if face_colors is None:
                handle = frontend.transaction.capture(native)
            else:
                handle, correspondence = frontend.transaction.capture_with_face_map(native)
                own["face_colors"] = authored_face_recipe(
                    face_colors, face_count=len(correspondence), correspondence=correspondence)
            transform = IDENTITY_TRANSFORM
        if face_colors is not None and "face_colors" not in own:
            if handle.prototype_id not in face_counts:
                face_counts[handle.prototype_id] = frontend.transaction.query(handle, lambda native: native_faces(native).Extent())
            own["face_colors"] = authored_face_recipe(face_colors, face_count=face_counts[handle.prototype_id])
        return GeometryLeaf(key, handle, transform=transform, label=value.label, appearance=appearance(own))

    root = node(shape, "root", frozenset())
    return ReturnedShape(root, tuple(sorted(unrepresented)))


def bind_returned_shape(frontend: Any, shape: Any):
    """Set the outer returned root after capturing its exact authored hierarchy."""
    returned = capture_returned_shape(frontend, shape)
    return frontend.transaction.bind_root(returned.root, unrepresented_metadata=returned.unrepresented_metadata)
