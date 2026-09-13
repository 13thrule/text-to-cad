"""Closed appearance values, independent of native geometry and persistence.

Face recipes address zero-based FACE MapShapes indices on exactly one retained
prototype. Authored ``cad_face_ordinal_colors`` uses one-based indices; conversion
happens once at capture, through the native copy's proven correspondence when
there is a private source shape. Neither representation is a persistent name.
"""
from __future__ import annotations

import math
from types import MappingProxyType

VERSION = 1
MAX_FACES = 100_000
MAX_TEXT = 4096
PBR_KEYS = frozenset({"roughness", "metalness", "clearcoat", "clearcoatRoughness", "opacity"})
KEYS = frozenset({"color", "pbr", "material", "face_colors", "physical_material"})
_PHYSICAL = frozenset({"name", "description", "density", "density_name", "density_type"})
_MAPS = (dict, MappingProxyType)


def _unit(value):
    if type(value) not in (int, float) or not 0 <= value <= 1 or not math.isfinite(value):
        raise ValueError("appearance channels require finite numbers in [0, 1]")
    return float(value)


def rgba(value):
    if type(value) not in (tuple, list) or len(value) not in (3, 4):
        raise ValueError("appearance color requires RGB or RGBA unit values")
    result = tuple(_unit(channel) for channel in value)
    return result + (1.,) if len(result) == 3 else result


def _text(value):
    if type(value) is not str or len(value) > MAX_TEXT or "\x00" in value:
        raise ValueError("appearance text must be a bounded string without NUL")
    return value


def physical_material(value):
    if type(value) not in _MAPS or set(value) != _PHYSICAL:
        raise ValueError("physical material requires name, description and native density fields")
    result = {key: _text(value[key]) for key in _PHYSICAL - {"density"}}
    density = value["density"]
    if type(density) not in (int, float) or not 0 <= density <= 1e100 or not math.isfinite(density):
        raise ValueError("physical material density must be finite and nonnegative")
    result["density"] = float(density)
    return MappingProxyType(dict(sorted(result.items())))


def face_recipe(value, *, face_count=None):
    if face_count is not None and (type(face_count) is not int or not 0 <= face_count <= MAX_FACES):
        raise ValueError("appearance face count exceeds the limit")
    if type(value) not in (tuple, list) or len(value) > MAX_FACES:
        raise ValueError("face colors require a bounded ordinal/color sequence")
    rows = {}
    for row in value:
        if type(row) not in (tuple, list) or len(row) != 2:
            raise ValueError("face colors require ordinal/color pairs")
        ordinal, color = row
        if (type(ordinal) is not int or not 0 <= ordinal < MAX_FACES
                or face_count is not None and ordinal >= face_count or ordinal in rows):
            raise ValueError("face color ordinal is duplicate or outside the exact prototype")
        rows[ordinal] = rgba(color)
    return tuple(sorted(rows.items()))


def authored_face_recipe(value, *, face_count, correspondence=None):
    """Convert strict authored one-based indices using an optional exact map."""
    if value is None:
        return ()
    if type(value) not in _MAPS or len(value) > MAX_FACES:
        raise ValueError("cad_face_ordinal_colors requires a bounded plain mapping")
    if correspondence is not None:
        if (type(correspondence) is not tuple or len(correspondence) != face_count
                or set(correspondence) != set(range(face_count))):
            raise ValueError("face capture correspondence must be an exact bijection")
    rows = []
    for ordinal, color in value.items():
        if type(ordinal) is not int or not 1 <= ordinal <= face_count:
            raise ValueError("authored face color ordinal is outside the source shape")
        target = ordinal - 1 if correspondence is None else correspondence[ordinal - 1]
        rows.append((target, color))
    return face_recipe(rows, face_count=face_count)


def appearance(value, *, face_count=None, allow_faces=True):
    """Validate and independently freeze the complete internal appearance."""
    if value is None or type(value) is tuple and not value:
        return MappingProxyType({})
    if type(value) not in _MAPS or set(value) - KEYS:
        raise ValueError("unsupported appearance fields")
    result = {}
    if "color" in value:
        result["color"] = rgba(value["color"])
    if "pbr" in value:
        pbr = value["pbr"]
        if type(pbr) not in _MAPS or set(pbr) - PBR_KEYS:
            raise ValueError("unsupported appearance PBR fields")
        result["pbr"] = MappingProxyType({key: _unit(pbr[key]) for key in sorted(pbr)})
    if "material" in value:
        result["material"] = _text(value["material"])
    if "physical_material" in value:
        result["physical_material"] = physical_material(value["physical_material"])
    if "face_colors" in value:
        if not allow_faces:
            raise ValueError("face colors belong to a geometry leaf, not an assembly group")
        result["face_colors"] = face_recipe(value["face_colors"], face_count=face_count)
    return MappingProxyType(result)


def inherited(parent, own):
    """Merge PBR fields; never inherit a recipe onto another geometry."""
    parent, own = appearance(parent), appearance(own)
    result = {key: value for key, value in parent.items() if key != "face_colors"}
    result.update(own)
    if "pbr" in parent or "pbr" in own:
        result["pbr"] = {**parent.get("pbr", {}), **own.get("pbr", {})}
    return appearance(result)


def to_value(value):
    """Fresh JSON-ready values for worker/browser boundaries."""
    value = appearance(value)
    def plain(item):
        if type(item) in _MAPS:
            return {key: plain(child) for key, child in item.items()}
        if type(item) is tuple:
            return [plain(child) for child in item]
        return item
    return plain(value)


