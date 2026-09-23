import * as THREE from 'three';
import { buildRockLibrary, mulberry32 } from './RockGeometry.js';
import { applyLunarShading } from '../render/lunarShading.js';
import { MACRO_SIZE } from '../terrain/constants.js';

// Size classes of the rock population (diameters in metres, densities per m²).
const CLASSES = [
  { name: 'boulder', cell: 64, min: 0.4, max: 3.2, alpha: 2.2, bg: 0.02, ej: 0.1, vis: 280, physics: true },
  { name: 'cobble', cell: 16, min: 0.11, max: 0.4, alpha: 1.9, bg: 0.62, ej: 1.6, vis: 250, physics: true },
  { name: 'pebble', cell: 8, min: 0.035, max: 0.11, alpha: 1.7, bg: 3.0, ej: 6.0, vis: 260, physics: false },
];

const LOD_SCREEN = [0.05, 0.016, 0.006]; // size/distance thresholds for LOD0..LOD2

function hashCell(ix, iz, salt) {
  let h = Math.imul(ix, 0x8da6b343) ^ Math.imul(iz, 0xd8163841) ^ Math.imul(salt + 1, 0x9e3779b1);
  h = Math.imul(h ^ (h >>> 16), 0x7feb352d);
  h = Math.imul(h ^ (h >>> 15), 0x846ca68b);
  return (h ^ (h >>> 16)) >>> 0;
}

const ROCK_VERTEX_PARS = /* glsl */ `
varying vec3 vRockWP;
varying vec3 vRockObj;
varying vec3 vRockN;
`;
const ROCK_VERTEX = /* glsl */ `
#include <worldpos_vertex>
{
  mat4 im = mat4(1.0);
  #ifdef USE_INSTANCING
    im = instanceMatrix;
  #endif
  vec4 rwp = modelMatrix * im * vec4(transformed, 1.0);
  vRockWP = rwp.xyz;
  float sc = length(im[0].xyz);
  vRockObj = transformed * sc + im[3].xyz * 0.37;
  vRockN = normalize(mat3(modelMatrix) * mat3(im) * objectNormal);
}
`;
const ROCK_FRAGMENT_PARS = /* glsl */ `
varying vec3 vRockWP;
varying vec3 vRockObj;
varying vec3 vRockN;
uniform sampler2D uMicro;
uniform vec3 uRegolith;
vec4 triMicro(vec3 p, vec3 n, float scale) {
  vec3 w = pow(abs(n), vec3(4.0));
  w /= (w.x + w.y + w.z);
  vec4 x = texture(uMicro, p.zy * scale);
  vec4 y = texture(uMicro, p.xz * scale + 0.5);
  vec4 z = texture(uMicro, p.xy * scale + 0.25);
  // gradient (xy, remapped) and albedo (z)
  vec3 g = vec3(0.0);
  vec2 gx = (x.xy - 0.5) * 2.0, gy = (y.xy - 0.5) * 2.0, gz = (z.xy - 0.5) * 2.0;
  g += w.x * vec3(0.0, gx.y, gx.x);
  g += w.y * vec3(gy.x, 0.0, gy.y);
  g += w.z * vec3(gz.x, gz.y, 0.0);
  float a = w.x * x.z + w.y * y.z + w.z * z.z;
  return vec4(g, a);
}
`;
const ROCK_FRAGMENT_MAP = /* glsl */ `
#include <color_fragment>
vec3 rN = normalize(vRockN);
vec4 rm1 = triMicro(vRockObj, rN, 2.3);
vec4 rm2 = triMicro(vRockObj * 1.0, rN, 0.55);
float rDust = smoothstep(0.35, 0.95, rN.y + (rm2.w - 0.5) * 0.6);
vec3 rockAlb = diffuseColor.rgb * (0.82 + (rm1.w - 0.5) * 0.5 + (rm2.w - 0.5) * 0.3);
diffuseColor.rgb = mix(rockAlb, uRegolith * (0.95 + (rm1.w - 0.5) * 0.3), rDust * 0.75);
`;
const ROCK_FRAGMENT_NORMAL = /* glsl */ `
#include <normal_fragment_maps>
{
  vec3 gW = rm1.xyz * 0.55 + rm2.xyz * 0.35;
  vec3 nW = normalize(rN - gW + rN * dot(gW, rN));
  normal = normalize((viewMatrix * vec4(nW, 0.0)).xyz);
}
`;

