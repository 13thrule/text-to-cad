"""``LazyCompound``: a child model's geometry, promised now and delivered when read.

A parent's body calls a child model and gets one of these back at once. If the
child was stale its build has been submitted to the pool (§9 in STORE.md); if it
was current there is no job at all. Either way the body keeps going — calling
its other children, placing them, labelling them — and only blocks when
something actually needs geometry: the first read of the wrapped OCCT shape,
which build123d cannot avoid. In the common body that read happens once, at the
closing ``Compound(children=[...])``, after every sibling has been submitted, so
stale children build in parallel.

Deferred without forcing: ``Pos/Rot/Location * child`` and ``.moved()`` compose
a placement; ``.label`` and ``.color`` are recorded and applied on force.
Everything else — ``.faces()``, ``.bounding_box()``, a boolean, ``.solids()``,
``copy.copy``, ``bool(child)`` — reaches the shape and forces. build123d reads
the shape through two names, the ``wrapped`` property and the ``_wrapped``
attribute it is backed by (its empty-shape checks are ``if self._wrapped is
None``), so ``_wrapped`` is the property here: a promise can never be mistaken
for an empty shape and answer with nothing. A build123d path not anticipated
here therefore degrades to "forced early": correct geometry, less overlap, never
wrong output.

Forcing: wait for the job (if any), then use the pinned tree — a current child was
pinned at the CALL (the wrapper read its record then), a stale child's tree is the
one its job produced; the first tree a child resolves to in a build is what every
later call composes (snapshot isolation). Materialize it, apply the placement with
``TopoDS_Shape.Moved`` (which shares the TShape, so the packager still sees the
child intact and writes a link), and tag the result exactly as
:func:`cadgen.store.materialize.materialize` does.

A failed child raises when forced; the error names the child, carries the
call site of the ``child()`` call, and includes the worker's output.

INTERNAL. No author names this type; ``type(arm())`` inside a parent is the only
way anyone sees it.
"""

from __future__ import annotations

import copy
import sys
import traceback
from pathlib import Path
from typing import Any

from build123d import Compound
from build123d.topology.shape_core import downcast
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy

from cadgen.store.materialize import PARTNER_TAG, ROOT_LOC_TAG, TREE_TAG, _Partner, materialize


class ChildBuildError(RuntimeError):
    """A child model's build failed; raised where the parent first needed it."""


