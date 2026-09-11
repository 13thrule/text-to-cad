#!/usr/bin/env node
// Source-only retained-scene boundary benchmark. This intentionally excludes
// STEP generation, preview transport, browser frames, and compositor work.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { performance } from "node:perf_hooks";
import * as THREE from "../../../packages/cadgen-js/node_modules/three/build/three.module.js";
import { buildComposedPackageMeshData } from "../../../packages/cadgen-js/src/lib/assembly/meshData.js";
import { buildModel } from "../../../packages/cadgen-js/src/common/cadScene.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const output = process.argv[2] || path.join(here, "results/r3-incremental-cpu-current.json");
const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];

function component(seed = 0) {
  return {
    vertices: new Float32Array([seed, 0, 0, seed + 1, 0, 0, seed, 1, 0]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
    indices: new Uint32Array([0, 1, 2]),
    parts: [{ id: "local", occurrenceId: "local", triangleOffset: 0, triangleCount: 1 }],
    bounds: { min: [seed, 0, 0], max: [seed + 1, 1, 0] },
    lodLevel: 1,
  };
}

function descriptor(count, moved = -1) {
  const occurrences = Array.from({ length: count }, (_, index) => ({
    id: `o${index}`,
    name: `part ${index}`,
    component: index % 2 ? "b" : "a",
    transform: index === moved
      ? [1, 0, 0, index + 2, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
      : [1, 0, 0, index, ...identity.slice(4)],
  }));
  return {
    kind: "assembly-package",
    components: { a: {}, b: {} },
    occurrences,
    assembly: {
      root: {
        id: "root",
        name: "root",
        nodeType: "assembly",
        children: occurrences.map(item => ({
          id: item.id, name: item.name, nodeType: "part", children: [],
        })),
      },
    },
  };
}

function run(count, iterations) {
  const components = { a: component(0), b: component(2) };
  let description = descriptor(count);
  let mesh = buildComposedPackageMeshData(description, components);
  const scene = buildModel(THREE, mesh, {
    renderPartsIndividually: true,
    displayMode: "shaded",
  });
  let compositionMs = 0;
  let sceneUpdateMs = 0;
  for (let index = 0; index < iterations; index += 1) {
    description = descriptor(count, index % count);
    let began = performance.now();
    const next = buildComposedPackageMeshData(description, components, { previous: mesh });
    compositionMs += performance.now() - began;
    began = performance.now();
    scene.update({ source: next });
    sceneUpdateMs += performance.now() - began;
    mesh = next;
  }
  scene.dispose();
  return {
    occurrences: count,
    iterations,
    compositionTotalMs: compositionMs,
    compositionPerRevisionMs: compositionMs / iterations,
    sceneUpdateTotalMs: sceneUpdateMs,
    sceneUpdatePerRevisionMs: sceneUpdateMs / iterations,
  };
}

const result = {
  status: "passed",
  measuredAt: new Date().toISOString(),
  node: process.version,
  scope: "synchronous composition and cadScene.update only",
  measurements: [run(24, 100), run(240, 40)],
};
fs.mkdirSync(path.dirname(path.resolve(output)), { recursive: true });
fs.writeFileSync(output, `${JSON.stringify(result, null, 2)}\n`);
console.log(JSON.stringify(result));
