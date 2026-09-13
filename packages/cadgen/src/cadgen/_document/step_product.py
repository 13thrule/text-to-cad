"""Pinned native STEP products, independent of the previous geometry store.

This bounded resident proof owns immutable bytes and actual-byte readback facts.
It is not a persistent store, a renderer, or a replacement for every export.
The only shared writer helpers used here assemble/canonicalize STEP bytes; no
model records, saved-document indexes, or LoadedStepScene participate.
"""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import tempfile
from threading import Event, RLock
from typing import Any

from .core import Document, ExportConflict
from .identities import normalize
from .native import copy_shape
from .resources import Cancelled, ResourceRequest
from .roots import AssemblyGroup, GeometryLeaf, IDENTITY_TRANSFORM, walk_root


_WRITER_VERSION = "pinned-root-step-v1"
_READBACK_VERSION = "stepcaf-metadata-v1"
_CODEC_LOCK = RLock()
_MAX_PRODUCTS = 8
_MAX_PRODUCT_BYTES = 64 * 1024**2


class UnsupportedStepProduct(ValueError):
    """The bound root does not fully describe this writer's supported inputs."""


@dataclass(frozen=True)
class StepOptions:
    schema: str = "AP214IS"
    originating_system: str = "cadgen"

    def __post_init__(self):
        if self.schema not in {"AP214IS", "AP242DIS"}:
            raise ValueError("STEP product schema must be AP214IS or AP242DIS")
        if type(self.originating_system) is not str or not self.originating_system:
            raise ValueError("STEP originating system requires a nonempty string")


@dataclass(frozen=True)
class SavedGeometry:
    """Facts computed only from the independent parse of the product bytes."""
    solids: int
    faces: int
    edges: int
    vertices: int
    volume: float
    area: float
    bounds: tuple[float, ...]
    valid: bool


@dataclass(frozen=True)
class SavedNode:
    path: tuple[int, ...]
    name: str
    local_transform: tuple[float, ...]
    color: tuple[float, ...] | None
    children: tuple["SavedNode", ...]
    geometry: SavedGeometry | None


@dataclass(frozen=True)
class _ExpectedNode:
    """Authored serialization inputs; these are never saved-byte facts."""
    name: str
    local_transform: tuple[float, ...]
    color: tuple[float, ...] | None
    children: tuple["_ExpectedNode", ...]


@dataclass(frozen=True)
class StepProduct:
    identity: str
    root_identity: str
    basename: str
    payload: bytes
    sha256: str
    saved_roots: tuple[SavedNode, ...]
    returned_root_path: tuple[int, ...]
    prototype_ids: frozenset[str]
    writer_identity: tuple

    @property
    def returned_root(self) -> SavedNode:
        """The actual parsed occurrence corresponding to the authored root.

        A located root has a STEP document envelope. Keep that real saved
        hierarchy in saved_roots and address the returned subtree explicitly.
        """
        siblings = self.saved_roots
        for index in self.returned_root_path:
            selected = siblings[index - 1]
            siblings = selected.children
        return selected


@dataclass(frozen=True)
class PublishReceipt:
    owner_id: str
    revision_id: int
    destination: str
    product_identity: str
    sha256: str
    size: int
    previous_sha256: str | None
    action: str


@dataclass(frozen=True)
class StepProductMetrics:
    computed: int
    reused: int
    prototype_copies: int
    appearance_copies: int
    independent_parses: int
    writes: int
    verified_existing: int