export class RockField {
  constructor(data, microTex, { variants = 8, quality = 1 } = {}) {
    this.data = data;
    this.quality = quality;
    this.library = buildRockLibrary(variants, quality >= 1 ? [14, 6, 3, 1] : [8, 4, 2, 1]);
    this.group = new THREE.Group();
    this.group.name = 'rocks';
    this.cells = CLASSES.map(() => new Map());
    this.regolith = new THREE.Color(0.2, 0.19, 0.178);

    this.material = new THREE.MeshStandardMaterial({ roughness: 0.93, metalness: 0 });
    this.material.onBeforeCompile = (shader) => {
      shader.uniforms.uMicro = { value: microTex };
      shader.uniforms.uRegolith = { value: this.regolith };
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\n' + ROCK_VERTEX_PARS)
        .replace('#include <worldpos_vertex>', ROCK_VERTEX);
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', '#include <common>\n' + ROCK_FRAGMENT_PARS)
        .replace('#include <color_fragment>', ROCK_FRAGMENT_MAP)
        .replace('#include <normal_fragment_maps>', ROCK_FRAGMENT_NORMAL);
      applyLunarShading(shader, { brdf: true, worldPosExpr: 'vRockWP' });
    };
    this.material.customProgramCacheKey = () => 'lunar-rock';

    // one InstancedMesh per variant × LOD
    this.meshes = [];
    const caps = [900, 2600, 7000, 14000];
    for (let v = 0; v < this.library.length; v++) {
      this.meshes[v] = [];
      for (let l = 0; l < 4; l++) {
        const m = new THREE.InstancedMesh(this.library[v].geos[l], this.material, caps[l]);
        m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
        m.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(caps[l] * 3), 3);
        m.instanceColor.setUsage(THREE.DynamicDrawUsage);
        m.count = 0;
        m.castShadow = true;
        m.receiveShadow = true;
        m.frustumCulled = false;
        this.group.add(m);
        this.meshes[v][l] = m;
      }
    }

    this._frustum = new THREE.Frustum();
    this._pm = new THREE.Matrix4();
    this._m = new THREE.Matrix4();
    this._q = new THREE.Quaternion();
    this._euler = new THREE.Euler();
    this._s = new THREE.Vector3();
    this._p = new THREE.Vector3();
    this._c = new THREE.Color();
    this._sphere = new THREE.Sphere();
    this._lastCam = new THREE.Vector3(1e9, 0, 0);
    this._lastDir = new THREE.Vector3();
    this._dir = new THREE.Vector3();
    this.visibleCount = 0;
    this.densityScale = 1;

