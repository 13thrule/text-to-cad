// Sidecar -> viewer runtime for the mates half. The sidecar's KINEMATICS
// section (typed mates, resolved axes, couplings, presets) becomes a
// step-module definition — one number slider per DOF, an update pass that
// folds slider values through the shared FK evaluator into per-occurrence
// matrix effects. Pure data in, arithmetic out: no authored JS is involved on
// this path. Choreography is the render module BESIDE the document
// (`<name>.step.js`, renderModule.js) and never touches the sidecar or this
// module; the two meet only in the effect records.

import {
  kinematicsAtRest,
  kinematicsDeltas,
  kinematicsDofs,
  kinematicsMates,
  kinematicsPoses
} from "./kinematicsRuntime.js";
import { normalizeStepModuleDefinition } from "./stepModule.js";

// The sidecar schema this runtime reads. Mirrors cadgen's
// source_sidecar.SOURCE_SIDECAR_SCHEMA_VERSION and the viewer's
// packageContract.mjs; pinned across the three by
// tests/python/global/test_render_contract_sync.py.
export const SOURCE_SIDECAR_SCHEMA_VERSION = 6;

function isObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function stripHash(ref) {
  return String(ref || "").replace(/^#/, "");
}

// Column-major THREE.Matrix4 elements -> the row-major flat 16 the effects
// matrix spec takes.
function rowMajor16(matrix) {
  const e = matrix.elements;
  return [
    e[0], e[4], e[8], e[12],
    e[1], e[5], e[9], e[13],
    e[2], e[6], e[10], e[14],
    e[3], e[7], e[11], e[15]
  ];
}

// Mate target subtrees may NEST: a servo group fastened to a gripper frame,
// whose output horn — a part inside that group — is fastened to the moving
// jaw beside it. Both mates legitimately name the horn, one by carrying its
// group and one explicitly.
//
// kinematicsDeltas returns ACCUMULATED WORLD deltas, not increments: the
// horn's delta already contains the whole jaw chain. Applying both to the
// horn (effects.transform premultiplies) counts the upstream motion twice and
// detaches the horn from the jaw it is bolted to. So each part takes exactly
// one delta: the one from the MOST SPECIFIC mate naming it — the smallest
// resolved target set it belongs to, which for nested sets is the deepest
// mate. That mate owns its leaves; the outer mate carries only what no deeper
// mate claimed.
//
// `resolve` is the effects api's own target resolution, so ownership is
// decided over exactly the parts the transform would have moved.
export function kinematicsDeltaTargets(deltas, resolve) {
  const entries = [];
  for (const [ref, delta] of deltas.entries()) {
    const partIds = resolve(stripHash(ref)) || [];
    if (partIds.length) {
      entries.push({ delta, partIds });
    }
  }
  const ownerByPartId = new Map();
  for (const entry of entries) {
    for (const partId of entry.partIds) {
      const owner = ownerByPartId.get(partId);
      // Equal-sized sets are two mates over the same parts, which the mate
      // tree rule (one parent mate per occurrence) already forbids upstream;
      // taking the later declaration keeps this deterministic either way.
      if (!owner || entry.partIds.length <= owner.partIds.length) {
        ownerByPartId.set(partId, entry);
      }
    }
  }
  const owned = new Map();
  for (const [partId, owner] of ownerByPartId.entries()) {
    const partIds = owned.get(owner);
    if (partIds) {
      partIds.push(partId);
    } else {
      owned.set(owner, [partId]);
    }
  }
  return [...owned.entries()].map(([owner, partIds]) => ({ delta: owner.delta, partIds }));
}

export function stepModuleFromKinematics(block) {
  if (!isObject(block) || !kinematicsMates(block).length) {
    return null;
  }
  const dofs = kinematicsDofs(block);
  const parameters = {};
  for (const dof of dofs) {
    const limits = Array.isArray(dof.limits) ? dof.limits : [0, 1];
    parameters[dof.id] = {
      type: "number",
      label: dof.id,
      min: limits[0],
      max: limits[1],
      default: 0,
      unit: dof.kind === "revolute" ? "deg" : dof.kind === "coupling" ? "" : "mm"
    };
  }
  // Every mated occurrence becomes a feature keyed by the authored label. It
  // resolves by NAME (the stable form the instance tree carries) AND, when the
  // build resolved one, by the occurrence id the sidecar recorded beside the
  // label: id matching is what covers a SUBASSEMBLY, because a group is not a
  // rendered part and so has no leaf name of its own, while an id matches its
  // whole subtree by prefix. A mate on a group carries its parts either way.
  const features = {};
  for (const mate of kinematicsMates(block)) {
    for (const [ref, id] of [[mate.parent, mate.parentId], [mate.child, mate.childId]]) {
      const label = stripHash(ref);
      if (!label || features[label]) {
        continue;
      }
      const occurrenceId = stripHash(id);
      features[label] = occurrenceId
        ? { ref: `#${occurrenceId}`, names: [label] }
        : { names: [label] };
    }
  }
  return {
    manifest: {
      schemaVersion: 1,
      parameters,
      features,
      kinematics: block,
      poses: kinematicsPoses(block)
    },
    update(ctx) {
      const values = isObject(ctx?.params) ? ctx.params : {};
      if (kinematicsAtRest(block, values)) {
        return;
      }
      const deltas = kinematicsDeltas(ctx.THREE, block, values);
      const targets = kinematicsDeltaTargets(deltas, (target) => ctx.effects.resolve(target));
      for (const { partIds, delta } of targets) {
        ctx.effects.transform({ partIds }, { matrix: rowMajor16(delta) });
      }
    }
  };
}

// Reading sections out of a sidecar written to a different shape is how a
// model silently loses its kinematics, so the schema is checked before any
// section is touched. The viewer surfaces this as the step-module load error.
// The sidecar's own filename, whether the url is a plain path or the viewer's
// `/__cad/asset?file=<path>` form (whose LAST path segment is "asset").
function sidecarName(url) {
  const text = String(url || "").split("#")[0];
  const query = /[?&]file=([^&]+)/.exec(text);
  const target = query ? decodeURIComponent(query[1]) : text.split("?")[0];
  return target.replace(/\\/g, "/").split("/").filter(Boolean).pop() || "sidecar";
}

function sidecarSections(sidecar, url) {
  const schemaVersion = sidecar?.schemaVersion;
  if (schemaVersion !== SOURCE_SIDECAR_SCHEMA_VERSION) {
    const name = sidecarName(url);
    const model = name.replace(/\.(step|stp)\.json$/i, "");
    throw new Error(
      `${name}: unsupported sidecar schema ${schemaVersion ?? "none"} `
      + `(expected ${SOURCE_SIDECAR_SCHEMA_VERSION}) — rebuild the model `
      + `(python ${model}.py) or re-annotate the document (cadgen step build)`
    );
  }
  return sidecar;
}

async function fetchSidecar(sidecarUrl) {
  const url = String(sidecarUrl || "").trim();
  if (!url) {
    return null;
  }
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load model sidecar: HTTP ${response.status}`);
  }
  return sidecarSections(await response.json(), url);
}

/** Fetch the model's sidecar (<name>.step.json) and compile its
 * kinematics section into a normalized step-module definition. Models with no
 * kinematics resolve to null (nothing to pose). */
export async function loadKinematicsModuleDefinition(sidecarUrl, { cadPath = "" } = {}) {
  const sidecar = await fetchSidecar(sidecarUrl);
  if (!sidecar) {
    return null;
  }
  const raw = stepModuleFromKinematics(sidecar.kinematics);
  if (!raw) {
    return null;
  }
  return normalizeStepModuleDefinition(raw, { url: String(sidecarUrl).trim(), cadPath });
}