def encoded_size_bound(value):
    """Conservative JSON byte bound before allocating transport dictionaries."""
    value = appearance(value)
    return 512 + len(value.get("face_colors", ())) * 160 + 6 * (
        len(value.get("material", ""))
        + sum(len(item) for item in value.get("physical_material", {}).values() if type(item) is str))


def native_faces(shape):
    """Owner-thread native helper; callers provide admission and checkpoints."""
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape
    result = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, result)
    if result.Extent() > MAX_FACES:
        raise ValueError("appearance topology exceeds the face limit")
    return result


def copied_face_recipe(source, target, copier, recipe):
    """Carry a recipe through this copier's actual topology history."""
    recipe = face_recipe(recipe)
    if not recipe:
        return ()
    source_faces, target_faces = native_faces(source), native_faces(target)
    recipe = face_recipe(recipe, face_count=source_faces.Extent())
    mapped = []
    for ordinal, color in recipe:
        copied = copier.ModifiedShape(source_faces.FindKey(ordinal + 1))
        index = target_faces.FindIndex(copied)
        if index < 1:
            raise ValueError("native copy did not preserve an appearance face")
        mapped.append((index - 1, color))
    return face_recipe(mapped, face_count=target_faces.Extent())


def relocated_face_recipe(source, target, recipe):
    """Map the same topology after changing only its root location."""
    recipe = face_recipe(recipe)
    if not recipe:
        return ()
    source_faces, target_faces = native_faces(source), native_faces(target)
    delta = target.Location().Multiplied(source.Location().Inverted())
    result = []
    for ordinal, color in face_recipe(recipe, face_count=source_faces.Extent()):
        index = target_faces.FindIndex(source_faces.FindKey(ordinal + 1).Moved(delta))
        if index < 1:
            raise ValueError("native relocation did not preserve an appearance face")
        result.append((index - 1, color))
    return face_recipe(result, face_count=target_faces.Extent())


def xcaf_color(label):
    from OCP.Quantity import Quantity_ColorRGBA
    from OCP.XCAFDoc import XCAFDoc_ColorGen, XCAFDoc_ColorSurf, XCAFDoc_ColorTool
    value = Quantity_ColorRGBA()
    for kind in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen):
        if XCAFDoc_ColorTool.GetColor_s(label, kind, value):
            rgb = value.GetRGB()
            return rgba((rgb.Red(), rgb.Green(), rgb.Blue(), value.Alpha()))
    return None


def xcaf_physical_material(label):
    """Read actual material attributes, avoiding pybind output-handle traps."""
    from OCP.TDF import TDF_AttributeIterator
    from OCP.TDataStd import TDataStd_TreeNode
    from OCP.XCAFDoc import XCAFDoc, XCAFDoc_Material
    def attributes(selected):
        iterator = TDF_AttributeIterator(selected)
        count = 0
        while iterator.More():
            count += 1
            if count > 4096:
                raise ValueError("STEP material label exceeds the attribute limit")
            yield iterator.Value()
            iterator.Next()
    attribute = None
    for candidate in attributes(label):
        if isinstance(candidate, XCAFDoc_Material):
            attribute = candidate
            break
        if (isinstance(candidate, TDataStd_TreeNode)
                and candidate.ID().IsSame(XCAFDoc.MaterialRefGUID_s())):
            if not candidate.HasFather():
                raise ValueError("STEP physical material reference has no definition")
            attribute = next((value for value in attributes(candidate.Father().Label())
                              if isinstance(value, XCAFDoc_Material)), None)
            if attribute is None:
                raise ValueError("STEP physical material reference has no material")
            break
    if attribute is None:
        return None
    def text(value):
        return "" if value is None else value.ToCString()
    return physical_material({"name": text(attribute.GetName()),
        "description": text(attribute.GetDescription()), "density": attribute.GetDensity(),
        "density_name": text(attribute.GetDensName()), "density_type": text(attribute.GetDensValType())})


def set_xcaf_physical_material(tool, label, value):
    from OCP.TCollection import TCollection_HAsciiString
    value = physical_material(value)
    tool.SetMaterial(label, TCollection_HAsciiString(value["name"]),
                     TCollection_HAsciiString(value["description"]), value["density"],
                     TCollection_HAsciiString(value["density_name"]),
                     TCollection_HAsciiString(value["density_type"]))


def xcaf_face_recipe(shape_tool, label, native, *, checkpoint=lambda: None):
    """Read subshape styles through exact native identity, never shape hashes."""
    from OCP.TDF import TDF_ChildIterator
    faces = None
    styles = {}
    visits = 0
    def collect(current, depth, include=True):
        nonlocal visits, faces
        visits += 1
        if visits > MAX_FACES * 4 or depth > 128:
            raise ValueError("STEP appearance labels exceed traversal limits")
        checkpoint()
        color = xcaf_color(current) if include else None
        if color is not None:
            if faces is None:
                faces = native_faces(native)
            shape = shape_tool.GetShape_s(current)
            if shape.IsNull():
                raise ValueError("STEP colored subshape has no native geometry")
            selected = native_faces(shape)
            if selected.Extent() == 0:
                raise ValueError("STEP subshape colors currently require faces")
            for index in range(1, selected.Extent() + 1):
                ordinal = faces.FindIndex(selected.FindKey(index))
                if not ordinal:
                    raise ValueError("STEP colored face is not in its exact prototype")
                styles[ordinal - 1] = color
        children = TDF_ChildIterator(current, False)
        while children.More():
            collect(children.Value(), depth + 1)
            children.Next()
    # Whole-definition/occurrence color is a separate inherited override.
    collect(label, 0, False)
    return face_recipe(tuple(styles.items()), face_count=0 if faces is None else faces.Extent())
