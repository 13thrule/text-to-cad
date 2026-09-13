"""Bind the authored return value without publishing intermediate tools.

This bridge is engine-private. Local ordinal keys describe this exact revision;
they are not persistent topology or occurrence names across source edits.
"""
from __future__ import annotations

from typing import Any

from .frontend import _state, _matrix
from .roots import AssemblyGroup, GeometryLeaf, IDENTITY_TRANSFORM


def bind_returned_shape(frontend: Any, shape: Any):
    """Capture the returned hierarchy before the exporter's private escape.

    Supported managed leaves retain their prototype and separate placement.
    Opaque leaves are captured from their actual native value. Their native
    location is part of that captured geometry, so it is not applied twice.
    """
    if not isinstance(shape, frontend._bd.Shape):
        raise TypeError("a document-backed model must return a build123d Shape")

    def appearance(value):
        result = {}
        color = value._color
        if color is not None:
            result["color"] = tuple(float(channel) for channel in color)
        if value.material:
            result["material"] = value.material
        return result

    def node(value, key, ancestors):
        if id(value) in ancestors:
            raise ValueError("returned shape hierarchy contains a cycle")
        ancestors = ancestors | {id(value)}
        state = _state(value)
        children = state.children if state is not None and state.children is not None else tuple(value.children)
        metadata = {"label": value.label, "appearance": appearance(value)}
        if children:
            if state is not None and not state.private:
                transform = state.transform
            else:
                native = frontend._native_originals["wrapped"].fget(value)
                transform = _matrix(frontend._bd.Location(native.Location()))
            return AssemblyGroup(key, tuple(node(child, str(index), ancestors)
                                           for index, child in enumerate(children)),
                                 transform=transform, **metadata)
        if state is not None and not state.private and state.handle is not None:
            handle = state.handle
            transform = state.transform
        else:
            native = frontend._native_originals["wrapped"].fget(value)
            handle = frontend.transaction.capture(native)
            transform = IDENTITY_TRANSFORM
        return GeometryLeaf(key, handle, transform=transform, **metadata)

    return frontend.transaction.bind_root(node(shape, "root", frozenset()))
