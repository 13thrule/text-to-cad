"""Exact unsplit face correspondence through live STEP transfer entities.

Native wrappers stay inside writer/reader work. The prepared inventory contains
only actual saved paths, entity labels and native face ordinals bound to bytes.
Neither face enumeration order nor geometric similarity proves correspondence.
"""
from __future__ import annotations

from dataclasses import dataclass

from .appearance import MAX_FACES, native_faces


class FaceTransferError(ValueError):
    pass


def _check_face_order(shape, faces):
    target = native_faces(shape)
    indices = tuple(target.FindIndex(face) for face in faces)
    if (len(indices) != target.Extent()
            or set(indices) != set(range(1, target.Extent() + 1))):
        raise FaceTransferError("native face copy is not an exact bijection")
    return tuple(faces)


def copied_face_order(source, target, copier, faces=None):
    """Return copied native faces in the proven source order."""
    if faces is None:
        original = native_faces(source)
        faces = tuple(original.FindKey(index) for index in range(1, original.Extent() + 1))
    return _check_face_order(target, tuple(copier.ModifiedShape(face) for face in faces))


def relocated_face_order(source, target, faces):
    delta = target.Location().Multiplied(source.Location().Inverted())
    return _check_face_order(target, tuple(face.Moved(delta) for face in faces))


def transfer_face_entities(writer, definitions, *, checkpoint=lambda: None):
    """Capture exact emitted geometry labels before the writer is discarded.

The writer helper calls this after in-model canonicalization. Its remaining
file canonicalization permutes only presentation entities, never AdvancedFace.
OCP's Number(handle) binding returns zero; held identity-stable entity wrappers
provide the same exact lookup used by the writer's style canonicalizer.
"""
    from OCP.STEPConstruct import STEPConstruct
    from OCP.StepShape import StepShape_AdvancedFace
    from OCP.Transfer import Transfer_SimpleBinderOfTransient
    from cadgen.step_export import _STYLE_TAIL_FAMILY

    if sum(map(len, definitions)) > MAX_FACES:
        raise FaceTransferError("STEP face proof exceeds the face limit")
    finder = writer.WS().TransferWriter().FinderProcess()
    rows, entities = [], {}
    for faces in definitions:
        row = []
        for face in faces:
            checkpoint()
            entity = STEPConstruct.FindEntity_s(finder, face)
            if (not isinstance(entity, StepShape_AdvancedFace)
                    or entity.DynamicType().Name() in _STYLE_TAIL_FAMILY):
                raise FaceTransferError("STEP face transfer is split, absent or unsupported")
            row.append(id(entity))
            entities[id(entity)] = entity
        if len(set(row)) != len(row):
            raise FaceTransferError("STEP face transfer merged distinct source faces")
        rows.append(tuple(row))

    # Require one complete singleton binder for every direct face result.
    # TransferBRep_ShapeMapper is not exposed by OCP, but the existing mapper
    # instances and their actual dynamic binders are available through Find.
    bindings = {key: 0 for key in entities}
    for index in range(1, finder.NbMapped() + 1):
        checkpoint()
        binder = finder.Find(finder.Mapped(index))
        if isinstance(binder, Transfer_SimpleBinderOfTransient):
            key = id(binder.Result())
            if key in bindings:
                if binder.IsMultiple() or binder.NextResult() is not None:
                    raise FaceTransferError("STEP face transfer has multiple results")
                bindings[key] += 1
    if any(count != 1 for count in bindings.values()):
        raise FaceTransferError("STEP face transfer lacks an unambiguous singleton binder")

    numbers = {}
    model = writer.Model()
    for index in range(1, model.NbEntities() + 1):
        checkpoint()
        entity = model.Entity(index)
        key = id(entity)
        if key in entities:
            if key in numbers:
                raise FaceTransferError("STEP face entity occurs more than once in the writer model")
            numbers[key] = index
    if numbers.keys() != entities.keys():
        raise FaceTransferError("STEP face transfer result is absent from the written model")
    return tuple(tuple(numbers[key] for key in row) for row in rows)


