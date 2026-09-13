"""Actual-byte STEP import into one retained document root.

This importer consumes only captured STEP bytes.  It owns a standalone XCAF
document for each native parse, captures the shapes produced by that parse,
and retains only bounded immutable hierarchy descriptors beside Document's
canonical geometry prototypes.  It never consults source code, model records,
or the retired geometry store.
"""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import tempfile
from threading import Event
from typing import Any

from .core import Document, GeometryHandle, Revision
from .identities import normalize
from .resources import AdmissionDenied, Cancelled, ResourceRequest
from .roots import AssemblyGroup, GeometryLeaf, RootNode
from .sources import CapturedInput
from .step_product import _CODEC_LOCK, _bounds, _matrix, _owned_xcaf_document
from .appearance import (appearance, face_recipe, relocated_face_recipe,
                         xcaf_face_recipe, xcaf_physical_material)


_IMPORT_POLICY = (
    "step-xcaf-import-v2",
    ("coordinate-unit", "MM"),
    ("names", "required"),
    ("occurrence-colors", "required"),
    ("face-colors", "exact-native-face-map"),
    ("materials", "physical-records;visual-materials-rejected"),
)
_MAX_IMPORTS = 8


class UnsupportedStepImport(ValueError):
    """The file contains metadata outside the current closed root schema."""


@dataclass(frozen=True)
class StepImportMetrics:
    native_parses: int
    retained_hits: int
    prototype_captures: int
    imported_nodes: int
    admitted_native_jobs: int
    admission_denied: int
    cancelled: int


@dataclass(frozen=True)
class ImportedStep:
    identity: str
    input_path: str
    input_sha256: str
    input_size: int
    revision_id: int
    root: RootNode
    root_bounds: tuple[float, ...]
    prototype_ids: frozenset[str]
    geometry_occurrences: int
    node_count: int
    coordinate_unit: str
    metadata_attestation: tuple[str, ...]


@dataclass(frozen=True)
class _Node:
    node_id: str
    label: str
    transform: tuple[float, ...]
    color: tuple[float, ...] | None
    definition: str | None
    children: tuple[_Node, ...]
    face_colors: tuple = ()
    physical_material: Any = None


@dataclass(frozen=True)
class _ImportRecord:
    identity: str
    handles: tuple[tuple[str, GeometryHandle], ...]
    roots: tuple[_Node, ...]
    root_bounds: tuple[float, ...]
    geometry_occurrences: int
    node_count: int
    face_maps: tuple = ()

    @property
    def prototype_ids(self) -> frozenset[str]:
        return frozenset(handle.prototype_id for _key, handle in self.handles)


class _StepImportRegistry:
    """Bounded descriptors only; Document remains the sole native owner."""

    def __init__(self) -> None:
        self.entries: OrderedDict[str, _ImportRecord] = OrderedDict()

    def prune(self, document: Document) -> None:
        live = set(document._prototypes)
        for key in tuple(self.entries):
            record = self.entries[key]
            if (not record.prototype_ids.issubset(live)
                    or any(handle.allocation_id not in document._allocations
                           for _definition, handle in record.handles)):
                del self.entries[key]
        while len(self.entries) > _MAX_IMPORTS:
            self.entries.popitem(last=False)

    def get(self, key: str) -> _ImportRecord | None:
        record = self.entries.get(key)
        if record is not None:
            self.entries.move_to_end(key)
        return record

    def put(self, record: _ImportRecord) -> None:
        self.entries[record.identity] = record
        self.entries.move_to_end(record.identity)
        while len(self.entries) > _MAX_IMPORTS:
            self.entries.popitem(last=False)


