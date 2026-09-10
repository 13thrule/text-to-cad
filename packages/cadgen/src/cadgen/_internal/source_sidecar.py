"""The source sidecar: everything SOURCE-derived a generated model carries.

The tree (in the user-level store, keyed by the document's content
hash) is a pure function of the STEP file's bytes plus schema versions — the
cache engine's world, freely evictable. The model's DECLARATIONS live in ONE
sidecar FILE BESIDE THE MODEL, ``<name>.step.json``: KINEMATICS
(typed mates with axes resolved to world numbers, couplings, pose presets)
and APPEARANCE (intrinsic PBR values keyed by canonical document occurrence).
Choreography and mesh-export declarations are not here. The render module
beside the document (``<name>.step.js``) is authored, loaded by
the viewer by name, and read by no build. The one hash here is
``documentHash``: an artifact binding that prevents declarations from being
applied to different STEP bytes after a partial copy or replacement. It is not
source identity or provenance. No source paths, closure hashes, or timestamps
belong here; provenance lives in the RECORDS tier below. The
sidecar sits beside the model because declarations cannot be re-derived from
the STEP bytes: evicting the store must never lose kinematics. New capability
= new SECTION + schema bump, never a second sidecar file.

A sidecar exists ONLY when the model NEEDS kinematics or appearance. A plain
model — geometry and nothing else — writes no sidecar at all; its provenance and freshness ride
the PROVENANCE RECORD in the evictable records tier (bottom of this module),
which every generated build writes and every gate reads — the ONE home of
source-derived identity. Eviction costs one rebuild, never correctness (an
evicted record simply reads as an import until the next build re-records it).
Imports write neither.

Write ordering matters: the named STEP and sidecar land before the model record
that makes their tree current, so a resolvable package never races a missing
sidecar.
Readers are lock-blind and tolerate a MISSING sidecar; a sidecar that is
present must declare ``SOURCE_SIDECAR_SCHEMA_VERSION``, because reading
sections out of a file written to a different shape is how a model silently
loses its kinematics.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from cadgen._internal.atomic_replace import replace_atomic, temp_suffix

# APPENDED to the artifact's whole name, so the pair sorts and reads together:
# `part.step` -> `part.step.json`. Never match a sidecar on this suffix alone —
# it is `.json`, which every unrelated JSON file also ends with. Construct the
# path from the artifact (:func:`source_sidecar_path`), or match the artifact
# suffix too (`.step.json` / `.stp.json`).
SOURCE_SIDECAR_SUFFIX = ".json"
# 7: documentHash binds resolved kinematics to the exact STEP bytes they name.
# 6: the animation and meshExports sections are gone. Choreography is the render
#    module beside the document (`<name>.step.js`), loaded by the viewer and never
#    by a build; a mesh door tessellates the document's tree and writes the file
#    it was asked for, and what a model declares lives in its record. A sidecar
#    is written for kinematics alone. 5 moved provenance OUT of the sidecar.
# 8: intrinsic PBR finishes are durable, document-bound occurrence annotations.
SOURCE_SIDECAR_SCHEMA_VERSION = 8

# What a sidecar may CONTAIN: declarations plus the exact-document binding.
# Anything source-derived-as-provenance (paths, closure hashes, timestamps)
# belongs to the provenance record; a sidecar sits beside the artifact and
# ships with it.
_SIDECAR_SECTIONS = ("schemaVersion", "documentHash", "kinematics", "appearance")
MATERIAL_KEYS = ("roughness", "metalness", "clearcoat", "clearcoatRoughness", "opacity")


def source_sidecar_path(step_path: Path | str) -> Path:
    """``<name>.step`` -> ``<name>.step.json``, beside the model."""
    artifact = Path(step_path)
    return artifact.with_name(artifact.name + SOURCE_SIDECAR_SUFFIX)


class SidecarSchemaError(ValueError):
    """A sidecar file that is not at the schema this cadgen reads."""


class SidecarBindingError(ValueError):
    """A sidecar bound to different STEP bytes than the adjacent document."""


class SidecarAppearanceError(ValueError):
    """An appearance annotation is invalid or targets a missing occurrence."""


def normalize_appearance(block: object) -> dict[str, Any] | None:
    """Validate resolved, source-free PBR values; return fresh canonical data."""
    if block is None:
        return None
    if not isinstance(block, dict) or set(block) != {"occurrences"}:
        raise SidecarAppearanceError("appearance must contain only an occurrences object")
    occurrences = block["occurrences"]
    if not isinstance(occurrences, dict):
        raise SidecarAppearanceError("appearance.occurrences must be an object keyed by occurrence id")
    if any(not isinstance(key, str) or not key.strip() for key in occurrences):
        raise SidecarAppearanceError("appearance occurrence ids must be nonempty strings")
    normalized = {}
    for occurrence_id, material in sorted(occurrences.items()):
        if not isinstance(material, dict) or not material or set(material) - set(MATERIAL_KEYS):
            raise SidecarAppearanceError(f"appearance {occurrence_id}: expected supported PBR channels: {', '.join(MATERIAL_KEYS)}")
        values = {}
        for key, value in sorted(material.items()):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise SidecarAppearanceError(f"appearance {occurrence_id}.{key}: expected a finite number between 0 and 1")
            values[key] = float(value)
        normalized[occurrence_id] = values
    return {"occurrences": normalized} if normalized else None


def appearance_digest(block: object) -> str:
    """A stable variant input, including the absence of appearance overrides."""
    payload = json.dumps(normalize_appearance(block), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_appearance_targets(descriptor: Mapping[str, Any], block: object) -> dict[str, Any] | None:
    """Validate annotation targets without copying an assembly for catalog scans."""
    appearance = normalize_appearance(block)
    if appearance is None:
        return None
    occurrences = {str(item.get("id") or ""): item for item in descriptor.get("occurrences") or []}
    for occurrence_id in appearance["occurrences"]:
        target = occurrences.get(occurrence_id)
        if target is None or not target.get("component"):
            raise SidecarAppearanceError(f"appearance targets missing document occurrence {occurrence_id}")
    return appearance


def apply_appearance(descriptor: Mapping[str, Any], block: object) -> dict[str, Any]:
    """Compose artifact annotations into an owned descriptor, never a tree object."""
    appearance = validate_appearance_targets(descriptor, block)
    result = deepcopy(dict(descriptor))
    if appearance:
        materials = appearance["occurrences"]
        for occurrence in result.get("occurrences") or []:
            if occurrence.get("id") in materials:
                occurrence["material"] = materials[occurrence["id"]]
    return result


def _raw_source_sidecar(step_path: Path | str) -> dict[str, Any] | None:
    """The sidecar's JSON with NO schema gate. Only the writer's no-op compare
    and the schema gate itself may use this; every consumer of the SECTIONS
    goes through :func:`read_source_sidecar`."""
    try:
        payload = json.loads(source_sidecar_path(step_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def sidecar_schema_is_current(payload: Mapping[str, Any] | None) -> bool:
    return bool(payload) and payload.get("schemaVersion") == SOURCE_SIDECAR_SCHEMA_VERSION


def _verified_document_hash(step_path: Path | str, document_hash: str | None) -> str:
    if document_hash is None:
        from cadgen._internal.step_hash import step_file_hash

        return step_file_hash(Path(step_path))
    digest = str(document_hash).strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"document_hash must be a sha256 hex digest, got {document_hash!r}")
    return digest


def _binding_error(step_path: Path | str, found: object, expected: str) -> SidecarBindingError:
    artifact = Path(step_path)
    return SidecarBindingError(
        f"{source_sidecar_path(artifact).name}: documentHash {found or 'none'} does not match "
        f"{artifact.name} sha256 {expected} — rebuild the model (python {artifact.stem}.py) "
        f"or re-annotate the document (cadgen step build)"
    )


def read_source_sidecar(
    step_path: Path | str,
    *,
    document_hash: str | None = None,
) -> dict[str, Any] | None:
    """The document's declarations, or ``None`` when it has no sidecar.

    A sidecar that IS there must declare this schema: reading sections out of
    a file written to a different shape is how a model silently loses its
    kinematics. Missing/unreadable stays ``None`` (an import, or a plain model
    that declares nothing); wrong schema or a binding to different STEP bytes
    is an error with the fix. ``document_hash`` may carry a digest already
    computed from the bytes being resolved, avoiding a second read.
    """
    payload = _raw_source_sidecar(step_path)
    if payload is None:
        return None
    if not sidecar_schema_is_current(payload):
        found = payload.get("schemaVersion", "none")
        artifact = Path(step_path)
        raise SidecarSchemaError(
            f"{source_sidecar_path(artifact).name}: unsupported sidecar schema {found} "
            f"(expected {SOURCE_SIDECAR_SCHEMA_VERSION}) — rebuild the model "
            f"(python {artifact.stem}.py) or re-annotate the document "
            f"(cadgen step build)"
        )
    expected = _verified_document_hash(step_path, document_hash)
    found = str(payload.get("documentHash") or "").strip().lower()
    if found != expected:
        raise _binding_error(step_path, found, expected)
    if "appearance" in payload:
        payload["appearance"] = normalize_appearance(payload["appearance"])
    return payload


def model_is_generated(step_path: Path | str) -> bool:
    """Whether this artifact carries a sidecar this cadgen reads. Never
    raises: classification is not a render, and the loud refusal belongs to
    the readers of the SECTIONS."""
    return source_sidecar_matches_document(step_path)


def source_sidecar_matches_document(
    step_path: Path | str,
    *,
    document_hash: str | None = None,
) -> bool:
    """Whether a sidecar is current and bound to these STEP bytes.

    Classification and current gates need a non-throwing predicate. Readers
    use :func:`read_source_sidecar` to receive the teaching error.
    """
    payload = _raw_source_sidecar(step_path)
    if not sidecar_schema_is_current(payload):
        return False
    try:
        expected = _verified_document_hash(step_path, document_hash)
    except (OSError, ValueError):
        return False
    found = str(payload.get("documentHash") or "").strip().lower()
    return found == expected


# The sections that WARRANT a sidecar. Provenance alone does not: it also
# lives in the assembly.json, and a file per plain model is pure clutter.
_WARRANTING_SECTIONS = ("kinematics", "appearance")


def sidecar_is_warranted(payload: Mapping[str, Any] | None) -> bool:
    """Whether this payload carries anything the model actually needs a
    sidecar FOR. Kinematics and PBR finishes have artifact consumers;
    metadata with no reader beside the artifact belongs in the
    record, not in a file."""
    if not payload:
        return False
    return any(payload.get(section) for section in _WARRANTING_SECTIONS)


def write_source_sidecar(
    step_path: Path | str,
    payload: Mapping[str, Any],
    *,
    document_hash: str | None = None,
) -> None:
    """Write the sidecar — or, for a payload that warrants none, remove any
    stale one (a model that DROPPED its kinematics must lose the file).
    The written ``documentHash`` describes the adjacent STEP bytes, or the
    caller's already-verified digest for those bytes. Only the FILE: the
    build's provenance record stays."""
    body = {k: v for k, v in payload.items() if k in _SIDECAR_SECTIONS}
    if "appearance" in body:
        body["appearance"] = normalize_appearance(body["appearance"])
        if body["appearance"] is None:
            body.pop("appearance")
    if not sidecar_is_warranted(body):
        source_sidecar_path(step_path).unlink(missing_ok=True)
        return
    target = source_sidecar_path(step_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    body["schemaVersion"] = SOURCE_SIDECAR_SCHEMA_VERSION
    body["documentHash"] = _verified_document_hash(step_path, document_hash)
    # A rewrite that changes nothing but the timestamp is pure churn — for
    # committed sidecars (imported/ projects) it dirties git on every no-op.
    if _raw_source_sidecar(step_path) == body:
        return
    temp = target.with_name(f".{target.name}{temp_suffix()}")
    temp.write_text(json.dumps(body, sort_keys=True), encoding="utf-8")
    replace_atomic(temp, target)


def remove_source_sidecar(step_path: Path | str) -> None:
    """Imports must never leave a stale generated-marker behind (e.g. a
    re-import over a model that used to be generated)."""
    source_sidecar_path(step_path).unlink(missing_ok=True)


def read_source_provenance(step_path: Path | str) -> dict[str, Any] | None:
    """The document's source provenance, read from the STORE RECORD of the model
    behind it (``cadgen.store.records``): sourceKind, the script path relative
    to the document, and the closure. ``None`` for a document with no record.

    The provenance record file this used to read is gone; the model record is
    the one freshness memory (STORE.md)."""
    from cadgen.store.records import record_for_document, source_for_document

    document = Path(step_path)
    record = record_for_document(document)
    if record is None:
        return None
    from cadgen.store.index import split_model_ref

    source, _function = split_model_ref(source_for_document(document))
    payload: dict[str, Any] = {
        "sourceKind": str(record.get("sourceKind") or "python"),
        "sourceClosureHash": str((record.get("closure") or {}).get("hash") or ""),
        "sourceClosureFiles": list((record.get("closure") or {}).get("files") or []),
        "tree": str(record.get("tree") or ""),
    }
    for key in ("sourceHash", "annotationHash", "kinematics", "stepHash"):
        if record.get(key) is not None:
            payload[key] = record[key]
    try:
        document_resolved = document.expanduser().resolve()
    except (OSError, RuntimeError):
        document_resolved = document
    if str(source) != str(document_resolved):
        import os

        try:
            payload["sourcePath"] = os.path.relpath(str(source), str(document_resolved.parent))
        except ValueError:
            payload["sourcePath"] = str(source)
    return payload
