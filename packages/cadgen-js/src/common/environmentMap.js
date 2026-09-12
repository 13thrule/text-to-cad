import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

import {
  getEnvironmentPresetById
} from "./themeSettings.js";

export const PROCEDURAL_STUDIO_ENVIRONMENT_ID = "studio-softbox";

function environmentPreset(settings = {}) {
  return getEnvironmentPresetById(settings.presetId);
}

function proceduralEnvironmentSize(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return 256;
  }
  return Math.min(Math.max(2 ** Math.round(Math.log2(numeric)), 64), 1024);
}

export function environmentResourceIdentity(settings = {}, { size = 256 } = {}) {
  if (settings.enabled !== true) {
    return "";
  }
  const preset = environmentPreset(settings);
  if (preset?.kind === "procedural") {
    return `procedural:${preset.id}@${proceduralEnvironmentSize(size)}`;
  }
  const url = String(preset?.url || "").trim();
  return url ? `texture:${url}` : "";
}

function ownedEnvironmentResource(identity, texture, disposeOwned) {
  let disposed = false;
  return {
    identity,
    texture,
    dispose() {
      if (disposed) {
        return;
      }
      disposed = true;
      disposeOwned?.();
    }
  };
}

/**
 * Create one environment resource owned by the caller. Procedural studios keep
 * their PMREM render target alive for exactly as long as its texture is in use;
 * callers must release the returned resource instead of disposing only the
 * texture. Remote image presets retain their existing TextureLoader behavior.
 */
export async function createEnvironmentResource(renderer, settings = {}, {
  textureLoader = null,
  size = 256
} = {}) {
  const identity = environmentResourceIdentity(settings, { size });
  if (!identity) {
    return null;
  }
  const preset = environmentPreset(settings);
  if (preset?.kind === "procedural") {
    if (!renderer) {
      throw new Error("A WebGL renderer is required for the procedural studio environment");
    }
    const room = new RoomEnvironment();
    const generator = new THREE.PMREMGenerator(renderer);
    try {
      // Preserve the source softbox shapes. Material roughness selects the
      // appropriate PMREM mip; source blur would erase polished-part detail at
      // every roughness and defeat the higher-resolution Render policy.
      const target = generator.fromScene(room, 0, 0.1, 100, {
        size: proceduralEnvironmentSize(size)
      });
      target.texture.name = preset.label || preset.id;
      return ownedEnvironmentResource(identity, target.texture, () => target.dispose());
    } finally {
      room.dispose();
      generator.dispose();
    }
  }

  const loader = textureLoader || new THREE.TextureLoader();
  if (typeof loader.setCrossOrigin === "function") {
    loader.setCrossOrigin("anonymous");
  }
  let texture = null;
  try {
    texture = await loader.loadAsync(String(preset?.url || "").trim());
    texture.mapping = THREE.EquirectangularReflectionMapping;
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.needsUpdate = true;
    return ownedEnvironmentResource(identity, texture, () => texture.dispose?.());
  } catch (error) {
    texture?.dispose?.();
    throw error;
  }
}

export function disposeEnvironmentResource(resource) {
  resource?.dispose?.();
}
