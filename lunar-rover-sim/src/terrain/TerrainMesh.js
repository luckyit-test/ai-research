import * as THREE from 'three';
import { terrainSamplingGLSL } from './sampling.js';
import { FAR_SIZE, MOON_RADIUS, CSM_FAR } from './constants.js';
import { applyLunarShading } from '../render/lunarShading.js';

const f = (v) => (Number.isInteger(v) ? v.toFixed(1) : String(v));

/** Unit grid in XZ ([0,1]²) with skirts: position.y = 1 marks skirt vertices. */
function createGridGeometry(n) {
  const verts = [];
  for (let j = 0; j <= n; j++) {
    for (let i = 0; i <= n; i++) verts.push(i / n, 0, j / n);
  }
  const idx = (i, j) => j * (n + 1) + i;
  const indices = [];
  for (let j = 0; j < n; j++) {
    for (let i = 0; i < n; i++) {
      const a = idx(i, j), b = idx(i + 1, j), c = idx(i, j + 1), d = idx(i + 1, j + 1);
      if ((i + j) & 1) indices.push(a, c, b, b, c, d);
      else indices.push(a, d, b, a, c, d);
    }
  }
  // skirts (both windings so they are visible from either side)
  const border = [];
  for (let i = 0; i < n; i++) border.push([idx(i, 0), idx(i + 1, 0)]);
  for (let j = 0; j < n; j++) border.push([idx(n, j), idx(n, j + 1)]);
  for (let i = n; i > 0; i--) border.push([idx(i, n), idx(i - 1, n)]);
  for (let j = n; j > 0; j--) border.push([idx(0, j), idx(0, j - 1)]);
  const skirtOf = new Map();
  const skirt = (v) => {
    if (!skirtOf.has(v)) {
      skirtOf.set(v, verts.length / 3);
      verts.push(verts[v * 3], 1, verts[v * 3 + 2]);
    }
    return skirtOf.get(v);
  };
  for (const [u, v] of border) {
    const su = skirt(u), sv = skirt(v);
    indices.push(u, v, su, v, sv, su);
    indices.push(u, su, v, v, su, sv);
  }
  const geo = new THREE.InstancedBufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
  geo.setIndex(indices);
  return geo;
}

function makeNodeAttribute(capacity) {
  const attr = new THREE.InstancedBufferAttribute(new Float32Array(capacity * 4), 4);
  attr.setUsage(THREE.DynamicDrawUsage);
  return attr;
}

const SKIRT_K = 0.035;

export const TERRAIN_VERTEX_PARS = (data) => /* glsl */ `
attribute vec4 aNode;
uniform vec3 uCamPos;
uniform float uHeightOffset;
varying vec3 vTerrainPos;
${terrainSamplingGLSL(data.macroRes, data.farRes)}
vec4 macroInfoLod(vec2 p) {
  float w = terrainBlendW(p);
  vec4 fi = textureLod(uFarInfo, (p - FAR_MIN) / ${f(FAR_SIZE)}, 0.0);
  if (w >= 1.0) return fi;
  vec4 mi = textureLod(uMacroInfo, (p - MACRO_MIN) / ${f(data.macroRes * data.macroTexel)}, 0.0);
  return mix(mi, fi, w);
}
`;

const TERRAIN_VERTEX_BEGIN = /* glsl */ `
vec2 tWp = aNode.xy + position.xz * aNode.z;
float tCamDist = length(tWp - uCamPos.xz);
float tH = baseHeight(tWp) + detailHeightV(tWp, tCamDist) + uHeightOffset;
tH -= position.y * (aNode.z * ${f(SKIRT_K)} + 0.4);
vec3 transformed = vec3(tWp.x, tH, tWp.y);
vTerrainPos = transformed;
vec2 tRel = tWp - uCamPos.xz;
transformed.y -= dot(tRel, tRel) * ${f(0.5 / MOON_RADIUS)};
`;

