function materialPassKey(material) {
  return JSON.stringify({
    type: material?.type || "",
    vertexColors: material?.vertexColors === true,
    roughness: Number(material?.roughness),
    metalness: Number(material?.metalness),
    clearcoat: Number(material?.clearcoat),
    clearcoatRoughness: Number(material?.clearcoatRoughness),
    emissiveIntensity: Number(material?.emissiveIntensity) || 0,
    side: material?.side,
    depthTest: material?.depthTest !== false,
    depthWrite: material?.depthWrite !== false,
    polygonOffset: material?.polygonOffset === true,
    polygonOffsetFactor: Number(material?.polygonOffsetFactor) || 0,
    polygonOffsetUnits: Number(material?.polygonOffsetUnits) || 0,
  });
}

function recordPassKey(record) {
  return `${materialPassKey(record?.material)}#order=${Number(record?.mesh?.renderOrder) || 0}`;
}

function instancingCandidate(record) {
  const matrix = record?.mesh?.matrix;
  return Boolean(
    record?.geometry &&
    record?.mesh &&
    record?.material &&
    record.material.transparent !== true &&
    Number(record.material.opacity) >= 0.999 &&
    record.effectVisible !== false &&
    !record.tubeDeformationState &&
    matrix?.determinant?.() >= 0
  );
}

export function surfaceInstancingStateEligible(settings = {}) {
  return !["transparent", "wireframe"].includes(String(settings.displayMode || "").trim()) &&
    Number(settings.materialSettings?.opacity ?? 1) >= 0.999;
}

function configureInstanceMaterial(material) {
  material.visible = true;
  material.color?.set?.(0xffffff);
  // Instance colour carries the occurrence's authored/fill colour through
  // both diffuse and the viewer's subtle base emissive response.
  if (material.emissive && Number(material.emissiveIntensity) > 0) {
    material.emissive.set(0xffffff);
  }
  material.onBeforeCompile = (shader) => {
    shader.fragmentShader = shader.fragmentShader.replace(
      "#include <emissivemap_fragment>",
      "#include <emissivemap_fragment>\n#ifdef USE_COLOR\ntotalEmissiveRadiance *= vColor.rgb;\n#endif"
    );
  };
  material.customProgramCacheKey = () => "cad-surface-instance-emissive-v1";
}

function materialSyncKey(material) {
  return JSON.stringify({
    pass: materialPassKey(material),
    opacity: Number(material?.opacity),
    alphaTest: Number(material?.alphaTest),
    blending: material?.blending,
    toneMapped: material?.toneMapped !== false,
    clipIntersection: material?.clipIntersection === true,
    clipShadows: material?.clipShadows === true,
    clippingPlanes: (material?.clippingPlanes || []).map((plane) => [
      Number(plane?.normal?.x) || 0,
      Number(plane?.normal?.y) || 0,
      Number(plane?.normal?.z) || 0,
      Number(plane?.constant) || 0,
    ]),
  });
}

function float32Changed(values, offset, source, count) {
  for (let index = 0; index < count; index += 1) {
    if (values[offset + index] !== Math.fround(source[index])) return true;
  }
  return false;
}

function storeFloat32(values, offset, source, count) {
  for (let index = 0; index < count; index += 1) values[offset + index] = source[index];
}

// Collapse compatible occurrence meshes into one draw. Records retain their
// private Mesh as a transform/picking metadata proxy. Its material is hidden,
// so it issues no draw, while remaining in the scene graph for world-matrix
// updates and the viewer's existing per-record raycast path.
export function buildCadSurfaceInstanceSets(THREE, records, modelGroup) {
  const byGeometry = new Map();
  for (const record of records || []) {
    if (!instancingCandidate(record)) continue;
    let byPass = byGeometry.get(record.geometry);
    if (!byPass) byGeometry.set(record.geometry, (byPass = new Map()));
    const key = recordPassKey(record);
    const group = byPass.get(key) || [];
    group.push(record);
    byPass.set(key, group);
  }
  const sets = new Set();
  for (const byPass of byGeometry.values()) {
    for (const group of byPass.values()) {
      if (group.length < 2) continue;
      const material = group[0].material.clone();
      configureInstanceMaterial(material);
      const object = new THREE.InstancedMesh(group[0].geometry, material, group.length);
      object.name = "CadSurfaceInstances";
      object.castShadow = true;
      object.receiveShadow = false;
      object.renderOrder = Number(group[0].mesh.renderOrder) || 0;
      object.userData.partIds = group.map((record) => record.partId);
      object.userData.faceIdsByInstance = group.map((record) => record.mesh.userData.faceIds || null);
      object.frustumCulled = false;
      const set = {
        object,
        records: group,
        disposed: false,
        matrixValues: new Float32Array(group.length * 16),
        colorValues: new Float32Array(group.length * 3),
        materialKey: materialSyncKey(group[0].material),
        groupPassKey: recordPassKey(group[0]),
        activeSlots: new Uint8Array(group.length).fill(1),
        zeroMatrix: new THREE.Matrix4().makeScale(0, 0, 0),
      };
      group.forEach((record, slot) => {
        record.material.visible = false;
        record.mesh.userData.cadSurfaceInstanceProxy = true;
        record.surfaceInstance = { set, slot };
        object.setMatrixAt(slot, record.mesh.matrix);
        const color = record.material.color || record.baseColor || new THREE.Color(0xffffff);
        object.setColorAt(slot, color);
        storeFloat32(set.matrixValues, slot * 16, record.mesh.matrix.elements, 16);
        storeFloat32(set.colorValues, slot * 3, [color.r, color.g, color.b], 3);
      });
      object.instanceMatrix.needsUpdate = true;
      if (object.instanceColor) object.instanceColor.needsUpdate = true;
      modelGroup.add(object);
      sets.add(set);
    }
  }
  return sets;
}

