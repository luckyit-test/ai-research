import * as THREE from 'three';
import { MACRO_MIN, MACRO_SIZE, FAR_MIN, FAR_SIZE, CSM_FAR } from '../terrain/constants.js';

const f = (v) => (Number.isInteger(v) ? v.toFixed(1) : String(v));

// Uniforms shared by every material that receives lunar lighting.
export const lunarUniforms = {
  uSunVisMacro: { value: null },
  uSunVisFar: { value: null },
  uBakedVisStrength: { value: 1 },
};

const DIFFUSE_LINE = 'reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseContribution ) * ( 1.0 - F );';

// McEwen lunar-Lambert photometric function with an opposition surge.
// Regolith is strongly back-scattering: surfaces facing away from the viewer
// do not darken like a Lambertian surface, and brightness surges when the Sun
// is behind the observer.
const LUNAR_DIFFUSE = /* glsl */ `
#ifdef LUNAR_BRDF
{
  float mu0 = max(dotNL, 1e-4);
  float mu = saturate(dot(geometryNormal, geometryViewDir));
  float g = degrees(acos(clamp(dot(directLight.direction, geometryViewDir), -1.0, 1.0)));
  float L = 0.75 * clamp(1.0 - 0.019 * g + 2.42e-4 * g * g - 1.46e-6 * g * g * g, 0.0, 1.0);
  float ls = 2.0 * mu0 / (mu0 + max(mu, 0.2) + 1e-3);
  float phot = (L * ls + (1.0 - L) * mu0) / mu0;
  float opp = 1.0 + 0.45 * exp(-g / 5.0);
  reflectedLight.directDiffuse += irradiance * phot * opp * BRDF_Lambert( material.diffuseContribution ) * ( 1.0 - F );
}
#else
  ${DIFFUSE_LINE}
#endif
`;

const PARS = /* glsl */ `
uniform sampler2D uSunVisMacro;
uniform sampler2D uSunVisFar;
uniform float uBakedVisStrength;
float lunarBakedVis(vec3 wp, float viewDist) {
  vec2 p = wp.xz;
  vec2 v;
  if (max(abs(p.x), abs(p.y)) < ${f(MACRO_SIZE / 2 - 8)}) {
    v = texture(uSunVisMacro, (p - ${f(MACRO_MIN)}) / ${f(MACRO_SIZE)}).rg;
  } else {
    v = texture(uSunVisFar, (p - ${f(FAR_MIN)}) / ${f(FAR_SIZE)}).rr;
  }
  float vis = mix(v.g, v.r, smoothstep(${f(CSM_FAR * 0.6)}, ${f(CSM_FAR * 0.92)}, viewDist));
  return mix(1.0, vis, uBakedVisStrength);
}
`;

let patchedLightsPars = null;
let patchedLightsBegin = null;

function lightsPars() {
  if (!patchedLightsPars) {
    const src = THREE.ShaderChunk.lights_physical_pars_fragment;
    if (!src.includes(DIFFUSE_LINE)) console.warn('lunarShading: diffuse line not found, lunar BRDF disabled');
    patchedLightsPars = src.replace(DIFFUSE_LINE, LUNAR_DIFFUSE);
  }
  return patchedLightsPars;
}

function lightsBegin() {
  if (!patchedLightsBegin) {
    const src = THREE.ShaderChunk.lights_fragment_begin;
    const anchor = 'getSunLightInfo( sunLight, directLight );';
    if (!src.includes(anchor)) console.warn('lunarShading: sun light anchor not found');
    patchedLightsBegin = src.replace(anchor, anchor + '\n\t\tdirectLight.color *= lunarSunVis;');
  }
  return patchedLightsBegin;
}

/**
 * Modifies a MeshStandardMaterial shader in onBeforeCompile.
 * worldPosExpr: GLSL expression for the fragment world position (defaults to
 * reconstruction from the view position).
 */
export function applyLunarShading(shader, { brdf = false, worldPosExpr = null } = {}) {
  Object.assign(shader.uniforms, lunarUniforms);
  shader.fragmentShader = shader.fragmentShader
    .replace('#include <common>', (brdf ? '#define LUNAR_BRDF\n' : '') + '#include <common>\n' + PARS)
    .replace('#include <lights_physical_pars_fragment>', lightsPars())
    .replace(
      '#include <lights_fragment_begin>',
      `float lunarSunVis = lunarBakedVis(${worldPosExpr || 'cameraPosition + transpose(mat3(viewMatrix)) * (-vViewPosition)'}, length(vViewPosition));\n` +
        lightsBegin(),
    );
}

/** Convenience for plain materials (rover parts, rocks...). */
export function patchMaterial(material, opts = {}) {
  const prev = material.onBeforeCompile;
  material.onBeforeCompile = (shader, renderer) => {
    if (prev) prev(shader, renderer);
    applyLunarShading(shader, opts);
  };
  const key = material.customProgramCacheKey ? material.customProgramCacheKey() : '';
  material.customProgramCacheKey = () => key + '|lunar' + (opts.brdf ? 'B' : '');
  material.needsUpdate = true;
}
