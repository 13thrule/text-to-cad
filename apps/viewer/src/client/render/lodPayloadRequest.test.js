import assert from "node:assert/strict";
import test from "node:test";
import { lodPayloadRequest, matchesLodPayloadRequest } from "./lodPayloadRequest.js";

test("a payload is pinned to its loaded descriptor, component and full concrete tessellation key", () => {
  const identity = { cid: "a", surf: "a.surf", sha256: "123" }, descriptor = { components: { a: identity } };
  const context = { descriptor, file: "same.step" }, url = "/objects/a.surf";
  const request = lodPayloadRequest({ cid: "a", descriptor, file: context.file, identity, surfUrl: url }, 2);
  assert.equal(matchesLodPayloadRequest(request, context, "a", 2, url), true);
  for (const [ctx, cid, level, path] of [
    [{ ...context, descriptor: { ...descriptor } }, "a", 2, url],
    [{ ...context, file: "new.step" }, "a", 2, url], [context, "b", 2, url],
    [context, "a", 1, url], [context, "a", 2, "/other/a.surf"],
  ]) assert.equal(matchesLodPayloadRequest(request, ctx, cid, level, path), false);
  assert.equal(matchesLodPayloadRequest({ ...request, key: "wrong" }, context, "a", 2, url), false);
  assert.equal(matchesLodPayloadRequest(null, context, "a", 2, url), false);
});