def _identity(value: Any) -> str:
    payload = json.dumps(normalize(value), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _runtime_identity(runtime: Any) -> tuple:
    return (
        _IMPORT_POLICY,
        hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        platform.python_version(),
        platform.machine(),
        importlib.metadata.version("cadquery-ocp"),
        normalize(runtime),
    )


def step_input_identity(captured: CapturedInput, *, runtime: Any = ()) -> str:
    """Identify consumed STEP bytes and this importer, independently of source."""
    if type(captured) is not CapturedInput:
        raise TypeError("STEP import requires CapturedInput bytes")
    if captured.path.suffix.lower() not in {".step", ".stp"}:
        raise ValueError("STEP import input path must end in .step or .stp")
    return _identity((captured.digest, len(captured.data), _runtime_identity(runtime)))


@contextmanager
def _reader_settings():
    """Normalize imported geometry to millimeters and restore OCCT statics."""
    from OCP.Interface import Interface_Static
    from OCP.STEPCAFControl import STEPCAFControl_Controller

    STEPCAFControl_Controller.Init_s()
    changes = {
        "xstep.cascade.unit": "MM",
        "read.step.product.mode": "ON",
        "read.step.assembly.level": "all",
    }
    previous = {name: Interface_Static.CVal_s(name) for name in changes}
    try:
        for name, value in changes.items():
            if not Interface_Static.SetCVal_s(name, value):
                raise UnsupportedStepImport(f"OCCT rejected STEP import setting {name}={value}")
        yield
    finally:
        for name, value in previous.items():
            Interface_Static.SetCVal_s(name, value)


def _name(label: Any) -> str:
    from OCP.TDataStd import TDataStd_Name

    attribute = TDataStd_Name()
    return (attribute.Get().ToExtString()
            if label.FindAttribute(TDataStd_Name.GetID_s(), attribute) else "")


def _color(label: Any, colors: Any) -> tuple[float, ...] | None:
    from OCP.Quantity import Quantity_ColorRGBA
    from OCP.XCAFDoc import XCAFDoc_ColorGen, XCAFDoc_ColorSurf, XCAFDoc_ColorTool

    value = Quantity_ColorRGBA()
    for kind in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen):
        if XCAFDoc_ColorTool.GetColor_s(label, kind, value):
            rgb = value.GetRGB()
            result = (float(rgb.Red()), float(rgb.Green()), float(rgb.Blue()), float(value.Alpha()))
            if not all(math.isfinite(channel) and 0.0 <= channel <= 1.0 for channel in result):
                raise ValueError("STEP occurrence color is not finite RGBA")
            return result
    return None


def _reject_unrepresented_metadata(document: Any, shape_tool: Any, colors: Any) -> None:
    """Refuse known appearance fields until their root value schema is complete."""
    from OCP.TDF import TDF_LabelSequence
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    visual = XCAFDoc_DocumentTool.VisMaterialTool_s(document.Main())
    visual_labels = TDF_LabelSequence()
    visual.GetMaterials(visual_labels)
    if visual_labels.Length():
        raise UnsupportedStepImport(
            "STEP visual material textures/channels are not yet represented"
        )



def _root_from(record: _ImportRecord) -> RootNode:
    handles = dict(record.handles)
    face_maps = dict(record.face_maps)

    def build(node: _Node) -> RootNode:
        own = {} if node.color is None else {"color": node.color}
        if node.physical_material is not None:
            own["physical_material"] = node.physical_material
        if node.face_colors:
            correspondence = face_maps[node.definition]
            own["face_colors"] = face_recipe(tuple((correspondence[index], color)
                                                  for index, color in node.face_colors),
                                              face_count=len(correspondence))
        if node.definition is not None:
            return GeometryLeaf(node.node_id, handles[node.definition], node.transform,
                                node.label, appearance(own))
        return AssemblyGroup(node.node_id, tuple(build(child) for child in node.children),
                             node.transform, node.label, appearance(own, allow_faces=False))

    roots = tuple(build(node) for node in record.roots)
    if len(roots) == 1:
        return roots[0]
    return AssemblyGroup("step-document", roots, label="STEP document")


def _map_imported_root(root, leaf):
    """Traverse only the exact hierarchy vocabulary emitted by this importer.

    Native importer roots and their verified checkpoints are trusted callers.
    This is not a correspondence inference for arbitrary source model roots.
    """
    from .annotations import MAX_DEPTH, MAX_NODES
    visits = 0
    def visit(node, path):
        nonlocal visits
        visits += 1
        if visits > MAX_NODES or len(path) > MAX_DEPTH:
            raise ValueError("saved annotation hierarchy exceeds the limit")
        if (type(node) not in (GeometryLeaf, AssemblyGroup)
                or node.node_id.value != f"n{path[-1]}"):
            raise ValueError("saved root does not carry the imported occurrence hierarchy")
        if type(node) is GeometryLeaf:
            return leaf(node, path)
        if not node.children:
            raise ValueError("saved root contains an empty imported assembly")
        children = tuple(visit(child, path + (index,))
                         for index, child in enumerate(node.children, 1))
        return node if all(a is b for a, b in zip(children, node.children)) else replace(node, children=children)
    if type(root) is AssemblyGroup and root.node_id.value == "step-document":
        children = tuple(visit(child, (index,)) for index, child in enumerate(root.children, 1))
        return root if all(a is b for a, b in zip(children, root.children)) else replace(root, children=children)
    return visit(root, (1,))


def saved_annotation_paths(captured, root):
    """Bind an actual imported/checkpointed hierarchy to the consumed bytes."""
    from .annotations import SavedAnnotationPaths
    leaves = []
    def record(node, path):
        leaves.append(path)
        return node
    _map_imported_root(root, record)
    return SavedAnnotationPaths(captured.digest, len(captured.data), tuple(leaves))