def _digest(value: Any) -> str:
    payload = json.dumps(normalize(value), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _color(appearance: Any) -> tuple[float, ...] | None:
    if appearance in ((), None):
        return None
    if not hasattr(appearance, "keys"):
        raise UnsupportedStepProduct("STEP appearance requires named immutable fields")
    unknown = set(appearance) - {"color", "material"}
    if unknown:
        raise UnsupportedStepProduct(f"unrepresented STEP appearance fields: {sorted(unknown)}")
    material = appearance.get("material", "")
    if type(material) is not str:
        raise UnsupportedStepProduct("build123d material tags must be strings")
    value = appearance.get("color")
    if value is None:
        return None
    if (type(value) is not tuple or len(value) != 4
            or any(type(channel) not in (int, float) or not math.isfinite(channel)
                   or not 0 <= channel <= 1 for channel in value)):
        raise UnsupportedStepProduct("STEP colors require four finite channels in [0, 1]")
    return tuple(float(channel) for channel in value)


def _root_value(root: Any) -> tuple:
    # Validate structure before recursion; unknown node types and cycles fail.
    tuple(walk_root(root))

    def node(value):
        # Logical keys, allocation UUIDs, and build123d material tags do not
        # reach this STEP codec. A fresh revision still owns those scene facts.
        common = (value.transform, value.label, _color(value.appearance))
        if type(value) is GeometryLeaf:
            return ("leaf", value.geometry.prototype_id, *common, ())  # no intrinsic recipe yet
        if not value.children:
            raise UnsupportedStepProduct("STEP products do not yet represent empty assembly groups")
        return ("group", *common, tuple(node(child) for child in value.children))

    return node(root)


def destination_digest(path: Path) -> str | None:
    """Capture the expected prior bytes before an explicit build/publication."""
    try:
        payload = Path(path).read_bytes()
    except FileNotFoundError:
        return None
    return hashlib.sha256(payload).hexdigest()


def _location(matrix: tuple[float, ...]):
    from OCP.gp import gp_Trsf
    from OCP.TopLoc import TopLoc_Location

    if matrix == IDENTITY_TRANSFORM:
        return TopLoc_Location()
    # A TopLoc placement cannot encode arbitrary affine deformation. Reject
    # unsupported matrices instead of letting gp_Trsf silently orthogonalize.
    axes = tuple(tuple(matrix[row * 4 + column] for row in range(3)) for column in range(3))
    for i in range(3):
        for j in range(3):
            dot = sum(a * b for a, b in zip(axes[i], axes[j]))
            if abs(dot - float(i == j)) > 1e-9:
                raise UnsupportedStepProduct("STEP placements require rigid orthonormal transforms")
    a, b, c = axes
    determinant = (a[0] * (b[1] * c[2] - b[2] * c[1])
                   - b[0] * (a[1] * c[2] - a[2] * c[1])
                   + c[0] * (a[1] * b[2] - a[2] * b[1]))
    if abs(determinant - 1.0) > 1e-9:
        raise UnsupportedStepProduct("STEP placements require proper rigid rotations")
    transform = gp_Trsf()
    transform.SetValues(*matrix[:12])
    return TopLoc_Location(transform)


def _matrix(location: Any) -> tuple[float, ...]:
    transform = location.Transformation()
    return tuple(float(transform.Value(row, column))
                 for row in range(1, 4) for column in range(1, 5)) + (0., 0., 0., 1.)


def _runtime_identity(document: Document) -> tuple:
    from cadgen import step_export

    # Writer code is part of product identity. This is library implementation
    # identity, never a source-model hash or a geometry-serialization cache key.
    writer_bytes = Path(step_export.__file__).read_bytes()
    return (_WRITER_VERSION, _READBACK_VERSION, hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            hashlib.sha256(writer_bytes).hexdigest(), platform.python_version(), platform.machine(),
            importlib.metadata.version("cadquery-ocp"), importlib.metadata.version("build123d"),
            normalize(document.runtime), os.environ.get("CADGEN_STEP_STYLE_REORDER", ""))


@contextmanager
def _owned_xcaf_document():
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    # Application.NewDocument's output-handle binding does not update a Python
    # argument. A standalone document avoids creating an unreachable document
    # in the process-global application's registry on every codec operation.
    document = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
    XCAFDoc_DocumentTool.SetLengthUnit_s(document, .001)
    try:
        yield document
    finally:
        document.Main().Root().ForgetAllAttributes(True)


@contextmanager
def _writer_settings(options: StepOptions):
    """Capture all OCCT translation statics, then restore the settings we set.

    Interface_Static.Items enumerates the translation parameters; its values
    include ambient writer/readback options beyond our closed explicit surface.
    This owner-thread proof serializes codec calls and does not claim isolation
    from unrelated native work in another process or arbitrary user threads.
    """
    from OCP.Interface import Interface_Static
    from OCP.STEPCAFControl import STEPCAFControl_Controller
    from OCP.STEPControl import STEPControl_Controller
    from OCP.IGESControl import IGESControl_Controller
    from OCP.XCAFDoc import XCAFDoc_ShapeTool

    STEPCAFControl_Controller.Init_s()
    STEPControl_Controller.Init_s()
    IGESControl_Controller.Init_s()
    changes = {"write.surfacecurve.mode": "1", "write.precision.mode": "0",
               "write.step.schema": options.schema, "write.step.unit": "MM"}
    previous = {name: Interface_Static.CVal_s(name) for name in changes}
    auto_naming = XCAFDoc_ShapeTool.AutoNaming_s()
    try:
        XCAFDoc_ShapeTool.SetAutoNaming_s(False)
        for name, value in changes.items():
            setter = Interface_Static.SetIVal_s if name.endswith(".mode") else Interface_Static.SetCVal_s
            if not setter(name, int(value) if name.endswith(".mode") else value):
                raise UnsupportedStepProduct(f"OCCT rejected STEP setting {name}={value}")
        names = Interface_Static.Items_s()
        settings = tuple(sorted((names.Value(index).ToCString(),
                                 Interface_Static.CVal_s(names.Value(index).ToCString()))
                                for index in range(1, names.Length() + 1)))
        yield settings + (("xcaf.auto-naming", "false"),)
    finally:
        for name, value in previous.items():
            Interface_Static.SetCVal_s(name, value)
        XCAFDoc_ShapeTool.SetAutoNaming_s(auto_naming)


class _StepProductRegistry:
    """Document-owned, byte-bounded immutable products; no native pointers."""
    def __init__(self):
        self.entries: OrderedDict[str, StepProduct] = OrderedDict()
        self.total_bytes = 0
        self._root_identities = {}

    def root_identity(self, revision):
        # Revisions and their closed roots are immutable owner-created values.
        # A digest belongs to that exact revision, never to an authored Shape
        # or a mutable source object. Keep at most the owner's live revisions.
        cached = self._root_identities.get(revision.revision_id)
        if cached is not None and cached[0] is revision:
            return cached[1]
        identity = _digest(_root_value(revision.root))
        self._root_identities[revision.revision_id] = (revision, identity)
        return identity

    def prune(self, document: Document):
        self._root_identities = {
            key: value for key, value in self._root_identities.items()
            if document._revisions.get(key) is value[0]
        }
        live_roots = set()
        for revision in document._revisions.values():
            if revision.root is None or revision.unrepresented_metadata != ():
                continue
            try:
                live_roots.add(self.root_identity(revision))
            except UnsupportedStepProduct:
                # Other retained roots need not be eligible for this product.
                continue
        for key, product in tuple(self.entries.items()):
            if (product.root_identity not in live_roots
                    or not product.prototype_ids <= document._prototypes.keys()):
                self.total_bytes -= len(product.payload)
                del self.entries[key]

    def get(self, identity: str):
        product = self.entries.get(identity)
        if product is not None:
            self.entries.move_to_end(identity)
        return product

    def put(self, product: StepProduct):
        if len(product.payload) > _MAX_PRODUCT_BYTES:
            return  # valid product, explicitly too large for resident retention
        while self.entries and (len(self.entries) >= _MAX_PRODUCTS
                                or self.total_bytes + len(product.payload) > _MAX_PRODUCT_BYTES):
            _, removed = self.entries.popitem(last=False)
            self.total_bytes -= len(removed.payload)
        self.entries[product.identity] = product
        self.total_bytes += len(product.payload)


class StepProductSession:
    """Prepare and publish one exact revision through its authoritative root."""
    def __init__(self, document: Document, revision_id: int, *, work_directory: Path,
                 cancellation: Event | None = None):
        if not isinstance(document, Document) or type(revision_id) is not int:
            raise TypeError("STEP product work requires a Document and exact revision id")
        document._assert_owner()
        self.document = document
        self._pin = document.pin(revision_id)
        self._closed = False
        self._cancellation = cancellation or Event()
        self.work_directory = Path(work_directory).resolve()
        self._product: StepProduct | None = None
        self._counts = dict(computed=0, reused=0, prototype_copies=0,
                            appearance_copies=0, independent_parses=0, writes=0, verified_existing=0)
        try:
            revision = self._pin.revision
            if revision.root is None:
                raise UnsupportedStepProduct("STEP products require an authoritative returned root")
            coverage = revision.unrepresented_metadata
            if coverage is None:
                raise UnsupportedStepProduct("returned metadata coverage is unknown")
            if coverage:
                raise UnsupportedStepProduct("unrepresented returned metadata: " + ", ".join(coverage))
            registry = getattr(document, "_step_products", None)
            if registry is None:
                registry = _StepProductRegistry()
                document._step_products = registry
            if type(registry) is not _StepProductRegistry:
                raise TypeError("document STEP product registry has an invalid type")
            self._root_identity = registry.root_identity(revision)
            for _path, node in walk_root(revision.root):
                if type(node) is GeometryLeaf:
                    document._get(node.geometry)
            self._registry = registry
        except BaseException:
            self._pin.release()
            self._closed = True
            raise

    @property
    def metrics(self):
        self._check()
        return StepProductMetrics(**self._counts)

    def _check(self):
        self.document._assert_owner()
        if self._closed:
            raise RuntimeError("STEP product session is closed")
        if self._cancellation.is_set():
            raise Cancelled("STEP product work was cancelled")

    def prepare(self, basename: str, *, options: StepOptions = StepOptions()) -> StepProduct:
        self._check()
        if (type(basename) is not str or Path(basename).name != basename
                or Path(basename).suffix.lower() not in {".step", ".stp"}):
            raise ValueError("STEP product basename must be a plain .step or .stp filename")
        if type(options) is not StepOptions:
            raise TypeError("STEP product options require StepOptions")
        self._registry.prune(self.document)
        root_identity = self._root_identity
        with _CODEC_LOCK, _writer_settings(options) as settings:
            writer_identity = (*_runtime_identity(self.document), settings,
                               options.schema, options.originating_system, basename)
            identity = _digest((root_identity, writer_identity))
            cached = self._registry.get(identity)
            if cached is not None:
                self._counts["reused"] += 1
                self._product = cached
                return cached
            self.work_directory.mkdir(parents=True, exist_ok=True)
            with self.document.admission.admit(ResourceRequest(kind="export"), cancellation=self._cancellation):
                with tempfile.TemporaryDirectory(prefix="step-product-", dir=self.work_directory) as temporary:
                    target = Path(temporary) / basename
                    from cadgen.step_export import write_xcaf_doc_step_file

                    with _owned_xcaf_document() as document:
                        prototypes, expected, returned_root_path = self._materialize_xcaf(document)
                        write_xcaf_doc_step_file(document, target,
                                                label=self._pin.revision.root.label or Path(basename).stem,
                                                originating_system=options.originating_system)
                    payload = target.read_bytes()
                    if not payload:
                        raise RuntimeError("STEP writer returned empty bytes")
                    digest = hashlib.sha256(payload).hexdigest()
                    # Reader input is a new private file made only from the
                    # captured bytes. The source XCAF/native document is never
                    # passed to this independent saved-document parse.
                    read_path = Path(temporary) / "saved-readback.step"
                    read_path.write_bytes(payload)
                    saved = _read_saved_metadata(read_path, digest)
                    self._counts["independent_parses"] += 1
                    self._validate_saved_hierarchy(expected, saved)
                    product = StepProduct(identity, root_identity, basename, payload, digest,
                                          saved, returned_root_path, frozenset(prototypes), writer_identity)
            self._check()
            self._registry.put(product)
            self._counts["computed"] += 1
            self._product = product
            return product

    def _materialize_xcaf(self, document):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDataStd import TDataStd_Name
        from OCP.TDF import TDF_Label
        from OCP.TopLoc import TopLoc_Location
        from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorSurf
        from cadgen.step_export import quantity_color_rgba_from_color

        shapes = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
        colors = XCAFDoc_DocumentTool.ColorTool_s(document.Main())
        prototypes, variants, definitions = {}, {}, {}

        def metadata(label, name, color):
            TDataStd_Name.Set_s(label, TCollection_ExtendedString(name))
            if color is not None:
                colors.SetColor(label, quantity_color_rgba_from_color(color), XCAFDoc_ColorSurf)

        def build(node, inherited_color):
            own_color = _color(node.appearance)
            color = inherited_color if own_color is None else own_color
            local = _location(node.transform)
            if type(node) is GeometryLeaf:
                key = node.geometry.prototype_id
                if key not in prototypes:
                    prototypes[key] = copy_shape(self.document._get(node.geometry).shape)
                    self._counts["prototype_copies"] += 1
                native = prototypes[key]
                local = local.Multiplied(native.Location())
                variant_key = (key, color)
                if variant_key not in definitions:
                    base = native.Located(TopLoc_Location())
                    if key in variants:
                        base = BRepBuilderAPI_Copy(base, False, False).Shape()
                        self._counts["appearance_copies"] += 1
                    variants.setdefault(key, []).append(base)
                    definition = shapes.AddShape(base, False)
                    definitions[variant_key] = definition
                    metadata(definition, node.label, color)
                expected = _ExpectedNode(node.label, _matrix(local), color, ())
                return definitions[variant_key], local, color, expected
            definition = shapes.NewShape()
            metadata(definition, node.label, color)
            expected_children = []
            for child in node.children:
                child_definition, child_location, child_color, expected_child = build(child, color)
                instance = shapes.AddComponent(definition, child_definition, child_location)
                metadata(instance, child.label, child_color)
                expected_children.append(expected_child)
            expected = _ExpectedNode(node.label, _matrix(local), color, tuple(expected_children))
            return definition, local, color, expected

        root, location, color, expected = build(self._pin.revision.root, None)
        shapes.UpdateAssemblies()
        returned_root_path = (1,)
        if not location.IsIdentity():
            placed = TDF_Label()
            if not shapes.SetLocation(root, location, placed):
                raise UnsupportedStepProduct("OCCT could not preserve the returned root placement")
            metadata(placed, self._pin.revision.root.label, color)
            # STEPCAF serializes a free located reference under an identity
            # document container. It is distinct from the authored hierarchy.
            expected = _ExpectedNode(expected.name, IDENTITY_TRANSFORM, None, (expected,))
            returned_root_path = (1, 1)
        return frozenset(prototypes), expected, returned_root_path

    @staticmethod
    def _validate_saved_hierarchy(expected: _ExpectedNode, saved: tuple[SavedNode, ...]):
        if len(saved) != 1:
            raise RuntimeError("STEP readback changed the number of returned roots")

        def validate(source, written):
            if source.name and source.name != written.name:
                raise RuntimeError(f"STEP readback changed occurrence name {source.name!r}")
            if any(abs(a - b) > 1e-8 for a, b in zip(source.local_transform, written.local_transform)):
                raise RuntimeError("STEP readback changed an occurrence placement")
            if source.color is not None and (written.color is None or
                    any(abs(a - b) > 1e-6 for a, b in zip(source.color, written.color))):
                raise UnsupportedStepProduct("STEP readback cannot preserve this occurrence color")
            if len(source.children) != len(written.children):
                raise RuntimeError("STEP readback changed the returned hierarchy")
            if source.children:
                for child, saved_child in zip(source.children, written.children):
                    validate(child, saved_child)
            elif written.geometry is None:
                raise RuntimeError("STEP readback did not preserve a returned geometry leaf")

        validate(expected, saved[0])

    def publish(self, destination: Path, *, expected_prior_digest: str | None) -> PublishReceipt:
        self._check()
        if self._product is None:
            raise RuntimeError("prepare the STEP product before publication")
        target = Path(destination).expanduser().resolve()
        product = self._product
        if target.name != product.basename:
            raise ValueError("destination basename differs from the prepared STEP product")
        if (expected_prior_digest is not None and
                (type(expected_prior_digest) is not str or len(expected_prior_digest) != 64
                 or any(c not in "0123456789abcdef" for c in expected_prior_digest))):
            raise ValueError("expected prior digest must be lowercase SHA-256 or None")

        def write():
            self._check()
            current = destination_digest(target)
            if current != expected_prior_digest:
                raise ExportConflict("STEP destination changed since the expected prior bytes")
            if current == product.sha256:
                action = "verified-existing"
                self._counts["verified_existing"] += 1
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(prefix=f".{target.stem}-", suffix=target.suffix,
                                                     dir=target.parent, delete=False) as output:
                        temporary = Path(output.name)
                        output.write(product.payload)
                        output.flush()
                        os.fsync(output.fileno())
                    self._check()
                    if destination_digest(target) != expected_prior_digest:
                        raise ExportConflict("STEP destination changed during publication")
                    if destination_digest(temporary) != product.sha256:
                        raise RuntimeError("staged STEP bytes failed verification")
                    os.replace(temporary, target)
                    temporary = None
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
                if destination_digest(target) != product.sha256:
                    raise ExportConflict("STEP destination changed at publication")
                action = "written"
                self._counts["writes"] += 1
            return PublishReceipt(self.document.owner_id, self._pin.revision_id, str(target),
                                  product.identity, product.sha256, len(product.payload), current, action)

        return self.document.publish_export(self._pin, str(target), write)

    def close(self):
        self.document._assert_owner()
        if not self._closed:
            self._pin.release()
            self._closed = True
            self._product = None

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *exc):
        self.close()