class LazyCompound(Compound):
    """See the module docstring."""

    def __init__(self, model: Path | str, job: Any, *, frame: Any, label: str, tree: str | None = None) -> None:
        self._lazy_shape = None
        self._lazy_forcing = False
        Compound.__init__(self, None, label=label)
        # The child's identity: its model ref (``script::fn``; see store.index).
        self._lazy_model = str(model)
        self._lazy_job = job
        self._lazy_frame = frame
        self._lazy_label = label
        self._lazy_placement = None
        # A CURRENT child is pinned AT THE CALL: the caller read its record and hands the
        # tree in, so a rebuild of that child between this call and the force cannot change
        # what this build composes. A stale child's pin is its job's result, fixed when the
        # job was submitted; it is read when forced.
        self._lazy_tree: str | None = (
            (frame.pin(self._lazy_model, tree) if frame is not None else tree) if tree else None
        )
        # Where the parent called the child: the line a failure is reported at.
        self._lazy_call_site = _call_site()

    # --- the shape, forced on first read -----------------------------------------------

    @property
    def _wrapped(self):
        shape = self.__dict__.get("_lazy_shape")
        if shape is None and not self.__dict__.get("_lazy_forcing", False):
            self._force()
            shape = self.__dict__.get("_lazy_shape")
        return shape

    @_wrapped.setter
    def _wrapped(self, shape) -> None:
        self.__dict__["_lazy_shape"] = shape

    @property
    def _forced(self) -> bool:
        return self.__dict__.get("_lazy_shape") is not None

    @property
    def cad_material(self):
        """The pinned root finish, forcing only when no override was authored."""
        if "cad_material" not in self.__dict__ and not self._forced:
            self._force()
        if "cad_material" not in self.__dict__:
            raise AttributeError("cad_material")
        return self.__dict__["cad_material"]

    @cad_material.setter
    def cad_material(self, value) -> None:
        # A model may deliberately replace or clear its child's finish before
        # geometry is needed. _force preserves this key; the immutable partner
        # baseline then rejects the child as a link when the value changed.
        self.__dict__["cad_material"] = value

    @cad_material.deleter
    def cad_material(self) -> None:
        # Match an ordinary Shape's metadata semantics.  Force first so the
        # immutable partner captures the pinned value; deleting it afterwards
        # is then an authored metadata change and cannot be mistaken for an
        # unchanged linked child.
        if not self._forced:
            self._force()
        if "cad_material" not in self.__dict__:
            raise AttributeError("cad_material")
        del self.__dict__["cad_material"]

    @property
    def cad_face_ordinal_colors(self):
        """The pinned root face colors, with the same ownership as material."""
        if "cad_face_ordinal_colors" not in self.__dict__ and not self._forced:
            self._force()
        if "cad_face_ordinal_colors" not in self.__dict__:
            raise AttributeError("cad_face_ordinal_colors")
        return self.__dict__["cad_face_ordinal_colors"]

    @cad_face_ordinal_colors.setter
    def cad_face_ordinal_colors(self, value) -> None:
        self.__dict__["cad_face_ordinal_colors"] = value

    @cad_face_ordinal_colors.deleter
    def cad_face_ordinal_colors(self) -> None:
        if not self._forced:
            self._force()
        if "cad_face_ordinal_colors" not in self.__dict__:
            raise AttributeError("cad_face_ordinal_colors")
        del self.__dict__["cad_face_ordinal_colors"]

    # --- what the parent may do without waiting ------------------------------------

    def moved(self, loc):  # type: ignore[override]
        from build123d import Plane

        if isinstance(loc, Plane):
            loc = loc.location
        if self._forced:
            # Already forced: build123d's own moved() keeps the TShape (a link)
            # and deep-copies the wrapper's attributes, tags included.
            return Compound.moved(self, loc)
        clone = LazyCompound.__new__(LazyCompound)
        clone._lazy_shape = None
        clone._lazy_forcing = False
        Compound.__init__(clone, None, label=self.label)
        clone.__dict__.update({k: v for k, v in self.__dict__.items() if k.startswith("_lazy_")})
        clone.color = self.color
        for key in ("cad_material", "cad_face_ordinal_colors"):
            if key in self.__dict__:
                clone.__dict__[key] = copy.deepcopy(self.__dict__[key])
        clone._lazy_placement = loc if self._lazy_placement is None else loc * self._lazy_placement
        return clone

    def __iter__(self):
        # build123d's ``Location.__mul__`` probes its right operand with ``list(other)``
        # before giving up and letting ``Shape.__rmul__`` place it. Iterating a promise
        # would force it, so ``Pos * child`` -- the one placement form every body uses --
        # would wait for the child right there. Refusing the probe (TypeError is what a
        # non-iterable raises, and what that code catches) hands the operator to
        # ``__rmul__`` -> ``moved()``, which defers. Any OTHER iteration forces: a body
        # that walks a child's parts needs the parts.
        if not self._forced and sys._getframe(1).f_code.co_name == "__mul__":
            raise TypeError("a pending child is placed, not iterated")
        return Compound.__iter__(self)

    def __deepcopy__(self, memo):
        # ``moved()`` and ``copy.copy`` deep-copy the wrapper (then re-place the same
        # TShape). The job and the frame are not copyable and are not geometry: the copy
        # is a plain Compound of the forced result, tags included, with the same
        # TopoDS copy semantics build123d's own ``Shape.__deepcopy__`` uses.
        shape = self._wrapped  # forces
        result = Compound.__new__(Compound)
        memo[id(self)] = result
        memo[id(shape)] = downcast(BRepBuilderAPI_Copy(shape).Shape())
        result._wrapped = memo[id(shape)]
        for key, value in self.__dict__.items():
            if key.startswith("_lazy_"):
                continue
            if key == "topo_parent":
                result.topo_parent = value
            else:
                setattr(result, key, copy.deepcopy(value, memo))
            if key == "joints":
                for joint in result.joints.values():
                    joint.parent = result
        return result

    # --- forcing -----------------------------------------------------------------

    @property
    def model(self) -> str:
        return self._lazy_model

    @property
    def model_name(self) -> str:
        from cadgen.store.index import split_model_ref

        script, function = split_model_ref(self._lazy_model)
        return f"{script.name}::{function}" if function and function != script.stem else script.name

    @property
    def pending(self) -> bool:
        """True while the child's build has not been waited for."""
        return self._lazy_tree is None and self._lazy_job is not None

    def tree_hash(self) -> str:
        """The tree this child resolves to in this build. Waits for the job."""
        if self._lazy_tree is not None:
            return self._lazy_tree
        job = self._lazy_job
        if job is not None:
            if getattr(job, "done", True):
                code = job.wait()
            else:
                # A waiting parent does no kernel work: give its job slot back for the
                # wait and take one again after (cadgen.daemon.broker).
                from cadgen.daemon.broker import yielded

                with yielded():
                    code = job.wait()
            if code != 0:
                raise ChildBuildError(
                    f"child model {self.model_name} failed to build "
                    f"(called at {self._lazy_call_site}):\n{job.output().rstrip()}"
                )
        record = _read_record(self._lazy_model) or {}
        tree = str(record.get("tree") or "")
        if not tree:
            raise ChildBuildError(
                f"child model {self.model_name} built but left no record "
                f"(called at {self._lazy_call_site})"
            )
        frame = self._lazy_frame
        self._lazy_tree = frame.pin(self._lazy_model, tree) if frame is not None else tree
        return self._lazy_tree

    def _force(self) -> None:
        if self._lazy_forcing:
            raise RuntimeError(f"child model {self.model_name} forced re-entrantly")
        self._lazy_forcing = True
        try:
            tree = self.tree_hash()
            material_overridden = "cad_material" in self.__dict__
            face_colors_overridden = "cad_face_ordinal_colors" in self.__dict__
            compound = _materialize_tree(tree, self._lazy_label)
            shape = compound.wrapped
            if self._lazy_placement is not None:
                shape = shape.Moved(self._lazy_placement.wrapped)
            self._lazy_shape = shape
            if not self.label:
                self.label = compound.label
            if self.color is None and getattr(compound, "color", None) is not None:
                self.color = compound.color
            for key, overridden in (
                ("cad_material", material_overridden),
                ("cad_face_ordinal_colors", face_colors_overridden),
            ):
                if overridden:
                    continue
                if key in compound.__dict__:
                    self.__dict__[key] = copy.deepcopy(compound.__dict__[key])
                else:
                    # No authored shell value exists, so an absent pinned value
                    # is authoritative. Never clear a model-authored override.
                    self.__dict__.pop(key, None)
            setattr(self, TREE_TAG, tree)
            # The child's own root placement rides along too: this shape is
            # ``placement * root`` and the packager divides the root back out of
            # the link it records (materialize.ROOT_LOC_TAG).
            setattr(self, ROOT_LOC_TAG, getattr(compound, ROOT_LOC_TAG, None))
            # Reads that descend (a parent inspecting the child's parts) see the
            # materialized structure; a link is written before any descent. The
            # children are transplanted, not re-attached: anytree's attach hook
            # rebuilds a Compound's shape from its children, which would replace
            # the placed shape above with an unplaced one of a different TShape.
            # build123d's own booleans move children the same way.
            kids = list(compound.__dict__.get("_NodeMixin__children") or [])
            self.__dict__["_NodeMixin__children"] = kids
            for child in kids:
                child.__dict__["_NodeMixin__parent"] = self
            holder = getattr(compound, PARTNER_TAG, None)
            setattr(self, PARTNER_TAG, holder.retarget(self) if isinstance(holder, _Partner) else _Partner(self))
        finally:
            self._lazy_forcing = False


def _read_record(model: Path) -> dict | None:
    from cadgen.store.records import read_record

    return read_record(model)


def materialize_model(tree: str, *, label: str) -> Compound:
    """The geometry a model's tree stands for, as a plain Compound: what a
    top-level call returns after its build (cadgen.authoring)."""
    return _materialize_tree(tree, label)


def _materialize_tree(tree: str, label: str) -> Compound:
    return materialize(tree, label=label)


_CADGEN_PACKAGE = str(Path(__file__).resolve().parents[1])


def _call_site() -> str:
    """The first frame outside the cadgen package: where the model author called the child."""
    for frame in reversed(traceback.extract_stack(limit=30)):
        filename = str(frame.filename)
        if filename.startswith(_CADGEN_PACKAGE) or filename.startswith("<"):
            continue
        return f"{frame.filename}:{frame.lineno}"
    return "<unknown>"