@dataclass(frozen=True)
class SavedFaceInventory:
    step_sha256: str
    step_bytes: int
    # Actual imported definition order: each tuple maps its native face ordinal
    # to the file entity label that transferred to that exact native face.
    definitions: tuple[tuple[int, ...], ...]
    occurrences: tuple[tuple[tuple[int, ...], int], ...]

    def __post_init__(self):
        if (type(self.step_sha256) is not str or len(self.step_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.step_sha256)
                or type(self.step_bytes) is not int or self.step_bytes < 1
                or type(self.definitions) is not tuple
                or sum(map(len, self.definitions)) > MAX_FACES
                or type(self.occurrences) is not tuple or len(self.occurrences) > MAX_FACES):
            raise FaceTransferError("invalid saved face inventory binding or limits")
        for row in self.definitions:
            if (type(row) is not tuple or not row or len(set(row)) != len(row)
                    or any(type(value) is not int or value < 1 for value in row)):
                raise FaceTransferError("saved face definition is not an entity bijection")
        seen = set()
        for path, definition in self.occurrences:
            if (type(path) is not tuple or not 0 < len(path) <= 128 or path in seen
                    or any(type(index) is not int or not 1 <= index <= MAX_FACES for index in path)
                    or type(definition) is not int or not 0 <= definition < len(self.definitions)):
                raise FaceTransferError("invalid saved face occurrence")
            seen.add(path)


class SavedFaceReader:
    """Live independent-reader adapter; never retained as product facts."""
    def __init__(self, reader, labels, *, checkpoint=lambda: None):
        from OCP.STEPConstruct import STEPConstruct
        from OCP.StepShape import StepShape_AdvancedFace
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopTools import TopTools_IndexedMapOfShape

        self._checkpoint = checkpoint
        self._faces = TopTools_IndexedMapOfShape()
        self._labels = []
        self._definitions, self._keys, self._occurrences = [], {}, []
        self._face_count = 0
        labels = sorted(set(labels))
        if len(labels) > MAX_FACES:
            raise FaceTransferError("STEP face proof exceeds the face limit")
        model = reader.Reader().Model()
        process = reader.Reader().WS().TransferReader().TransientProcess()
        previous = 0
        entities = []
        for label in labels:
            checkpoint()
            # IdentLabel(handle) has the same broken OCP handle lookup as
            # Number. Native label search avoids equating file label and rank.
            index = model.NextNumberForLabel(f"#{label}", previous, True)
            if not index and previous:
                index = model.NextNumberForLabel(f"#{label}", 0, True)
            if index < 1:
                raise FaceTransferError("saved STEP lacks a transferred face entity label")
            previous = index
            entity = model.Entity(index)
            if not isinstance(entity, StepShape_AdvancedFace):
                raise FaceTransferError("saved face entity label changed type")
            entities.append((label, entity))

        # Find(handle) has the same OCP lookup defect as Number(handle). Keep
        # the actual model wrappers alive and inspect the exact mapped entity's
        # binder by native map index. FindShape alone can conceal extra results.
        bindings = {id(entity): 0 for _, entity in entities}
        for index in range(1, process.NbMapped() + 1):
            checkpoint()
            key = id(process.Mapped(index))
            if key not in bindings:
                continue
            binder = process.MapItem(index)
            if binder is None or not binder.HasResult():
                raise FaceTransferError("saved face transfer lacks a complete singleton binder")
            if binder.IsMultiple() or binder.NextResult() is not None:
                raise FaceTransferError("saved face transfer has multiple results")
            bindings[key] += 1
        if any(count != 1 for count in bindings.values()):
            raise FaceTransferError("saved face transfer lacks an unambiguous singleton binder")

        for label, entity in entities:
            checkpoint()
            face = STEPConstruct.FindShape_s(process, entity)
            if face.IsNull() or face.ShapeType() != TopAbs_FACE:
                raise FaceTransferError("saved face transfer is missing, split or healed")
            if self._faces.Contains(face):
                raise FaceTransferError("saved STEP merged distinct face entities")
            self._faces.Add(face)
            self._labels.append(label)

    def record(self, key, path, native):
        self._checkpoint()
        if key not in self._keys:
            faces = native_faces(native)
            indices = tuple(self._faces.FindIndex(faces.FindKey(index))
                            for index in range(1, faces.Extent() + 1))
            if not any(indices):
                self._keys[key] = None
            else:
                if not all(indices) or len(set(indices)) != len(indices):
                    raise FaceTransferError("saved face membership is not a complete bijection")
                self._face_count += len(indices)
                if self._face_count > MAX_FACES:
                    raise FaceTransferError("saved face inventory exceeds the face limit")
                self._keys[key] = len(self._definitions)
                self._definitions.append(tuple(self._labels[index - 1] for index in indices))
        definition = self._keys[key]
        if definition is not None:
            if len(self._occurrences) >= MAX_FACES:
                raise FaceTransferError("saved face inventory exceeds the occurrence limit")
            self._occurrences.append((path, definition))

    def finish(self, digest, size):
        return SavedFaceInventory(digest, size, tuple(self._definitions), tuple(self._occurrences))
