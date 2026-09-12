// One neutral product-photography rig shared by the direct light and the HDR
// reflection cards. Public rotation moves these directions together about Z.
export const PHOTOGRAPHIC_STUDIO_KEY_DIRECTION = Object.freeze([0.72, -0.62, 0.82]);
export const PHOTOGRAPHIC_STUDIO_FILL_DIRECTION = Object.freeze([-0.42, 0.78, 0.36]);

// Full square-ground width relative to model-bounds radius. Keep the camera's
// fitted far padding on this same multiplier so the ordinary-depth frustum
// contains the stage instead of cutting an artificial horizon through it.
// The plane remains two triangles, so increasing its extent adds no geometry.
export const PHOTOGRAPHIC_STUDIO_STAGE_RADIUS_MULTIPLIER = 96;
