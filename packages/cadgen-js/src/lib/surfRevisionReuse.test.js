import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  loadRenderSurf,
  loadRenderSurfPayloadAtLevel,
  loadRenderSurfSelectorBundle,
  releaseRenderSurfLevel,
  surfTessellationCacheKey,
} from "./renderAssetClient.js";
import { setRenderAssetSourceScope } from "./renderAssetSourceScope.js";
import { setTessellationCacheProvider } from "./surf/tessellationCache.js";

const fixture = readFileSync(new URL("./surf/fixtures/sun_gear.surf", import.meta.url));
const identity = { surfObject: createHash("sha256").update(fixture).digest("hex") };
const url = (tree, cid = "123456789abcdef0", extra = "") =>
  `/__cad/store?file=${tree.repeat(64)}/components/${cid}.surf${extra}`;
const key = (value, options, object = identity) => surfTessellationCacheKey(value, options, object);

test("immutable SURF identity survives tree revisions but preserves all mesh inputs", () => {
  assert.equal(key(url("a")), key(url("b")));
  assert.equal(key(url("a", undefined, "&v=first")), key(url("b", undefined, "&v=second")));
  assert.equal(key(url("a", undefined, "&q=1&mode=x")), key(url("b", undefined, "&mode=x&q=1")));
  assert.notEqual(key(url("a")), key(url("b"), undefined, { surfObject: "c".repeat(64) }));
  assert.notEqual(key(url("a")), key(url("b", "fedcba9876543210")));
  assert.notEqual(key(url("a")), key(url("b"), { chordTolerance: 0.002, angleTolerance: 1.4 }));
  assert.notEqual(key(url("a", undefined, "&mode=x")), key(url("b", undefined, "&mode=y")));
  assert.notEqual(key(`https://one.example${url("a")}`), key(`https://two.example${url("b")}`));
});

test("noncanonical URLs and incomplete identities retain URL isolation", () => {
  for (const object of [undefined, {}, { surfObject: "abc" }, { surfObject: "x".repeat(64) }]) {
    assert.notEqual(surfTessellationCacheKey(url("a"), undefined, object),
      surfTessellationCacheKey(url("b"), undefined, object));
  }
  assert.notEqual(key("/arbitrary/a.surf"), key("/arbitrary/b.surf"));
  assert.notEqual(key(`${url("a")}&file=other`), key(`${url("b")}&file=other`));
  assert.notEqual(key("/__cad/store?file=local/components/123456789abcdef0.surf"), key(url("b")));
});

test("revisions reuse meshes and exact selector payloads without fetching unchanged objects", async (t) => {
  setTessellationCacheProvider(null);
  let fetches = 0;
  t.mock.method(globalThis, "fetch", async () => {
    fetches += 1;
    return new Response(fixture);
  });
  const first = url("1");
  const second = url("2");
  const mesh = await loadRenderSurf(first, { identity });
  const firstFetches = fetches;
  assert.equal(await loadRenderSurf(second, { identity }), mesh);
  assert.equal(fetches, firstFetches);
  const selectors = await loadRenderSurfSelectorBundle(first, { identity });
  assert.ok(selectors.manifest);
  assert.equal(await loadRenderSurfSelectorBundle(second, { identity }), selectors);
  assert.equal(fetches, firstFetches);

  const tessellation = { chordTolerance: 0.002, angleTolerance: 1.4 };
  const payload = await loadRenderSurfPayloadAtLevel(first, { identity, tessellation });
  assert.equal(await loadRenderSurfPayloadAtLevel(second, { identity, tessellation }), payload);
  assert.notEqual(payload.bundle, selectors, "selectors must follow the concrete mesh parameters");
  assert.equal(fetches, firstFetches);

  assert.ok(releaseRenderSurfLevel(second, { identity, tessellation }) > 0);
  assert.ok(payload.meshData, "release drops cache ownership, not an active scene's payload");
  const replacement = await loadRenderSurfPayloadAtLevel(first, { identity, tessellation });
  assert.notEqual(replacement, payload);
  assert.equal(await loadRenderSurf(second, { identity }), mesh, "another concrete level remains owned");
});

test("snapshot source collision guard remains active even with an object identity", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response(fixture));
  const asset = url("3");
  setRenderAssetSourceScope("snapshot-A.step");
  try {
    assert.notEqual(key(asset), key(url("4")), "scoped snapshots retain URL identity");
    await loadRenderSurf(asset, { identity });
    setRenderAssetSourceScope("snapshot-B.step");
    await assert.rejects(loadRenderSurf(asset, { identity }), { name: "RenderAssetSourceScopeError" });
  } finally {
    setRenderAssetSourceScope("");
  }
});