def apply_saved_annotations(root, annotations):
    """Create owned scene values; the imported native root stays immutable."""
    overrides = {row.path: row.appearance for row in annotations.occurrences}
    used = set()
    def apply(node, path):
        # These two fields come exclusively from this companion codec. Native
        # STEP color, exact face recipes and physical records remain untouched.
        native = _native_appearance(node)
        if path in overrides:
            used.add(path)
        return replace(node, appearance=appearance({**native, **overrides.get(path, {})}))
    result = _map_imported_root(root, apply)
    if used != set(overrides):
        raise ValueError("annotation paths do not match the imported root")
    return result


def _native_appearance(node):
    return {key: value for key, value in appearance(node.appearance).items()
            if key not in {"pbr", "material"}}


def native_saved_root(root):
    """Recover STEP-only values from a verified annotated saved checkpoint."""
    return _map_imported_root(root, lambda node, _path: replace(node, appearance=appearance(_native_appearance(node))))


class StepImportSession:
    """Import exact captured bytes into a new immutable document revision."""

    def __init__(self, document: Document, *, work_directory: Path,
                 cancellation: Event | None = None):
        if not isinstance(document, Document):
            raise TypeError("STEP import requires a Document")
        document._assert_owner()
        self.document = document
        self.work_directory = Path(work_directory).resolve()
        self.cancellation = cancellation or Event()
        registry = getattr(document, "_step_imports", None)
        if registry is None:
            registry = _StepImportRegistry()
            document._step_imports = registry
        if type(registry) is not _StepImportRegistry:
            raise TypeError("document STEP import registry has an invalid type")
        self._registry = registry
        self._counts = dict(native_parses=0, retained_hits=0, prototype_captures=0,
                            imported_nodes=0, admitted_native_jobs=0,
                            admission_denied=0, cancelled=0)

    @property
    def metrics(self) -> StepImportMetrics:
        self.document._assert_owner()
        return StepImportMetrics(**self._counts)

    def _check(self) -> None:
        self.document._assert_owner()
        if self.cancellation.is_set():
            raise Cancelled("STEP import was cancelled")

    def load(self, captured: CapturedInput) -> ImportedStep:
        """Parse or reuse one exact byte/runtime/policy identity and commit it."""
        try:
            return self._load(captured)
        except AdmissionDenied:
            self._counts["admission_denied"] += 1
            raise
        except Cancelled:
            self._counts["cancelled"] += 1
            raise

    def _load(self, captured: CapturedInput) -> ImportedStep:
        self._check()
        identity = step_input_identity(captured, runtime=self.document.runtime)
        self._registry.prune(self.document)
        cached = self._registry.get(identity)
        if cached is not None:
            self._check()
            with self.document.begin(f"step:{captured.digest}") as transaction:
                transaction.cancellation = self.cancellation
                root = _root_from(cached)
                transaction.bind_root(root, unrepresented_metadata=())
                revision = transaction.commit()
            self._counts["retained_hits"] += 1
            self._counts["imported_nodes"] += cached.node_count
            return self._result(captured, cached, revision)

        with self.document.begin(f"step:{captured.digest}") as transaction:
            transaction.cancellation = self.cancellation
            record = self._parse_capture(captured, identity, transaction)
            self._check()
            root = _root_from(record)
            transaction.bind_root(root, unrepresented_metadata=())
            revision = transaction.commit()
        self._registry.put(record)
        self._counts["imported_nodes"] += record.node_count
        return self._result(captured, record, revision)

    def _result(self, captured: CapturedInput, record: _ImportRecord,
                revision: Revision) -> ImportedStep:
        return ImportedStep(
            record.identity, str(captured.path), captured.digest, len(captured.data),
            revision.revision_id, revision.root, record.root_bounds,
            record.prototype_ids, record.geometry_occurrences, record.node_count, "MM",
            ("names-preserved", "occurrence-colors-preserved",
             "per-face-colors-exact-native-map", "physical-materials-preserved"),
        )

    def _parse_capture(self, captured: CapturedInput, identity: str,
                       transaction: Any) -> _ImportRecord:
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPCAFControl import STEPCAFControl_Reader
        from OCP.TCollection import TCollection_AsciiString
        from OCP.TDF import TDF_Label, TDF_LabelSequence, TDF_Tool
        from OCP.TopLoc import TopLoc_Location
        from OCP.XCAFDoc import XCAFDoc_DocumentTool

        self.work_directory.mkdir(parents=True, exist_ok=True)
        definitions: dict[str, Any] = {}
        colored_definitions = set()
        nodes = 0
        leaves = 0
        with self.document.admission.admit(ResourceRequest(kind="native"),
                                            cancellation=self.cancellation):
            self._counts["admitted_native_jobs"] += 1
            with _CODEC_LOCK, _reader_settings(), tempfile.TemporaryDirectory(
                    prefix="step-import-", dir=self.work_directory) as temporary:
                selected = Path(temporary) / "captured.step"
                selected.write_bytes(captured.data)
                if hashlib.sha256(selected.read_bytes()).hexdigest() != captured.digest:
                    raise RuntimeError("selected STEP parser bytes changed before read")
                reader = STEPCAFControl_Reader()
                reader.SetNameMode(True)
                reader.SetColorMode(True)
                reader.SetMatMode(True)
                reader.SetLayerMode(False)
                reader.SetGDTMode(False)
                reader.SetPropsMode(False)
                reader.SetSHUOMode(False)
                reader.SetViewMode(False)
                reader.SetMetaMode(False)
                reader.SetProductMetaMode(False)
                self._counts["native_parses"] += 1
                if reader.ReadFile(str(selected)) != IFSelect_RetDone:
                    raise ValueError("STEP parser rejected captured bytes")
                with _owned_xcaf_document() as document:
                    if not reader.Transfer(document):
                        raise ValueError("STEP transfer rejected captured bytes")
                    self._check()
                    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
                    colors = XCAFDoc_DocumentTool.ColorTool_s(document.Main())
                    _reject_unrepresented_metadata(document, shape_tool, colors)

                    def visit(label: Any, local_index: int,
                              inherited_color: tuple[float, ...] | None, parent_material=None) -> _Node:
                        nonlocal nodes, leaves
                        self._check()
                        nodes += 1
                        definition = label
                        if shape_tool.IsReference_s(label):
                            definition = TDF_Label()
                            if not shape_tool.GetReferredShape_s(label, definition):
                                raise ValueError("STEP occurrence has no referenced definition")
                        instance_shape = shape_tool.GetShape_s(label)
                        if instance_shape.IsNull():
                            raise ValueError("STEP occurrence contains null geometry")
                        local = _matrix(instance_shape.Location())
                        color = (_color(label, colors) or _color(definition, colors)
                                 or inherited_color)
                        physical = xcaf_physical_material(label) or xcaf_physical_material(definition) or parent_material
                        children = TDF_LabelSequence()
                        shape_tool.GetComponents_s(definition, children)
                        descendants = tuple(
                            visit(children.Value(index), index, color, physical)
                            for index in range(1, children.Length() + 1)
                        )
                        label_name = _name(label) or _name(definition)
                        if descendants:
                            return _Node(f"n{local_index}", label_name, local, color,
                                         None, descendants, (), physical)
                        entry = TCollection_AsciiString()
                        TDF_Tool.Entry_s(definition, entry)
                        key = entry.ToCString()
                        if key not in definitions:
                            native = shape_tool.GetShape_s(definition).Located(TopLoc_Location())
                            if native.IsNull():
                                raise ValueError("STEP definition contains null geometry")
                            definitions[key] = native
                        definition_shape = shape_tool.GetShape_s(definition)
                        styles = dict(xcaf_face_recipe(shape_tool, definition, definition_shape, checkpoint=self._check))
                        if not label.IsEqual(definition):
                            styles.update(xcaf_face_recipe(shape_tool, label, definition_shape, checkpoint=self._check))
                        recipe = relocated_face_recipe(definition_shape, definitions[key], tuple(styles.items()))
                        if recipe:
                            colored_definitions.add(key)
                        leaves += 1
                        return _Node(f"n{local_index}", label_name, local, color, key, (), recipe, physical)

                    root_labels = TDF_LabelSequence()
                    shape_tool.GetFreeShapes(root_labels)
                    roots = tuple(visit(root_labels.Value(index), index, None)
                                  for index in range(1, root_labels.Length() + 1))
                    if not roots:
                        raise ValueError("STEP document contains no free shapes")
                    one_shape = shape_tool.GetOneShape()
                    root_bounds = _bounds(one_shape)
                if hashlib.sha256(selected.read_bytes()).hexdigest() != captured.digest:
                    raise RuntimeError("selected STEP parser bytes changed during read")

        self._check()
        handles = []
        face_maps = []
        for key, native in definitions.items():
            self._check()
            if key in colored_definitions:
                handle, mapping = transaction.capture_with_face_map(native, logical_id=f"step-definition:{key}")
                face_maps.append((key, mapping))
            else:
                handle = transaction.capture(native, logical_id=f"step-definition:{key}")
            handles.append((key, handle))
            self._counts["prototype_captures"] += 1
        return _ImportRecord(identity, tuple(handles), roots, root_bounds, leaves, nodes, tuple(face_maps))
