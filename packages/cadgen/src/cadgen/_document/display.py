"""Value-only display products from an exact resident revision.

This boundary separates native ownership from scene ownership. Mesh packets
are shared by immutable byte identity; occurrence paths are revision-scoped,
not a promise of persistent selection correspondence across source edits.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import math
import weakref
from types import MappingProxyType
from typing import Mapping

from .consumers import RevisionConsumer
from .meshing import MAX_PACKET_BYTES, MeshOptions, mesh_for_occurrence, unpack_mesh
from .roots import AssemblyGroup, walk_root

MAX_NODES = 100_000
MAX_MANIFEST_BYTES = 16 * 1024**2
MAX_ASSET_BYTES = 256 * 1024**2
_products = weakref.WeakValueDictionary()
_PBR = {"roughness", "metalness", "clearcoat", "clearcoatRoughness", "opacity"}


def _appearance(value):
    if value in ((), None):
        return {}
    if type(value) not in (dict, MappingProxyType) or set(value) - {"color", "pbr"}:
        raise ValueError("unsupported display appearance fields")
    result = {}
    unit = lambda v: type(v) in (int, float) and 0 <= v <= 1 and math.isfinite(v)
    if "color" in value:
        color = value["color"]
        if type(color) not in (list, tuple) or len(color) not in (3, 4) or not all(map(unit, color)):
            raise ValueError("display color requires linear RGB or RGBA unit values")
        result["color"] = list(color)
    if "pbr" in value:
        pbr = value["pbr"]
        if type(pbr) not in (dict, MappingProxyType) or set(pbr) - _PBR or not all(map(unit, pbr.values())):
            raise ValueError("unsupported display PBR values")
        result["pbr"] = dict(pbr)
    return result


@dataclass(frozen=True)
class MeshAsset:
    identity: str
    payload: bytes
    origin: tuple[float, float, float]
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    triangles: int
    faces: int
    edges: int


@dataclass(frozen=True)
class DisplayProduct:
    owner_id: str
    revision_id: int
    manifest: bytes
    assets: Mapping[str, MeshAsset]
    prototype_assets: Mapping[str, str]


def build_display(document, revision_id: int, *, options: MeshOptions = MeshOptions(),
                  previous: DisplayProduct | None = None, cancellation=None) -> DisplayProduct:
    """Mesh unique prototypes and publish a complete scene with no native handles.

    A previous product only saves hashing/validation of the exact same live
    immutable payload. It does not authorize reuse based on a filename, a
    source version, or an occurrence ordinal.
    """
    if previous is not None and type(previous) is not DisplayProduct:
        raise TypeError("display reuse requires a DisplayProduct")
    trusted = (previous is not None and _products.get(id(previous)) is previous
               and previous.owner_id == document.owner_id)
    old_assets = previous.assets if trusted else {}
    old_prototypes = previous.prototype_assets if trusted else {}
    with document.pin(revision_id) as pin, RevisionConsumer(document, revision_id, cancellation=cancellation) as consumer:
        if pin.revision.unrepresented_metadata is None or pin.revision.unrepresented_metadata:
            raise ValueError("display root does not represent all authored metadata")
        occurrences = consumer.occurrences()
        # Validate all scene metadata before expensive native derivations.
        effective, nodes = {}, []
        metadata_bytes = 0
        for path, node in walk_root(pin.revision.root):
            consumer.checkpoint()
            if len(nodes) >= MAX_NODES or len(path) > 128 or any(len(key) > 1024 for key in path) or len(node.label) > 4096:
                raise ValueError("display hierarchy exceeds the scene limit")
            metadata_bytes += sum(len(key) * 6 + 3 for key in path) + len(node.label) * 6 + 1024
            if metadata_bytes > MAX_MANIFEST_BYTES // 2:
                raise ValueError("display metadata exceeds the scene limit")
            own = _appearance(node.appearance)
            effective[path] = {**effective.get(path[:-1], {}), **own}
            nodes.append({"path": path, "kind": "group" if type(node) is AssemblyGroup else "part",
                          "label": node.label, "transform": node.transform, "appearance": own})
        assets = {}
        prototypes = {}
        prototype_assets = {}
        total_bytes = 0
        for occurrence in occurrences:
            if occurrence.prototype_id in prototypes:
                continue
            consumer.checkpoint()
            payload = mesh_for_occurrence(consumer, occurrence.path, options)
            if len(payload) > MAX_PACKET_BYTES or total_bytes + len(payload) > MAX_ASSET_BYTES:
                raise ValueError("display assets exceed the scene limit")
            old = old_assets.get(old_prototypes.get(occurrence.prototype_id))
            if old is not None and old.payload is payload:
                asset = old
            else:
                header, _ = unpack_mesh(payload)
                asset = MeshAsset(hashlib.sha256(payload).hexdigest(), payload,
                                  tuple(header["origin"]), tuple(header["bounds"]["min"]),
                                  tuple(header["bounds"]["max"]),
                                  header["buffers"]["indices"]["count"] // 3,
                                  len(header["faces"]), len(header["edges"]))
            if asset.identity not in assets:
                total_bytes += len(payload)
            assets[asset.identity] = asset
            prototype_assets[occurrence.prototype_id] = asset.identity
            prototypes[occurrence.prototype_id] = {"mesh": asset.identity, "bytes": len(payload)}
        rows = [{"path": row.path.nodes, "prototype": row.prototype_id,
                 "transform": row.transform, "label": row.label,
                 "appearance": effective[row.path.nodes]} for row in occurrences]
        value = {"version": 1, "owner": document.owner_id, "revision": revision_id,
                               "nodes": nodes, "prototypes": prototypes, "occurrences": rows}
        stream = io.BytesIO()
        for index, part in enumerate(json.JSONEncoder(separators=(",", ":"), allow_nan=False).iterencode(value)):
            if index % 1024 == 0:
                consumer.checkpoint()
            encoded = part.encode("utf-8")
            if stream.tell() + len(encoded) > MAX_MANIFEST_BYTES:
                raise ValueError("display manifest exceeds the scene limit")
            stream.write(encoded)
        manifest = stream.getvalue()
        consumer.checkpoint()
        product = DisplayProduct(document.owner_id, revision_id, manifest,
                                 MappingProxyType(assets), MappingProxyType(prototype_assets))
        _products[id(product)] = product
        return product
