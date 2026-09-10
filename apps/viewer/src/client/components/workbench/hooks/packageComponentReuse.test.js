import assert from "node:assert/strict";
import test from "node:test";

import {
  matchingDisplayedPackageContext,
  retainedComponentMeshesForRevision,
} from "./packageComponentReuse.js";

const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);
const SURF_A = "1".repeat(64);
const CID = "0123456789abcdef";

function descriptor(surfObject = SURF_A) {
  return { components: { [CID]: { surf: `components/${CID}.surf`, surfObject } } };
}

function meshUrl(tree) {
  return `/__cad/store?file=/${tree}&v=${tree}`;
}

test("an unchanged concrete surface stays retained across a tree revision", () => {
  const meshData = { lodLevel: 0, vertices: new Float32Array(3) };
  const previous = {
    descriptor: descriptor(),
    meshUrl: meshUrl(HASH_A),
    componentMeshDataByCid: { [CID]: meshData },
    componentLodLevelByCid: { [CID]: 0 },
  };
  const retained = retainedComponentMeshesForRevision({
    previous,
    descriptor: descriptor(),
    meshUrl: meshUrl(HASH_B),
  });
  assert.equal(retained[CID], meshData);
});

test("reuse rejects changed surface objects, changed exact levels and noncanonical sources", () => {
  const meshData = { lodLevel: 0 };
  const previous = {
    descriptor: descriptor(),
    meshUrl: meshUrl(HASH_A),
    componentMeshDataByCid: { [CID]: meshData },
    componentLodLevelByCid: { [CID]: 0 },
  };
  assert.deepEqual(retainedComponentMeshesForRevision({
    previous,
    descriptor: descriptor("2".repeat(64)),
    meshUrl: meshUrl(HASH_B),
  }), {});

  const changedLevel = { ...previous, componentLodLevelByCid: { [CID]: 1 } };
  assert.deepEqual(retainedComponentMeshesForRevision({
    previous: changedLevel,
    descriptor: descriptor(),
    meshUrl: meshUrl(HASH_B),
  }), {}, "the retained mesh's stamped L0 and requested L1 cannot alias");

  assert.deepEqual(retainedComponentMeshesForRevision({
    previous: { ...previous, meshUrl: `/elsewhere?file=/${HASH_A}` },
    descriptor: descriptor(),
    meshUrl: `/elsewhere?file=/${HASH_B}`,
  }), {}, "legacy and scoped URLs remain source-bound");
});

test("A remains the bounded reuse source after B staging fails or is superseded by C", () => {
  const meshData = { lodLevel: 0 };
  const displayedA = {
    file: "assembly.step",
    meshHash: "tree-a",
    complete: true,
    descriptor: descriptor(),
    meshUrl: meshUrl(HASH_A),
    componentMeshDataByCid: { [CID]: meshData },
    componentLodLevelByCid: { [CID]: 0 },
  };
  const visibleA = {
    file: "assembly.step",
    meshHash: "tree-a",
    assemblyInteractionReady: true,
  };

  const stagingB = { requestId: 2, file: "assembly.step", meshHash: "tree-b", complete: false };
  assert.equal(
    matchingDisplayedPackageContext(displayedA, visibleA, stagingB.file),
    displayedA,
    "staging does not replace displayed ownership",
  );
  assert.equal(
    matchingDisplayedPackageContext(stagingB, visibleA, stagingB.file),
    null,
    "partial work can never regain displayed ownership after failure",
  );

  const sourceForC = matchingDisplayedPackageContext(displayedA, visibleA, "assembly.step");
  const retainedForC = retainedComponentMeshesForRevision({
    previous: sourceForC,
    descriptor: descriptor(),
    meshUrl: meshUrl(HASH_B),
  });
  assert.equal(retainedForC[CID], meshData);
  assert.equal(
    matchingDisplayedPackageContext(displayedA, { ...visibleA, meshHash: "other" }, "assembly.step"),
    null,
    "a context not backing the visible mesh is never reused",
  );
});
