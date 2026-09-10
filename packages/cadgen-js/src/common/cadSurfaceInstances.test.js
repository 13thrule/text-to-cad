import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import {
  buildCadSurfaceInstanceSets,
  dissolveCadSurfaceInstanceSets,
  surfaceInstancingStateEligible,
  syncCadSurfaceInstanceRecord,
} from "./cadSurfaceInstances.js";

function record(id, geometry, x, { mirrored = false } = {}) {
  const material = new THREE.MeshStandardMaterial({ color: id === "a" ? "#ff0000" : "#00ff00" });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.matrixAutoUpdate = false;
  mesh.matrix.makeScale(mirrored ? -1 : 1, 1, 1).setPosition(x, 0, 0);
  mesh.userData = { partId: id, faceIds: new Uint32Array([x]) };
  return { partId: id, mesh, geometry, material, baseColor: material.color.clone(), baseEmissiveIntensity: 0 };
}

test("compatible surfaces share one draw and keep per-instance identity and transforms", () => {
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const group = new THREE.Group();
  const records = [record("a", geometry, 2), record("b", geometry, 7)];
  records.forEach((item) => group.add(item.mesh));
  const sets = buildCadSurfaceInstanceSets(THREE, records, group);
  const [set] = sets;
  let objectDisposes = 0;
  set.object.addEventListener("dispose", () => { objectDisposes += 1; });
  assert.equal(group.children.length, 3, "two hidden pick proxies plus one rendered instance draw");
  assert.equal(set.object.isInstancedMesh, true);
  assert.equal(set.matrixValues, set.object.instanceMatrix.array, "dirty checks reuse the upload array");
  assert.equal(set.colorValues, set.object.instanceColor.array, "color dirty checks need no CPU mirror");
  assert.deepEqual(set.object.userData.partIds, ["a", "b"]);
  assert.equal(set.object.userData.faceIdsByInstance[1][0], 7);
  const matrix = new THREE.Matrix4();
  set.object.getMatrixAt(1, matrix);
  assert.equal(matrix.elements[12], 7);
  records[1].mesh.matrix.makeTranslation(11, 0, 0);
  syncCadSurfaceInstanceRecord(records[1]);
  set.object.getMatrixAt(1, matrix);
  assert.equal(matrix.elements[12], 11);
  const matrixVersion = set.object.instanceMatrix.version;
  const colorVersion = set.object.instanceColor.version;
  const materialVersion = set.object.material.version;
  const originalCopy = set.object.material.copy;
  let materialCopies = 0;
  set.object.material.copy = function (...args) {
    materialCopies += 1;
    return originalCopy.apply(this, args);
  };
  syncCadSurfaceInstanceRecord(records[1]);
  syncCadSurfaceInstanceRecord(records[0]);
  assert.equal(set.object.instanceMatrix.version, matrixVersion, "stable transforms schedule no upload");
  assert.equal(set.object.instanceColor.version, colorVersion, "stable colours schedule no upload");
  assert.equal(set.object.material.version, materialVersion, "stable pass state avoids material copy/configure");
  assert.equal(materialCopies, 0);
  dissolveCadSurfaceInstanceSets(sets, group);
  assert.equal(group.children.length, 2);
  assert.equal(objectDisposes, 1, "InstancedMesh releases its private instance GPU attributes");
  dissolveCadSurfaceInstanceSets(sets, group);
  assert.equal(objectDisposes, 1, "dissolve is idempotent");
  geometry.dispose();
  records.forEach((item) => item.material.dispose());
});

test("mirrored placements and incompatible mutable states stay on ordinary meshes", () => {
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const group = new THREE.Group();
  const records = [
    record("a", geometry, 0),
    record("b", geometry, 1),
    record("mirror", geometry, 2, { mirrored: true }),
  ];
  records.forEach((item) => group.add(item.mesh));
  const sets = buildCadSurfaceInstanceSets(THREE, records, group);
  assert.equal(sets.size, 1);
  assert.ok(records[0].surfaceInstance && records[1].surfaceInstance);
  assert.equal(records[2].surfaceInstance, undefined, "negative determinant keeps Three.js mirrored-normal handling");
  dissolveCadSurfaceInstanceSets(sets, group);
  assert.equal(surfaceInstancingStateEligible({}), true);
  assert.equal(surfaceInstancingStateEligible({ selection: { selectedPartIds: ["a"] } }), true);
  assert.equal(surfaceInstancingStateEligible({ stepParameters: {} }), true, "mutable effects are handled per record");
  geometry.dispose();
  records.forEach((item) => item.material.dispose());
});

test("opaque generated-surface vertex colours remain shared and instanced", () => {
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(
    Array.from({ length: geometry.getAttribute("position").count * 3 }, (_, index) => (
      index % 3 === 0 ? 0.25 : index % 3 === 1 ? 0.5 : 0.75
    )),
    3
  ));
  const group = new THREE.Group();
  const records = [record("a", geometry, 0), record("b", geometry, 2)];
  for (const item of records) {
    item.hasVertexColors = true;
    item.material.vertexColors = true;
    item.material.color.set(0xffffff);
    group.add(item.mesh);
  }
  const sets = buildCadSurfaceInstanceSets(THREE, records, group);
  const [set] = sets;
  assert.equal(sets.size, 1, "shared vertex colours do not block the ordinary opaque path");
  assert.equal(set.object.material.vertexColors, true);
  assert.equal(set.object.renderOrder, records[0].mesh.renderOrder);
  assert.deepEqual(set.object.instanceColor.array.slice(0, 3), new Float32Array([1, 1, 1]));

  records[1].material.transparent = true;
  records[1].material.opacity = 0.5;
  const reconciled = buildCadSurfaceInstanceSets(THREE, records, new THREE.Group());
  assert.equal(reconciled.size, 0, "a true alpha-blended occurrence stays an ordinary mesh");
  dissolveCadSurfaceInstanceSets(sets, group);
  geometry.dispose();
  records.forEach((item) => item.material.dispose());
});
