import assert from "node:assert/strict";
import test from "node:test";

import {
  PROCEDURAL_STUDIO_ENVIRONMENT_ID,
  createEnvironmentResource,
  disposeEnvironmentResource,
  environmentResourceIdentity
} from "./environmentMap.js";

test("environment resource identities distinguish the built-in softbox from remote textures", () => {
  assert.equal(PROCEDURAL_STUDIO_ENVIRONMENT_ID, "studio-softbox");
  assert.equal(environmentResourceIdentity({
    enabled: true,
    presetId: PROCEDURAL_STUDIO_ENVIRONMENT_ID
  }), "procedural:studio-softbox@256");
  assert.equal(environmentResourceIdentity({
    enabled: true,
    presetId: PROCEDURAL_STUDIO_ENVIRONMENT_ID
  }, { size: 512 }), "procedural:studio-softbox@512");
  assert.match(environmentResourceIdentity({
    enabled: true,
    presetId: "studio-hdri-43"
  }), /^texture:https:\/\//);
  assert.equal(environmentResourceIdentity({
    enabled: false,
    presetId: PROCEDURAL_STUDIO_ENVIRONMENT_ID
  }), "");
});

test("remote environment resources have idempotent caller-owned disposal", async () => {
  let crossOrigin = "";
  let disposeCount = 0;
  const texture = {
    dispose() {
      disposeCount += 1;
    }
  };
  const resource = await createEnvironmentResource(null, {
    enabled: true,
    presetId: "studio-hdri-43"
  }, {
    textureLoader: {
      setCrossOrigin(value) {
        crossOrigin = value;
      },
      async loadAsync() {
        return texture;
      }
    }
  });

  assert.equal(crossOrigin, "anonymous");
  assert.equal(resource.texture, texture);
  disposeEnvironmentResource(resource);
  disposeEnvironmentResource(resource);
  assert.equal(disposeCount, 1);
});

test("procedural environments require the renderer that owns their PMREM", async () => {
  await assert.rejects(
    createEnvironmentResource(null, {
      enabled: true,
      presetId: PROCEDURAL_STUDIO_ENVIRONMENT_ID
    }),
    /WebGL renderer is required/
  );
});