const TERRAIN_FRAGMENT_PARS = /* glsl */ `
varying vec3 vTerrainPos;
uniform sampler2D uTracks;
uniform vec4 uTrackWin; // center x, center z, world size, texel size (m)
uniform float uTrackStrength;
uniform vec3 uAlbedoTint;
uniform float uAlbedo;

vec3 trackSample(vec2 p) {
  // returns (rut depth, tread, fade) — the track map is a toroidal window
  vec2 rel = abs(p - uTrackWin.xy);
  float fade = 1.0 - smoothstep(uTrackWin.z * 0.40, uTrackWin.z * 0.48, max(rel.x, rel.y));
  if (fade <= 0.0) return vec3(0.0);
  vec2 t = texture(uTracks, p / uTrackWin.z).rg;
  return vec3(t, fade);
}
`;

// Fragment: compute terrain normal & albedo from gradients of all layers.
const TERRAIN_FRAGMENT_MAP = /* glsl */ `
vec2 tp = vTerrainPos.xz;
float tDist = length(vViewPosition);
vec4 tMi = macroInfo(tp);
vec4 tDa = texture(uDetail, detailUvA(tp));
vec4 tDb = texture(uDetail, detailUvB(tp));
float tBw = 1.0 - terrainBlendW(tp);
vec2 tGrad = tMi.xy + (tDa.yz + DB_AMP * (transpose(DB_ROT) * tDb.yz)) * tBw;

// micro regolith: two rotated scales
vec4 tM1 = texture(uMicro, tp / MICRO_TILE);
vec4 tM2 = texture(uMicro, (mat2(0.28, 0.96, -0.96, 0.28) * tp) / (MICRO_TILE * 0.37) + 0.31);
float tMf = 1.0 - smoothstep(12.0, 80.0, tDist);
vec2 tGm = ((tM1.xy - 0.5) * 1.1 + (tM2.xy - 0.5) * 0.6) * tMf;
tGrad += tGm;
// mid-distance rubble: the micro tile scaled up reads as scattered stones
vec4 tM3 = texture(uMicro, (mat2(0.8, 0.6, -0.6, 0.8) * tp) / (MICRO_TILE * 7.0) + 0.71);
float tRf = smoothstep(14.0, 40.0, tDist) * (1.0 - smoothstep(350.0, 900.0, tDist));
tGrad += (tM3.xy - 0.5) * 1.6 * tRf;
// regolith mottling at metre scale (albedo only)
float tMott = texture(uMicro, (mat2(0.6, -0.8, 0.8, 0.6) * tp) / (MICRO_TILE * 9.0)).z - 0.5
            + (texture(uMicro, tp / (MICRO_TILE * 31.0) + 0.13).z - 0.5) * 0.8;

// rover tracks
float tRut = 0.0;
if (uTrackStrength > 0.0 && tDist < 90.0) {
  vec3 ts = trackSample(tp);
  if (ts.z > 0.0) {
    float e = uTrackWin.w;
    float hx1 = dot(trackSample(tp + vec2(e, 0.0)).xy, vec2(1.0, 0.45));
    float hx0 = dot(trackSample(tp - vec2(e, 0.0)).xy, vec2(1.0, 0.45));
    float hz1 = dot(trackSample(tp + vec2(0.0, e)).xy, vec2(1.0, 0.45));
    float hz0 = dot(trackSample(tp - vec2(0.0, e)).xy, vec2(1.0, 0.45));
    vec2 tg = -vec2(hx1 - hx0, hz1 - hz0) / (2.0 * e) * 0.028 * ts.z * uTrackStrength;
    tGrad += tg;
    tRut = ts.x * ts.z * uTrackStrength;
  }
}

vec3 tN = normalize(vec3(-tGrad.x, 1.0, -tGrad.y));
float tSlope = 1.0 - tN.y;
float tEj = max(tMi.z, max(tDa.w, tDb.w) * 0.7) * tBw;
float tAlb = uAlbedo * (1.0 + tMi.w * 0.16);
tAlb *= 1.0 + tEj * 0.45;
tAlb *= 1.0 + ((tM1.z - 0.5) * 0.3 + (tM2.z - 0.5) * 0.18) * tMf + tMott * 0.22 + (tM3.z - 0.5) * 0.3 * tRf;
tAlb *= 1.0 + smoothstep(0.08, 0.45, tSlope) * 0.25;
tAlb *= 1.0 - tRut * 0.22;
diffuseColor.rgb = vec3(tAlb) * uAlbedoTint;
`;