function disposeSurfaceInstanceSet(set, modelGroup) {
  if (!set || set.disposed) return;
  set.disposed = true;
  (set.object.parent || modelGroup)?.remove(set.object);
  set.object.dispose?.();
  set.object.material?.dispose?.();
  for (const record of set.records) {
    record.surfaceInstance = null;
    record.material.visible = true;
    delete record.mesh.userData.cadSurfaceInstanceProxy;
  }
}

export function dissolveCadSurfaceInstanceSets(sets, modelGroup) {
  for (const set of sets || []) {
    // InstancedMesh owns instanceMatrix/instanceColor GPU attributes even
    // though its component geometry is shared. Its dispose event releases
    // those renderer-side buffers without disposing the shared geometry.
    disposeSurfaceInstanceSet(set, modelGroup);
  }
  sets?.clear?.();
}

function setSlotActive(set, record, active) {
  const slot = record.surfaceInstance?.slot;
  if (!Number.isInteger(slot) || set.disposed || Boolean(set.activeSlots[slot]) === active) return;
  set.activeSlots[slot] = active ? 1 : 0;
  record.material.visible = !active;
  if (active) record.mesh.userData.cadSurfaceInstanceProxy = true;
  else delete record.mesh.userData.cadSurfaceInstanceProxy;
  const matrix = active ? record.mesh.matrix : set.zeroMatrix;
  set.object.setMatrixAt(slot, matrix);
  storeFloat32(set.matrixValues, slot * 16, matrix.elements, 16);
  set.object.instanceMatrix.needsUpdate = true;
}

// Reconcile mutable visual state without rebuilding compatible instance
// buffers. Selected/hovered/dimmed records temporarily use their ordinary
// meshes; the unaffected majority stays in the existing InstancedMesh and the
// same slots re-activate when the transient state clears.
export function reconcileCadSurfaceInstanceSets(THREE, records, modelGroup, sets = new Set()) {
  const currentRecords = new Set(records || []);
  const assigned = new Set();
  for (const set of [...sets]) {
    const membershipIntact = set.records.every((record) => (
      currentRecords.has(record) && record.surfaceInstance?.set === set
    ));
    const active = membershipIntact ? set.records.filter(instancingCandidate) : [];
    const activePass = active[0] ? recordPassKey(active[0]) : "";
    const compatible = active.length >= 2 && active.every((record) => recordPassKey(record) === activePass);
    if (!membershipIntact || !compatible) {
      disposeSurfaceInstanceSet(set, modelGroup);
      sets.delete(set);
      continue;
    }
    set.groupPassKey = activePass;
    const activeSet = new Set(active);
    for (const record of set.records) {
      assigned.add(record);
      setSlotActive(set, record, activeSet.has(record));
    }
    const representative = active[0];
    const nextMaterialKey = materialSyncKey(representative.material);
    if (nextMaterialKey !== set.materialKey) {
      set.object.material.copy(representative.material);
      configureInstanceMaterial(set.object.material);
      set.materialKey = nextMaterialKey;
    }
  }

  const unassigned = (records || []).filter((record) => !assigned.has(record) && instancingCandidate(record));
  for (const set of buildCadSurfaceInstanceSets(THREE, unassigned, modelGroup)) sets.add(set);
  return sets;
}

export function syncCadSurfaceInstanceRecord(record) {
  const instance = record?.surfaceInstance;
  if (!instance || instance.set.disposed) return;
  const { set, slot } = instance;
  if (!set.activeSlots[slot]) return;
  if (instance.slot === 0) {
    const nextMaterialKey = materialSyncKey(record.material);
    if (nextMaterialKey !== set.materialKey) {
      set.object.material.copy(record.material);
      configureInstanceMaterial(set.object.material);
      set.materialKey = nextMaterialKey;
    }
  }
  const matrixOffset = slot * 16;
  if (float32Changed(set.matrixValues, matrixOffset, record.mesh.matrix.elements, 16)) {
    set.object.setMatrixAt(slot, record.mesh.matrix);
    storeFloat32(set.matrixValues, matrixOffset, record.mesh.matrix.elements, 16);
    set.object.instanceMatrix.needsUpdate = true;
  }
  const color = record.material.color || record.baseColor;
  const colorValues = [color.r, color.g, color.b];
  const colorOffset = slot * 3;
  if (float32Changed(set.colorValues, colorOffset, colorValues, 3)) {
    set.object.setColorAt(slot, color);
    storeFloat32(set.colorValues, colorOffset, colorValues, 3);
    if (set.object.instanceColor) set.object.instanceColor.needsUpdate = true;
  }
}