    // local physics index
    this._phys = { cx: 1e9, cz: 1e9, size: 48, cell: 2, grid: null, bigs: [] };
  }

  /** Deterministically generate the rocks of one cell of a class. */
  _cell(ci, ix, iz) {
    const map = this.cells[ci];
    const key = ix + ',' + iz;
    let c = map.get(key);
    if (c) return c;
    const cls = CLASSES[ci];
    const rnd = mulberry32(hashCell(ix, iz, ci));
    const x0 = ix * cls.cell, z0 = iz * cls.cell;
    const area = cls.cell * cls.cell;
    const data = this.data;
    const rocks = [];
    const limit = MACRO_SIZE / 2 - 240;
    if (Math.abs(x0) < limit && Math.abs(z0) < limit) {
      const maxDensity = (cls.bg + cls.ej) * this.densityScale;
      const perSample = ci === 0; // boulders: sample rockiness per candidate
      const rCell = perSample ? 0 : data.rockiness(x0 + cls.cell / 2, z0 + cls.cell / 2);
      const cellDensity = (cls.bg + cls.ej * rCell * rCell) * this.densityScale;
      const n = Math.round((perSample ? maxDensity : cellDensity) * area * (0.7 + rnd() * 0.6));
      for (let i = 0; i < n; i++) {
        const x = x0 + rnd() * cls.cell, z = z0 + rnd() * cls.cell;
        const u = rnd();
        if (perSample) {
          const r = data.rockiness(x, z);
          if (u * maxDensity > cls.bg * this.densityScale + cls.ej * r * r * this.densityScale) continue;
        }
        // truncated power-law size distribution
        const a = cls.alpha, lo = Math.pow(cls.min, -a), hi = Math.pow(cls.max, -a);
        const d = Math.pow(lo + (hi - lo) * rnd(), -1 / a);
        const variant = Math.floor(rnd() * this.library.length);
        const lib = this.library[variant];
        const s = d / (2 * Math.max(lib.halfX, lib.halfZ));
        const yaw = rnd() * Math.PI * 2;
        const tiltX = (rnd() - 0.5) * 0.35, tiltZ = (rnd() - 0.5) * 0.35;
        const bury = 0.12 + rnd() * 0.35;
        // settle on the lowest point of the footprint
        const r0 = d * 0.35;
        let h = data.heightAt(x, z);
        if (d > 0.25) {
          h = Math.min(h, data.heightAt(x + r0, z), data.heightAt(x - r0, z), data.heightAt(x, z + r0), data.heightAt(x, z - r0));
        }
        const height = (lib.top - lib.bottom) * s;
        const y = h - lib.bottom * s - bury * height;
        const tone = 0.62 + rnd() * 0.5;
        const warm = rnd() * 0.06;
        this._q.setFromEuler(this._euler.set(tiltX, yaw, tiltZ));
        this._s.setScalar(s);
        this._p.set(x, y, z);
        const m = new Float32Array(16);
        this._m.compose(this._p, this._q, this._s).toArray(m);
        rocks.push({
          x, y, z, d, variant, m,
          top: y + lib.top * s,
          rad: Math.max(lib.halfX, lib.halfZ) * s * 0.85,
          color: [tone * (0.25 + warm * 0.7), tone * 0.238, tone * (0.222 - warm * 0.35)],
        });
      }
    }
    c = { rocks };
    map.set(key, c);
    if (map.size > 4000) {
      // simple eviction of the oldest entries
      let k = 0;
      for (const oldKey of map.keys()) {
        map.delete(oldKey);
        if (++k > 800) break;
      }
    }
    return c;
  }

  update(camera, force = false) {
    const cam = camera.position;
    camera.getWorldDirection(this._dir);
    if (!force && cam.distanceToSquared(this._lastCam) < 2.2 * 2.2 && this._dir.dot(this._lastDir) > 0.996) return;
    this._lastCam.copy(cam);
    this._lastDir.copy(this._dir);
    this._pm.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    this._frustum.setFromProjectionMatrix(this._pm);

    const counts = this.meshes.map((l) => l.map(() => 0));
    const q = this.quality;
    let total = 0;
    for (let ci = 0; ci < CLASSES.length; ci++) {
      const cls = CLASSES[ci];
      const range = cls.max * cls.vis * q;
      const i0 = Math.floor((cam.x - range) / cls.cell), i1 = Math.floor((cam.x + range) / cls.cell);
      const j0 = Math.floor((cam.z - range) / cls.cell), j1 = Math.floor((cam.z + range) / cls.cell);
      for (let j = j0; j <= j1; j++) {
        for (let i = i0; i <= i1; i++) {
          // cull whole cells
          const cx = (i + 0.5) * cls.cell, cz = (j + 0.5) * cls.cell;
          const dx = cx - cam.x, dz = cz - cam.z;
          const cd = Math.sqrt(dx * dx + dz * dz) - cls.cell * 0.71;
          if (cd > range) continue;
          // whole-cell frustum test (with a margin for shadows)
          const gy = this.data.heightAt(cx, cz);
          this._sphere.center.set(cx, gy, cz);
          this._sphere.radius = cls.cell * 0.75 + 12;
          if (!this._frustum.intersectsSphere(this._sphere)) continue;
          const cell = this._cell(ci, i, j);
          const visK = cls.vis * q;
          for (const r of cell.rocks) {
            const rx = r.x - cam.x, ry = r.y - cam.y, rz = r.z - cam.z;
            const d2 = rx * rx + ry * ry + rz * rz;
            const lim = r.d * visK;
            if (d2 > lim * lim) continue;
            const dist = Math.sqrt(d2);
            this._sphere.center.set(r.x, r.y, r.z);
            this._sphere.radius = r.d * (dist < 60 ? 6 : 1);
            if (!this._frustum.intersectsSphere(this._sphere)) continue;
            const ratio = r.d / Math.max(dist, 0.1);
            const lod = ratio > LOD_SCREEN[0] ? 0 : ratio > LOD_SCREEN[1] ? 1 : ratio > LOD_SCREEN[2] ? 2 : 3;
            const mesh = this.meshes[r.variant][lod];
            const idx = counts[r.variant][lod];
            if (idx >= mesh.instanceMatrix.count) continue;
            mesh.instanceMatrix.array.set(r.m, idx * 16);
            const ca = mesh.instanceColor.array;
            ca[idx * 3] = r.color[0]; ca[idx * 3 + 1] = r.color[1]; ca[idx * 3 + 2] = r.color[2];
            counts[r.variant][lod] = idx + 1;
            total++;
          }
        }
      }
    }
    for (let v = 0; v < this.meshes.length; v++) {
      for (let l = 0; l < 4; l++) {
        const m = this.meshes[v][l];
        m.count = counts[v][l];
        m.instanceMatrix.clearUpdateRanges();
        m.instanceMatrix.addUpdateRange(0, m.count * 16);
        m.instanceMatrix.needsUpdate = true;
        m.instanceColor.clearUpdateRanges();
        m.instanceColor.addUpdateRange(0, m.count * 3);
        m.instanceColor.needsUpdate = true;
      }
    }
    this.visibleCount = total;
  }

  // ---- physics -----------------------------------------------------------

  _buildPhysics(x, z) {
    const P = this._phys;
    P.cx = Math.round(x / 8) * 8;
    P.cz = Math.round(z / 8) * 8;
    const n = P.size / P.cell;
    P.grid = Array.from({ length: n * n }, () => []);
    P.bigs = [];
    const x0 = P.cx - P.size / 2, z0 = P.cz - P.size / 2;
    for (let ci = 0; ci < CLASSES.length; ci++) {
      if (!CLASSES[ci].physics) continue;
      const cs = CLASSES[ci].cell;
      for (let j = Math.floor((z0 - 4) / cs); j <= Math.floor((z0 + P.size + 4) / cs); j++) {
        for (let i = Math.floor((x0 - 4) / cs); i <= Math.floor((x0 + P.size + 4) / cs); i++) {
          for (const r of this._cell(ci, i, j).rocks) {
            const ground = this.data.heightAt(r.x, r.z);
            const h = r.top - ground;
            if (h < 0.05) continue;
            const rr = r.rad;
            const gx0 = Math.max(0, Math.floor((r.x - rr - x0) / P.cell)), gx1 = Math.min(n - 1, Math.floor((r.x + rr - x0) / P.cell));
            const gz0 = Math.max(0, Math.floor((r.z - rr - z0) / P.cell)), gz1 = Math.min(n - 1, Math.floor((r.z + rr - z0) / P.cell));
            const entry = { x: r.x, z: r.z, rad: rr, top: r.top, h };
            for (let gz = gz0; gz <= gz1; gz++) for (let gx = gx0; gx <= gx1; gx++) P.grid[gz * n + gx].push(entry);
            if (h > 0.5) P.bigs.push(entry);
          }
        }
      }
    }
  }

  _ensurePhysics(x, z) {
    const P = this._phys;
    if (Math.abs(x - P.cx) > P.size / 2 - 10 || Math.abs(z - P.cz) > P.size / 2 - 10) this._buildPhysics(x, z);
  }

  /** Terrain height including rock tops (what a wheel rests on). */
  surfaceAt(x, z, base) {
    const P = this._phys;
    if (!P.grid) return base;
    const n = P.size / P.cell;
    const gx = Math.floor((x - (P.cx - P.size / 2)) / P.cell), gz = Math.floor((z - (P.cz - P.size / 2)) / P.cell);
    if (gx < 0 || gz < 0 || gx >= n || gz >= n) return base;
    let h = base;
    for (const r of P.grid[gz * n + gx]) {
      const dx = x - r.x, dz = z - r.z;
      const q = (dx * dx + dz * dz) / (r.rad * r.rad);
      if (q >= 1) continue;
      const top = r.top - r.h + r.h * Math.sqrt(1 - q);
      if (top > h) h = top;
    }
    return h;
  }

  /** Push-out vector if the rover footprint overlaps a large boulder. */
  collide(x, z, yaw) {
    this._ensurePhysics(x, z);
    const c = Math.cos(yaw), s = Math.sin(yaw);
    const hx = 1.25, hz = 1.55;
    for (const r of this._phys.bigs) {
      const dx = r.x - x, dz = r.z - z;
      if (dx * dx + dz * dz > 16) continue;
      // into rover frame (x lateral left, z forward)
      const lx = dx * c - dz * s, lz = dx * s + dz * c;
      const px = Math.max(-hx, Math.min(hx, lx)), pz = Math.max(-hz, Math.min(hz, lz));
      const ex = lx - px, ez = lz - pz;
      const d = Math.hypot(ex, ez);
      const rad = r.rad * 0.8;
      if (d < rad) {
        const pen = rad - d + 0.01;
        let nx = d > 1e-4 ? -ex / d : -Math.sign(lx) || -1, nz = d > 1e-4 ? -ez / d : 0;
        // back to world
        return { x: (nx * c + nz * s) * pen, z: (-nx * s + nz * c) * pen };
      }
    }
    return null;
  }
}
