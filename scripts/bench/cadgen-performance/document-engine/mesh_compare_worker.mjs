// Private comparison worker for mesh_compare.py. This is benchmark tooling;
// neither the SURF path nor this protocol is a production fallback.
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { createInterface } from "node:readline";

import { parseSurf } from "../../../../packages/cadgen-js/src/lib/surf/container.js";
import {
  edgeClassesFromSurfIndex,
  encodeComponentTessellation,
} from "../../../../packages/cadgen-js/src/lib/surf/tessellationCache.js";
import {
  DEFAULT_OPTIONS,
  TESSELLATION_VERSION,
  tessellateComponent,
} from "../../../../packages/cadgen-js/src/lib/surf/tessellate.js";

const reply = (value) => process.stdout.write(`${JSON.stringify(value)}\n`);
const digest = (bytes) => createHash("sha256").update(bytes).digest("hex");

reply({
  ready: true,
  node: process.version,
  tessellatorVersion: TESSELLATION_VERSION,
  defaultOptions: DEFAULT_OPTIONS,
});

const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of lines) {
  let request = null;
  try {
    request = JSON.parse(line);
    if (request?.command === "close") {
      reply({ id: request.id, closed: true });
      break;
    }
    const started = performance.now();
    const sourceBytes = readFileSync(request.input);
    const readFinished = performance.now();
    const arrayBuffer = sourceBytes.buffer.slice(
      sourceBytes.byteOffset,
      sourceBytes.byteOffset + sourceBytes.byteLength,
    );
    const { index, floats } = parseSurf(arrayBuffer);
    const decoded = performance.now();
    const options = {
      chordTolerance: request.chordTolerance,
      loopTolerance: request.loopTolerance,
      angleTolerance: request.angleTolerance,
    };
    const component = tessellateComponent(index, floats, options);
    const tessellated = performance.now();
    const sourceDigest = digest(sourceBytes);
    const packed = encodeComponentTessellation(component, {
      surfaceInput: sourceDigest,
      surfaceObject: sourceDigest,
      tessellation: options,
      edgeClasses: edgeClassesFromSurfIndex(index),
    });
    const packedAt = performance.now();
    writeFileSync(request.output, packed);
    const written = performance.now();
    const sourceEdgeOrds = index.edges.map((edge) => edge.ord);
    const meshEdgeOrds = component.edges.map((edge) => edge.ord);
    const meshEdgeSet = new Set(meshEdgeOrds);
    reply({
      id: request.id,
      stagesMs: {
        surfRead: readFinished - started,
        decode: decoded - readFinished,
        tessellate: tessellated - decoded,
        pack: packedAt - tessellated,
        tessWrite: written - packedAt,
        requestTotal: written - started,
      },
      sourceBytes: sourceBytes.length,
      packetBytes: packed.length,
      sourceFaceOrds: index.faces.map((face) => face.ord),
      meshFaceOrds: component.faceRanges.map((range) => range.ord),
      sourceEdgeOrds,
      meshEdgeOrds,
      omittedEdges: index.edges
        .filter((edge) => !meshEdgeSet.has(edge.ord))
        .map((edge) => ({ ord: edge.ord, class: edge.class, hasCurve: Boolean(edge.curve) })),
      counts: {
        positions: component.positions.length / 3,
        triangles: component.indices.length / 3,
        sourceFaces: index.faces.length,
        meshFaces: component.faceRanges.length,
        sourceEdges: index.edges.length,
        meshEdges: component.edges.length,
      },
      bounds: component.bounds,
      scale: component.scale,
    });
  } catch (error) {
    reply({
      id: request?.id ?? null,
      error: error instanceof Error ? `${error.name}: ${error.message}` : String(error),
    });
  }
}
