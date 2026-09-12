// One neutral product-photography rig shared by the direct light and the HDR
// reflection cards. Public rotation moves these directions together about Z.
// The key sits above and to the side of the default isometric camera: a
// camera-aligned key flattens cylinders and hides depth between assembly parts.
export const PHOTOGRAPHIC_STUDIO_KEY_DIRECTION = Object.freeze([-0.35, -1, 1.5]);
// The broad rear fill reflects into horizontal surfaces viewed from iso, so
// polished plates and black plastic retain detail instead of reflecting void.
export const PHOTOGRAPHIC_STUDIO_FILL_DIRECTION = Object.freeze([-0.65, 0.8, 0.6]);

// Calibrated together at 0 EV. PMREM also supplies diffuse illumination, so
// its key card and the shadow-casting spotlight share the illumination budget.
export const PHOTOGRAPHIC_STUDIO_KEY_ILLUMINANCE = 2.1;
export const PHOTOGRAPHIC_STUDIO_CARD_RADIANCE = 8;
export const PHOTOGRAPHIC_STUDIO_ROOM_RADIANCE = 0.04;
// A small backdrop-colored floor fill keeps the opaque stage legible in the
// dark studio and prevents contact shadows from collapsing to black. This is
// material-local emission: it does not alter the model or the calibrated rig.
export const PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_INTENSITY = 0.12;
export const PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_NEUTRAL_MIX = 0.02;

// Full square-ground width relative to model-bounds radius. Keep the camera's
// fitted far padding on this same multiplier so the ordinary-depth frustum
// contains the stage instead of cutting an artificial horizon through it.
// The plane remains two triangles, so increasing its extent adds no geometry.
export const PHOTOGRAPHIC_STUDIO_STAGE_RADIUS_MULTIPLIER = 96;
