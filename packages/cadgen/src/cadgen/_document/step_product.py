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
from .native import copy_shape, dependency_version
from .resources import Cancelled, ResourceRequest
from .roots import AssemblyGroup, GeometryLeaf, IDENTITY_TRANSFORM, walk_root
from .appearance import (appearance, copied_face_recipe, face_recipe, inherited,
                         native_faces, relocated_face_recipe, set_xcaf_physical_material,
                         xcaf_face_recipe, xcaf_physical_material)
from .step_faces import (FaceTransferError, SavedFaceInventory, SavedFaceReader,
                         copied_face_order, relocated_face_order, transfer_face_entities)


_WRITER_VERSION = "pinned-root-step-v3"
_READBACK_VERSION = "stepcaf-metadata-v4-finite-geometry"
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
    """Finite completion facts from the independent parse of product bytes.

    Topology inventories and validity diagnostics belong to explicit saved-file
    queries. They do not participate in the publisher's translation checks.
    """
    volume: float
    area: float
    bounds: tuple[float, ...]


@dataclass(frozen=True)
class SavedNode:
    path: tuple[int, ...]
    name: str
    local_transform: tuple[float, ...]
    color: tuple[float, ...] | None
    children: tuple["SavedNode", ...]
    geometry: SavedGeometry | None
    face_colors: tuple = ()
    physical_material: Any = None


@dataclass(frozen=True)
class _ExpectedNode:
    """Authored serialization inputs; these are never saved-byte facts."""
    name: str
    local_transform: tuple[float, ...]
    color: tuple[float, ...] | None
    children: tuple["_ExpectedNode", ...]
    face_colors: tuple = ()
    physical_material: Any = None
    face_definition: int | None = None


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
    saved_faces: SavedFaceInventory | None = None

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
    sha256: str | None
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
    annotation_writes: int
    annotation_deletions: int
    annotation_verified: int


@dataclass(frozen=True)
class _StagedOutput:
    destination: Path
    staged_path: Path | None
    identity: str
    sha256: str | None
    size: int
    kind: str