def _read_saved_metadata(path: Path, expected_sha256: str) -> tuple[SavedNode, ...]:
    """Independent STEPCAF parse: every returned field comes from these bytes."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Reader

    if destination_digest(path) != expected_sha256:
        raise RuntimeError("independent STEP reader input does not match product bytes")
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(True)
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise ValueError("independent STEP parser rejected the product bytes")
    with _owned_xcaf_document() as document:
        if not reader.Transfer(document):
            raise ValueError("independent STEP transfer rejected the product bytes")
        result = _saved_document_metadata(document)
    if not result or destination_digest(path) != expected_sha256:
        raise ValueError("STEP parse has no geometry or its selected bytes changed")
    return result


def _saved_document_metadata(document):
    from OCP.Quantity import Quantity_ColorRGBA
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label, TDF_LabelSequence, TDF_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorTool, XCAFDoc_ColorSurf, XCAFDoc_ColorGen

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    geometry_definitions = {}

    def name(label):
        attribute = TDataStd_Name()
        return attribute.Get().ToExtString() if label.FindAttribute(TDataStd_Name.GetID_s(), attribute) else ""

    def color(label):
        value = Quantity_ColorRGBA()
        for kind in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen):
            if XCAFDoc_ColorTool.GetColor_s(label, kind, value):
                rgb = value.GetRGB()
                return (float(rgb.Red()), float(rgb.Green()), float(rgb.Blue()), float(value.Alpha()))
        return None

    def node(label, path, parent_location, inherited_color):
        definition = label
        if shape_tool.IsReference_s(label):
            definition = TDF_Label()
            if not shape_tool.GetReferredShape_s(label, definition):
                raise ValueError("STEP reference has no definition")
        instance_shape = shape_tool.GetShape_s(label)
        if instance_shape.IsNull():
            raise ValueError("STEP readback contains a null occurrence")
        local = instance_shape.Location()
        world = parent_location.Multiplied(local)
        label_color = color(label) or color(definition) or inherited_color
        children = TDF_LabelSequence()
        shape_tool.GetComponents_s(definition, children)
        descendants = tuple(node(children.Value(index), path + (index,), world, label_color)
                            for index in range(1, children.Length() + 1))
        geometry = None
        if not descendants:
            entry = TCollection_AsciiString()
            TDF_Tool.Entry_s(definition, entry)
            key = entry.ToCString()
            if key not in geometry_definitions:
                native = shape_tool.GetShape_s(definition).Located(TopLoc_Location())
                geometry_definitions[key] = (native, _geometry_facts(native))
            native, geometry = geometry_definitions[key]
            if not world.IsIdentity():
                geometry = replace(geometry, bounds=_bounds(native.Moved(world)))
        return SavedNode(path, name(label) or name(definition), _matrix(local), label_color,
                         descendants, geometry)

    roots = TDF_LabelSequence()
    shape_tool.GetFreeShapes(roots)
    return tuple(node(roots.Value(index), (index,), TopLoc_Location(), None)
                 for index in range(1, roots.Length() + 1))


def _geometry_facts(native: Any) -> SavedGeometry:
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    if native is None or native.IsNull():
        raise ValueError("STEP readback contains a null geometry leaf")
    counts = []
    for kind in (TopAbs_SOLID, TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX):
        values = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(native, kind, values)
        counts.append(values.Extent())
    volume, area = GProp_GProps(), GProp_GProps()
    BRepGProp.VolumeProperties_s(native, volume)
    BRepGProp.SurfaceProperties_s(native, area)
    values = (float(volume.Mass()), float(area.Mass()), *_bounds(native))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("STEP readback contains nonfinite geometry facts")
    return SavedGeometry(*counts, values[0], values[1], tuple(values[2:]),
                         bool(BRepCheck_Analyzer(native).IsValid()))


def _bounds(native: Any) -> tuple[float, ...]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    bounds = Bnd_Box()
    BRepBndLib.AddOptimal_s(native, bounds, False, False)
    result = tuple(map(float, bounds.Get()))
    if not all(math.isfinite(value) for value in result):
        raise ValueError("STEP readback contains nonfinite geometry bounds")
    return result
