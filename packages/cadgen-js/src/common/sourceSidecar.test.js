import assert from "node:assert/strict";
import test from "node:test";

import {
  applySourceAppearance,
  loadSourceSidecar,
  normalizeSourceAppearance,
  SOURCE_SIDECAR_SCHEMA_VERSION,
  validateSourceSidecar
} from "./sourceSidecar.js";

const DOCUMENT_HASH = "a".repeat(64);

function descriptor() {
  return {
    kind: "assembly-package",
    occurrences: [
      { id: "o1.1", component: "cid-a", name: "base" },
      { id: "o1.2", component: "cid-b", name: "cap", material: { roughness: 0.8 } }
    ]
  };
}

test("appearance accepts only finite supported unit-interval channels", () => {
  assert.deepEqual(normalizeSourceAppearance({ occurrences: {
    "o1.2": { roughness: 0.25, metalness: 1, clearcoat: 0.5, clearcoatRoughness: 0, opacity: 0.9 }
  } }), { occurrences: {
    "o1.2": { clearcoat: 0.5, clearcoatRoughness: 0, metalness: 1, opacity: 0.9, roughness: 0.25 }
  } });
  for (const value of [NaN, Infinity, -0.1, 1.1, "0.5", true]) {
    assert.throws(
      () => normalizeSourceAppearance({ occurrences: { "o1.1": { roughness: value } } }),
      /finite number between 0 and 1/
    );
  }
  assert.throws(
    () => normalizeSourceAppearance({ occurrences: { "o1.1": { sheen: 0.5 } } }),
    /supported PBR channels/
  );
  assert.throws(() => normalizeSourceAppearance({ occurrences: {}, extra: true }), /only an occurrences/);
});

test("appearance composition owns changed occurrences and leaves the stored descriptor unchanged", () => {
  const stored = descriptor();
  const composed = applySourceAppearance(stored, {
    occurrences: { "o1.2": { metalness: 0.7, roughness: 0.2 } }
  });
  assert.notEqual(composed, stored);
  assert.notEqual(composed.occurrences, stored.occurrences);
  assert.equal(composed.occurrences[0], stored.occurrences[0]);
  assert.deepEqual(composed.occurrences[1].material, { metalness: 0.7, roughness: 0.2 });
  assert.deepEqual(stored.occurrences[1].material, { roughness: 0.8 });
  assert.throws(
    () => applySourceAppearance(stored, { occurrences: { missing: { opacity: 0.5 } } }),
    /missing document occurrence missing/
  );
  const prototypeIdAppearance = { occurrences: Object.fromEntries([
    ["__proto__", { roughness: 0.3 }]
  ]) };
  assert.deepEqual(
    normalizeSourceAppearance(prototypeIdAppearance),
    prototypeIdAppearance,
    "a valid object key must not disappear through Object.prototype"
  );
  assert.throws(
    () => applySourceAppearance(stored, prototypeIdAppearance),
    /missing document occurrence __proto__/
  );
});

test("one stored tree can compose distinct saved-document finishes", () => {
  const stored = descriptor();
  const brushed = applySourceAppearance(stored, {
    occurrences: { "o1.1": { metalness: 0.8, roughness: 0.35 } }
  });
  const painted = applySourceAppearance(stored, {
    occurrences: { "o1.1": { metalness: 0, roughness: 0.7 } }
  });
  assert.deepEqual(brushed.occurrences[0].material, { metalness: 0.8, roughness: 0.35 });
  assert.deepEqual(painted.occurrences[0].material, { metalness: 0, roughness: 0.7 });
  assert.equal(stored.occurrences[0].material, undefined);
});

test("sidecars are schema and document bound", () => {
  const valid = {
    schemaVersion: SOURCE_SIDECAR_SCHEMA_VERSION,
    documentHash: DOCUMENT_HASH,
    appearance: { occurrences: { "o1.1": { roughness: 0.4 } } }
  };
  assert.deepEqual(validateSourceSidecar(valid, {
    url: "/part.step.json",
    documentHash: DOCUMENT_HASH
  }).appearance, valid.appearance);
  assert.throws(
    () => validateSourceSidecar({ ...valid, documentHash: "b".repeat(64) }, {
      url: "/part.step.json", documentHash: DOCUMENT_HASH
    }),
    /does not match STEP sha256/
  );
  assert.throws(
    () => validateSourceSidecar({ ...valid, schemaVersion: SOURCE_SIDECAR_SCHEMA_VERSION - 1 }, {
      url: "/part.step.json", documentHash: DOCUMENT_HASH
    }),
    /unsupported sidecar schema/
  );
});

test("a mutable sidecar URL is never retained as immutable content", async (t) => {
  const originalFetch = globalThis.fetch;
  let fetches = 0;
  const url = `/part.step.json?v=${Date.now()}-${Math.random()}`;
  globalThis.fetch = async () => {
    fetches += 1;
    return new Response(JSON.stringify({
      schemaVersion: SOURCE_SIDECAR_SCHEMA_VERSION,
      documentHash: DOCUMENT_HASH,
      appearance: { occurrences: { "o1.1": { clearcoat: fetches === 1 ? 0.4 : 0.9 } } }
    }));
  };
  t.after(() => { globalThis.fetch = originalFetch; });
  const first = await loadSourceSidecar(url, { documentHash: DOCUMENT_HASH });
  const second = await loadSourceSidecar(url, { documentHash: DOCUMENT_HASH });
  assert.equal(first.appearance.occurrences["o1.1"].clearcoat, 0.4);
  assert.equal(second.appearance.occurrences["o1.1"].clearcoat, 0.9);
  assert.equal(fetches, 2);
});