def _digest(value: Any) -> str:
    payload = json.dumps(normalize(value), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _color(appearance: Any) -> tuple[float, ...] | None:
    if appearance in ((), None):
        return None
    if not hasattr(appearance, "keys"):
        raise UnsupportedStepProduct("STEP appearance requires named immutable fields")
    unknown = set(appearance) - {"color", "material", "pbr", "face_colors", "physical_material"}
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
        try:
            own = appearance(value.appearance, allow_faces=type(value) is GeometryLeaf)
        except ValueError as error:
            raise UnsupportedStepProduct(str(error)) from error
        physical = own.get("physical_material")
        common = (value.transform, value.label, _color(own),
                  None if physical is None else tuple(sorted(physical.items())))
        if type(value) is GeometryLeaf:
            return ("leaf", value.geometry.prototype_id, *common, own.get("face_colors", ()))
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
    from . import step_faces

    # Writer code is part of product identity. This is library implementation
    # identity, never a source-model hash or a geometry-serialization cache key.
    writer_bytes = Path(step_export.__file__).read_bytes()
    return (_WRITER_VERSION, _READBACK_VERSION, hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            hashlib.sha256(writer_bytes).hexdigest(),
            hashlib.sha256(Path(step_faces.__file__).read_bytes()).hexdigest(),
            platform.python_version(), platform.machine(),
            dependency_version("cadquery-ocp"), dependency_version("build123d"),
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
        self._staged_outputs = {}
        self._counts = dict(computed=0, reused=0, prototype_copies=0,
                            appearance_copies=0, independent_parses=0, writes=0, verified_existing=0,
                            annotation_writes=0, annotation_deletions=0, annotation_verified=0)
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
                        prototypes, expected, returned_root_path, face_inputs = self._materialize_xcaf(document)
                        transferred = ()
                        def capture_faces(writer):
                            nonlocal transferred
                            transferred = transfer_face_entities(writer, face_inputs, checkpoint=self._check)
                        write_xcaf_doc_step_file(document, target,
                                                label=self._pin.revision.root.label or Path(basename).stem,
                                                originating_system=options.originating_system,
                                                _transfer_observer=capture_faces if face_inputs else None)
                    payload = target.read_bytes()
                    if not payload:
                        raise RuntimeError("STEP writer returned empty bytes")
                    digest = hashlib.sha256(payload).hexdigest()
                    # Reader input is a new private file made only from the
                    # captured bytes. The source XCAF/native document is never
                    # passed to this independent saved-document parse.
                    read_path = Path(temporary) / "saved-readback.step"
                    read_path.write_bytes(payload)
                    saved, saved_faces = _read_saved_metadata(read_path, digest, transferred=transferred,
                                                              checkpoint=self._check)
                    self._counts["independent_parses"] += 1
                    self._validate_saved_hierarchy(expected, saved, transferred, saved_faces)
                    product = StepProduct(identity, root_identity, basename, payload, digest,
                                          saved, returned_root_path, frozenset(prototypes), writer_identity, saved_faces)
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
        materials = XCAFDoc_DocumentTool.MaterialTool_s(document.Main())
        prototypes, variants, definitions = {}, {}, {}
        face_inputs = []

        def metadata(label, name, color, physical=None):
            TDataStd_Name.Set_s(label, TCollection_ExtendedString(name))
            if color is not None:
                colors.SetColor(label, quantity_color_rgba_from_color(color), XCAFDoc_ColorSurf)
            if physical is not None:
                set_xcaf_physical_material(materials, label, physical)

        def build(node, parent_appearance):
            effective = inherited(parent_appearance, node.appearance)
            color = _color(effective)
            physical = effective.get("physical_material")
            local = _location(node.transform)
            if type(node) is GeometryLeaf:
                key = node.geometry.prototype_id
                if key not in prototypes:
                    source = self.document._get(node.geometry).shape
                    copier = BRepBuilderAPI_Copy(source, True, True)
                    prototypes[key] = (source, copier.Shape(), copier)
                    self._counts["prototype_copies"] += 1
                source, native, copier = prototypes[key]
                local = local.Multiplied(native.Location())
                recipe = face_recipe(effective.get("face_colors", ()))
                if recipe:
                    face_recipe(recipe, face_count=native_faces(source).Extent())
                variant_key = (key, color, recipe, normalize(None if physical is None else dict(physical)))
                if variant_key not in definitions:
                    mapped_recipe = copied_face_recipe(source, native, copier, recipe)
                    face_order = copied_face_order(source, native, copier) if recipe else None
                    base = native.Located(TopLoc_Location())
                    mapped_recipe = relocated_face_recipe(native, base, mapped_recipe)
                    if face_order is not None:
                        face_order = relocated_face_order(native, base, face_order)
                    if key in variants:
                        variant_copy = BRepBuilderAPI_Copy(base, False, False)
                        copied = variant_copy.Shape()
                        mapped_recipe = copied_face_recipe(base, copied, variant_copy, mapped_recipe)
                        if face_order is not None:
                            face_order = copied_face_order(base, copied, variant_copy, face_order)
                        base = copied
                        self._counts["appearance_copies"] += 1
                    variants.setdefault(key, []).append(base)
                    definition = shapes.AddShape(base, False)
                    face_definition = None
                    if face_order is not None:
                        from .appearance import MAX_FACES
                        if sum(map(len, face_inputs)) + len(face_order) > MAX_FACES:
                            raise FaceTransferError("STEP face proof exceeds the face limit")
                        face_definition = len(face_inputs)
                        face_inputs.append(face_order)
                    definitions[variant_key] = (definition, face_definition)
                    metadata(definition, node.label, color, physical)
                    face_map = native_faces(base) if mapped_recipe else None
                    for ordinal, rgba in mapped_recipe:
                        self._check()
                        sublabel = shapes.AddSubShape(definition, face_map.FindKey(ordinal + 1))
                        metadata(sublabel, "", rgba)
                definition, face_definition = definitions[variant_key]
                expected = _ExpectedNode(node.label, _matrix(local), color, (), recipe, physical, face_definition)
                return definition, local, color, expected
            definition = shapes.NewShape()
            metadata(definition, node.label, color, physical)
            expected_children = []
            for child in node.children:
                child_definition, child_location, child_color, expected_child = build(child, effective)
                instance = shapes.AddComponent(definition, child_definition, child_location)
                metadata(instance, child.label, child_color, expected_child.physical_material)
                expected_children.append(expected_child)
            expected = _ExpectedNode(node.label, _matrix(local), color, tuple(expected_children), (), physical)
            return definition, local, color, expected

        root, location, color, expected = build(self._pin.revision.root, {})
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
        return frozenset(prototypes), expected, returned_root_path, tuple(face_inputs)

    @staticmethod
    def _validate_saved_hierarchy(expected: _ExpectedNode, saved: tuple[SavedNode, ...],
                                  transferred=(), saved_faces=None):
        if len(saved) != 1:
            raise RuntimeError("STEP readback changed the number of returned roots")

        paths = {} if saved_faces is None else dict(saved_faces.occurrences)

        def validate(source, written):
            if source.name and source.name != written.name:
                raise RuntimeError(f"STEP readback changed occurrence name {source.name!r}")
            if any(abs(a - b) > 1e-8 for a, b in zip(source.local_transform, written.local_transform)):
                raise RuntimeError("STEP readback changed an occurrence placement")
            if source.color is not None and (written.color is None or
                    any(abs(a - b) > 1e-6 for a, b in zip(source.color, written.color))):
                raise UnsupportedStepProduct("STEP readback cannot preserve this occurrence color")
            if source.physical_material != written.physical_material:
                raise UnsupportedStepProduct("STEP readback cannot preserve this physical material")
            if source.face_colors and source.face_definition is None:
                raise FaceTransferError("styled source lacks exact face transfer evidence")
            if source.face_definition is not None:
                if not 0 <= source.face_definition < len(transferred):
                    raise FaceTransferError("source face definition lacks transfer evidence")
                if written.path not in paths:
                    raise FaceTransferError("saved occurrence lacks exact transferred face membership")
                original = transferred[source.face_definition]
                actual = saved_faces.definitions[paths[written.path]]
                if len(original) != len(actual) or set(original) != set(actual):
                    raise FaceTransferError("source and saved face entities are not a complete bijection")
                by_entity = {entity: ordinal for ordinal, entity in enumerate(actual)}
                wanted_styles, actual_styles = dict(source.face_colors), dict(written.face_colors)
                for ordinal, entity in enumerate(original):
                    wanted = wanted_styles.get(ordinal, source.color)
                    observed = actual_styles.get(by_entity[entity], written.color)
                    if ((wanted is None) != (observed is None)
                            or wanted is not None and any(abs(a - b) > 1e-6 for a, b in zip(wanted, observed))):
                        raise FaceTransferError("STEP readback changed an exactly transferred face color")
            if len(source.children) != len(written.children):
                raise RuntimeError("STEP readback changed the returned hierarchy")
            if source.children:
                for child, saved_child in zip(source.children, written.children):
                    validate(child, saved_child)
            elif written.geometry is None:
                raise RuntimeError("STEP readback did not preserve a returned geometry leaf")

        validate(expected, saved[0])

    def prepare_annotations(self):
        """Bind this revision's effective finishes to the verified saved paths.

        Native STEP identity excludes PBR and material tags. Matching that exact
        identity proves the cached product has the same validated hierarchy;
        only its independently read SavedNode paths address the companion.
        """
        from .annotations import paths_from_product, prepare_annotations
        self._check()
        if self._product is None:
            raise RuntimeError("prepare the STEP product before its annotations")
        if self._product.root_identity != self._root_identity:
            raise RuntimeError("annotation source and saved hierarchy identities differ")
        rows = []
        def visit(source, saved, parent):
            effective = inherited(parent, source.appearance)
            if type(source) is GeometryLeaf:
                if saved.children or saved.geometry is None:
                    raise RuntimeError("saved annotation path does not address this geometry leaf")
                own = {key: effective[key] for key in ("pbr", "material") if effective.get(key)}
                if own:
                    rows.append({"path": saved.path, **own})
            else:
                if len(source.children) != len(saved.children):
                    raise RuntimeError("saved annotation hierarchy does not match the source root")
                for child, actual in zip(source.children, saved.children):
                    visit(child, actual, effective)
        visit(self._pin.revision.root, self._product.returned_root, {})
        return prepare_annotations(self._product.payload, paths_from_product(self._product), rows)

    @contextmanager
    def _stage(self, products):
        staged = []
        try:
            for target, payload, digest, identity, kind in products:
                self._check()
                target.parent.mkdir(parents=True, exist_ok=True)
                path = None
                if payload is not None:
                    try:
                        existing = (target.stat().st_size == len(payload)
                                    and destination_digest(target) == digest)
                    except FileNotFoundError:
                        existing = False
                    if existing:
                        # Retain only the immutable expected output facts. The
                        # final claim rechecks these bytes before acknowledging.
                        staged.append(_StagedOutput(target, None, identity, digest, len(payload), kind))
                        continue
                    with tempfile.NamedTemporaryFile(prefix=f".{target.name}-", suffix=".stage",
                                                     dir=target.parent, delete=False) as output:
                        path = Path(output.name)
                        # Register before writing so a disk failure is cleaned.
                        staged.append(_StagedOutput(target, path, identity, digest, len(payload), kind))
                        output.write(payload)
                        output.flush()
                        os.fsync(output.fileno())
                    if destination_digest(path) != digest:
                        raise RuntimeError("staged output bytes failed verification")
                else:
                    staged.append(_StagedOutput(target, None, identity, None, 0, kind))
            self._staged_outputs = {id(item): item for item in staged}
            yield tuple(staged)
        finally:
            self._staged_outputs.clear()
            for item in staged:
                if item.staged_path is not None:
                    item.staged_path.unlink(missing_ok=True)

    @contextmanager
    def stage_outputs(self, destinations):
        """Stage both products before acquiring the coordinator's final claims."""
        from .annotations import companion_path
        self._check()
        if self._product is None:
            raise RuntimeError("prepare the STEP product before staging outputs")
        targets = tuple(Path(path).resolve() for path in destinations)
        if (len(targets) != 2 or targets[0] == targets[1]
                or targets[0].name != self._product.basename
                or targets[1] != companion_path(targets[0]).resolve()):
            raise ValueError("STEP publication requires its exact STEP and companion destinations")
        if not set(map(str, targets)) <= set(self._pin.revision.required_exports):
            raise ValueError("STEP and companion must both be declared output obligations")
        annotations = self.prepare_annotations()
        products = ((targets[0], self._product.payload, self._product.sha256, self._product.identity, "step"),
                    (targets[1], annotations.payload, annotations.sha256,
                     _digest(("annotations", annotations.step_sha256, annotations.sha256)), "annotations"))
        with self._stage(products) as staged:
            yield staged

    def publish_staged(self, staged, *, expected_prior_digest, completed=None):
        """Complete one staged filesystem effect; caller owns the group claim."""
        self._check()
        if self._staged_outputs.get(id(staged)) is not staged:
            raise ValueError("publication requires this session's live staged output")
        if (expected_prior_digest is not None and
                (type(expected_prior_digest) is not str or len(expected_prior_digest) != 64
                 or any(c not in "0123456789abcdef" for c in expected_prior_digest))):
            raise ValueError("expected prior digest must be lowercase SHA-256 or None")
        target = staged.destination
        def write():
            self._check()
            current = destination_digest(target)
            if current != expected_prior_digest:
                raise ExportConflict("output destination changed since the expected prior bytes")
            if current == staged.sha256:
                action = "verified-absent" if current is None else "verified-existing"
                metric = "verified_existing" if staged.kind == "step" else "annotation_verified"
            elif staged.sha256 is None:
                target.unlink()
                action, metric = "deleted", "annotation_deletions"
            else:
                if staged.staged_path is None:
                    raise ExportConflict("unstaged output changed before publication")
                if destination_digest(staged.staged_path) != staged.sha256:
                    raise RuntimeError("staged output bytes changed before publication")
                if destination_digest(target) != expected_prior_digest:
                    raise ExportConflict("output destination changed during publication")
                os.replace(staged.staged_path, target)
                action = "written"
                metric = "writes" if staged.kind == "step" else "annotation_writes"
            self._counts[metric] += 1
            receipt = PublishReceipt(self.document.owner_id, self._pin.revision_id, str(target),
                                     staged.identity, staged.sha256, staged.size, current, action)
            # The rename/delete (or matching-state observation) is already a
            # historical completed effect. Preserve its receipt even if final
            # verification, external replacement or cancellation now fails.
            if completed is not None:
                completed(receipt)
            if destination_digest(target) != staged.sha256:
                raise ExportConflict("output destination changed at publication")
            return receipt
        return self.document.publish_export(self._pin, str(target), write)

    def publish(self, destination: Path, *, expected_prior_digest: str | None) -> PublishReceipt:
        """Publish a native-only product; annotated programs use stage_outputs."""
        self._check()
        if self._product is None:
            raise RuntimeError("prepare the STEP product before publication")
        if self.prepare_annotations().payload is not None:
            raise UnsupportedStepProduct("intrinsic finishes require paired STEP and annotation publication")
        target = Path(destination).expanduser().resolve()
        if target.name != self._product.basename:
            raise ValueError("destination basename differs from the prepared STEP product")
        with self._stage(((target, self._product.payload, self._product.sha256,
                           self._product.identity, "step"),)) as staged:
            return self.publish_staged(staged[0], expected_prior_digest=expected_prior_digest)

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


def _read_saved_metadata(path: Path, expected_sha256: str, *, transferred=(), checkpoint=lambda: None):
    """Independent STEPCAF parse: every returned field comes from these bytes."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Reader

    if destination_digest(path) != expected_sha256:
        raise RuntimeError("independent STEP reader input does not match product bytes")
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(True)
    reader.SetMatMode(True)
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise ValueError("independent STEP parser rejected the product bytes")
    with _owned_xcaf_document() as document:
        if not reader.Transfer(document):
            raise ValueError("independent STEP transfer rejected the product bytes")
        face_reader = (SavedFaceReader(reader, (label for row in transferred for label in row), checkpoint=checkpoint)
                       if transferred else None)
        result = _saved_document_metadata(document, face_reader=face_reader)
        inventory = None if face_reader is None else face_reader.finish(expected_sha256, path.stat().st_size)
    if not result or destination_digest(path) != expected_sha256:
        raise ValueError("STEP parse has no geometry or its selected bytes changed")
    return result, inventory


def _saved_document_metadata(document, *, face_reader=None):
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

    def node(label, path, parent_location, inherited_color, parent_material=None):
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
        physical = xcaf_physical_material(label) or xcaf_physical_material(definition) or parent_material
        children = TDF_LabelSequence()
        shape_tool.GetComponents_s(definition, children)
        descendants = tuple(node(children.Value(index), path + (index,), world, label_color, physical)
                            for index in range(1, children.Length() + 1))
        geometry = None
        recipe = ()
        if not descendants:
            entry = TCollection_AsciiString()
            TDF_Tool.Entry_s(definition, entry)
            key = entry.ToCString()
            if key not in geometry_definitions:
                native = shape_tool.GetShape_s(definition).Located(TopLoc_Location())
                geometry_definitions[key] = (native, _geometry_facts(native))
            native, geometry = geometry_definitions[key]
            if face_reader is not None:
                face_reader.record(key, path, native)
            definition_shape = shape_tool.GetShape_s(definition)
            styles = dict(xcaf_face_recipe(shape_tool, definition, definition_shape))
            if not label.IsEqual(definition):
                styles.update(xcaf_face_recipe(shape_tool, label, definition_shape))
            recipe = relocated_face_recipe(definition_shape, native, tuple(styles.items()))
            if not world.IsIdentity():
                geometry = replace(geometry, bounds=_bounds(native.Moved(world)))
        return SavedNode(path, name(label) or name(definition), _matrix(local), label_color,
                         descendants, geometry, recipe, physical)

    roots = TDF_LabelSequence()
    shape_tool.GetFreeShapes(roots)
    return tuple(node(roots.Value(index), (index,), TopLoc_Location(), None)
                 for index in range(1, roots.Length() + 1))


def _geometry_facts(native: Any) -> SavedGeometry:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    if native is None or native.IsNull():
        raise ValueError("STEP readback contains a null geometry leaf")
    volume, area = GProp_GProps(), GProp_GProps()
    BRepGProp.VolumeProperties_s(native, volume)
    BRepGProp.SurfaceProperties_s(native, area)
    values = (float(volume.Mass()), float(area.Mass()), *_bounds(native))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("STEP readback contains nonfinite geometry facts")
    return SavedGeometry(values[0], values[1], tuple(values[2:]))


def _bounds(native: Any) -> tuple[float, ...]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    bounds = Bnd_Box()
    BRepBndLib.AddOptimal_s(native, bounds, False, False)
    result = tuple(map(float, bounds.Get()))
    if not all(math.isfinite(value) for value in result):
        raise ValueError("STEP readback contains nonfinite geometry bounds")
    return result