const TERRAIN_FRAGMENT_NORMAL = /* glsl */ `
normal = normalize((viewMatrix * vec4(tN, 0.0)).xyz);
`;

export class TerrainMesh {
  constructor(data, sharedUniforms, { segments = 64, casterSegments = 32, lodK = 1.6 } = {}) {
    this.data = data;
    this.lodK = lodK;
    this.minSize = 16;
    this.rootSize = FAR_SIZE;
    this.group = new THREE.Group();

    const blank = new THREE.DataTexture(new Uint8Array(4), 1, 1);
    blank.needsUpdate = true;
    this.uniforms = {
      ...data.uniforms(),
      uTracks: { value: blank },
      uTrackWin: { value: new THREE.Vector4(0, 0, 128, 0.0625) },
      uTrackStrength: { value: 0 },
      ...sharedUniforms,
      uCamPos: { value: new THREE.Vector3() },
      uHeightOffset: { value: 0 },
      uAlbedoTint: { value: new THREE.Color(1.0, 0.955, 0.9) },
      uAlbedo: { value: 0.2 },
    };

    // --- visible terrain -------------------------------------------------
    this.geometry = createGridGeometry(segments);
    this.nodeAttr = makeNodeAttribute(2048);
    this.geometry.setAttribute('aNode', this.nodeAttr);
    this.geometry.instanceCount = 0;

    this.material = new THREE.MeshStandardMaterial({ roughness: 0.96, metalness: 0 });
    this.material.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, this.uniforms);
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\n' + TERRAIN_VERTEX_PARS(data))
        .replace('#include <beginnormal_vertex>', /* glsl */ `
          vec2 tWpN = aNode.xy + position.xz * aNode.z;
          vec4 tMiV = macroInfoLod(tWpN);
          vec3 objectNormal = normalize(vec3(-tMiV.x, 1.0, -tMiV.y));`)
        .replace('#include <begin_vertex>', TERRAIN_VERTEX_BEGIN);
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', '#include <common>\n' + terrainSamplingGLSL(data.macroRes, data.farRes) + TERRAIN_FRAGMENT_PARS)
        .replace('#include <map_fragment>', TERRAIN_FRAGMENT_MAP)
        .replace('#include <roughnessmap_fragment>', 'float roughnessFactor = 0.97;')
        .replace('#include <normal_fragment_maps>', TERRAIN_FRAGMENT_NORMAL);
      applyLunarShading(shader, { brdf: true, worldPosExpr: 'vTerrainPos' });
    };
    this.material.customProgramCacheKey = () => 'lunar-terrain';

    this.mesh = new THREE.Mesh(this.geometry, this.material);
    this.mesh.frustumCulled = false;
    this.mesh.receiveShadow = true;
    this.mesh.castShadow = false;
    this.mesh.name = 'terrain';
    this.group.add(this.mesh);

    // --- shadow casters (coarser, only around the camera) ----------------
    this.casterGeometry = createGridGeometry(casterSegments);
    this.casterAttr = makeNodeAttribute(1024);
    this.casterGeometry.setAttribute('aNode', this.casterAttr);
    this.casterGeometry.instanceCount = 0;
    this.casterCount = 0;
    const casterUniforms = { ...this.uniforms, uHeightOffset: { value: -0.12 } };
    const depthMat = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking });
    depthMat.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, casterUniforms);
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\n' + TERRAIN_VERTEX_PARS(data))
        .replace('#include <begin_vertex>', TERRAIN_VERTEX_BEGIN);
    };
    depthMat.customProgramCacheKey = () => 'lunar-terrain-depth';
    // The caster mesh is invisible in the main pass (0 instances) and only
    // draws its instances while the shadow map renders.
    const hidden = new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: false });
    this.caster = new THREE.Mesh(this.casterGeometry, hidden);
    this.caster.customDepthMaterial = depthMat;
    this.caster.castShadow = true;
    this.caster.receiveShadow = false;
    this.caster.frustumCulled = false;
    this.caster.name = 'terrain-caster';
    this.caster.onBeforeRender = () => { this.casterGeometry.instanceCount = 0; };
    this.caster.onBeforeShadow = () => { this.casterGeometry.instanceCount = this.casterCount; };
    this.group.add(this.caster);

    this._frustum = new THREE.Frustum();
    this._m = new THREE.Matrix4();
    this._box = new THREE.Box3();
    this._range = { min: 0, max: 0 };
    this.stats = { nodes: 0, casters: 0 };
  }

  _grow(attr, geometry, name, needed) {
    if (needed <= attr.count) return attr;
    const next = makeNodeAttribute(Math.ceil(needed * 1.5));
    geometry.setAttribute(name, next);
    return next;
  }

  update(camera) {
    const cam = camera.position;
    this.uniforms.uCamPos.value.copy(cam);
    this._m.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    this._frustum.setFromProjectionMatrix(this._m);

    const visible = [];
    const casters = [];
    const half = this.rootSize / 2;
    const castRange = CSM_FAR + 140;
    this._select(-half, -half, this.rootSize, cam, visible, true, false);
    this._select(-half, -half, this.rootSize, cam, casters, false, true, castRange);

    this.nodeAttr = this._grow(this.nodeAttr, this.geometry, 'aNode', visible.length / 4);
    this.nodeAttr.array.set(visible);
    this.nodeAttr.clearUpdateRanges();
    this.nodeAttr.addUpdateRange(0, visible.length);
    this.nodeAttr.needsUpdate = true;
    this.geometry.instanceCount = visible.length / 4;

    this.casterAttr = this._grow(this.casterAttr, this.casterGeometry, 'aNode', casters.length / 4);
    this.casterAttr.array.set(casters);
    this.casterAttr.clearUpdateRanges();
    this.casterAttr.addUpdateRange(0, casters.length);
    this.casterAttr.needsUpdate = true;
    this.casterCount = casters.length / 4;

    this.stats.nodes = visible.length / 4;
    this.stats.casters = this.casterCount;
  }

  _select(x0, z0, size, cam, out, cull, casterMode, castRange = 0) {
    const r = this.data.heightRange(x0, z0, x0 + size, z0 + size, this._range);
    // curvature drop for distant nodes
    const dx = Math.max(x0 - cam.x, 0, cam.x - (x0 + size));
    const dz = Math.max(z0 - cam.z, 0, cam.z - (z0 + size));
    const d2 = dx * dx + dz * dz;
    const farDx = Math.max(Math.abs(x0 - cam.x), Math.abs(x0 + size - cam.x));
    const farDz = Math.max(Math.abs(z0 - cam.z), Math.abs(z0 + size - cam.z));
    const drop = (farDx * farDx + farDz * farDz) * (0.5 / MOON_RADIUS);
    const ymin = r.min - drop, ymax = r.max;

    if (casterMode) {
      if (Math.sqrt(d2) > castRange) return;
    } else if (cull) {
      this._box.min.set(x0, ymin, z0);
      this._box.max.set(x0 + size, ymax, z0 + size);
      if (!this._frustum.intersectsBox(this._box)) return;
    }

    const dy = Math.max(ymin - cam.y, 0, cam.y - ymax);
    const dist = Math.sqrt(d2 + dy * dy);
    const k = casterMode ? this.lodK * 0.55 : this.lodK;
    const minSize = casterMode ? this.minSize * 2 : this.minSize;
    if (size > minSize && dist < size * k) {
      const h = size / 2;
      this._select(x0, z0, h, cam, out, cull, casterMode, castRange);
      this._select(x0 + h, z0, h, cam, out, cull, casterMode, castRange);
      this._select(x0, z0 + h, h, cam, out, cull, casterMode, castRange);
      this._select(x0 + h, z0 + h, h, cam, out, cull, casterMode, castRange);
    } else {
      out.push(x0, z0, size, 0);
    }
  }
}
