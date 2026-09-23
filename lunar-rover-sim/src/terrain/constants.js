// World layout. All distances are metres, +Y is up.

export const MOON_RADIUS = 1737400;
export const LUNAR_G = 1.62;

// Macro height map: the drivable area.
export const MACRO_SIZE = 4096;
export const MACRO_MIN = -MACRO_SIZE / 2;

// Far height map: horizon & mountains.
export const FAR_SIZE = 32768;
export const FAR_MIN = -FAR_SIZE / 2;

// Blend band where the macro map fades into the far map.
export const BLEND_START = 1780;
export const BLEND_END = 1980;

// Tileable detail relief.
export const DETAIL_TILE = 128;
export const DETAIL_B_SCALE = 2.7;
export const DETAIL_B_AMP = 0.75;
export const DETAIL_B_ROT = 0.65;
export const DETAIL_B_OFFSET = [37.1, -11.9];

// Tileable micro regolith (normal/albedo only).
export const MICRO_TILE = 2;

// Distance ranges over which geometric detail fades out (vertex shader).
export const DETAIL_A_FADE = [90, 260];
export const DETAIL_B_FADE = [320, 900];

// Sun shadow maps (cascades) cover this distance from the camera; beyond it
// the baked horizon visibility takes over.
export const CSM_FAR = 220;
// Baked "far occluder" visibility starts marching after this distance.
export const BAKED_NEAR_SKIP = 140;
