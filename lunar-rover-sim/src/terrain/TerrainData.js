import * as THREE from 'three';
import { GLSL_NOISE, GLSL_CRATERS, GLSL_MACRO, GLSL_DETAIL, GLSL_MICRO } from './glsl.js';
import {
  MACRO_MIN, MACRO_SIZE, FAR_MIN, FAR_SIZE, BLEND_START, BLEND_END,
  DETAIL_TILE, DETAIL_B_SCALE, DETAIL_B_AMP, DETAIL_B_ROT, DETAIL_B_OFFSET, MICRO_TILE,
} from './constants.js';

const FS_VERT = /* glsl */ `
in vec3 position;
void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }
`;

const BAKE_HEADER = /* glsl */ `
precision highp float;
precision highp int;
uniform vec4 uRegion; // x0, z0, texel size, unused
out vec4 outColor;
`;

let _tri = null;
function fullscreenTriangle() {
  if (_tri) return _tri;
  _tri = new THREE.BufferGeometry();
  _tri.setAttribute('position', new THREE.Float32BufferAttribute([-1, -1, 0, 3, -1, 0, -1, 3, 0], 3));
  return _tri;
}

const _cam = new THREE.Camera();

/** Render a fullscreen fragment program into a target, in tiles to keep each draw short. */
export function runFullscreen(renderer, material, target, tile = 512) {
  const mesh = new THREE.Mesh(fullscreenTriangle(), material);
  mesh.frustumCulled = false;
  const prevTarget = renderer.getRenderTarget();
  const prevAutoClear = renderer.autoClear;
  renderer.autoClear = false;
  renderer.setRenderTarget(target);
  const w = target.width, h = target.height;
  for (let y = 0; y < h; y += tile) {
    for (let x = 0; x < w; x += tile) {
      target.viewport.set(0, 0, w, h);
      target.scissor.set(x, y, Math.min(tile, w - x), Math.min(tile, h - y));
      target.scissorTest = true;
      renderer.setRenderTarget(target);
      renderer.render(mesh, _cam);
    }
  }
  target.scissorTest = false;
  renderer.setRenderTarget(prevTarget);
  renderer.autoClear = prevAutoClear;
}

function bakeMaterial(body, uniforms = {}) {
  return new THREE.RawShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: FS_VERT,
    fragmentShader: BAKE_HEADER + GLSL_NOISE + GLSL_CRATERS + body,
    uniforms,
    depthTest: false,
    depthWrite: false,
  });
}

function floatTarget(size) {
  return new THREE.WebGLRenderTarget(size, size, {
    type: THREE.FloatType,
    format: THREE.RGBAFormat,
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    depthBuffer: false,
    generateMipmaps: false,
  });
}

function readFloat(renderer, rt) {
  const out = new Float32Array(rt.width * rt.height * 4);
  renderer.readRenderTargetPixels(rt, 0, 0, rt.width, rt.height, out);
  return out;
}

function channel(src, c, n) {
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) out[i] = src[i * 4 + c];
  return out;
}

function halfTexture(data, size, wrap, mipmaps = true) {
  const tex = new THREE.DataTexture(data, size, size, THREE.RGBAFormat, THREE.HalfFloatType);
  tex.wrapS = tex.wrapT = wrap;
  tex.magFilter = THREE.LinearFilter;
  tex.minFilter = mipmaps ? THREE.LinearMipmapLinearFilter : THREE.LinearFilter;
  tex.generateMipmaps = mipmaps;
  tex.anisotropy = 8;
  tex.colorSpace = THREE.NoColorSpace;
  tex.needsUpdate = true;
  return tex;
}

function heightTexture(data, size) {
  const tex = new THREE.DataTexture(data, size, size, THREE.RedFormat, THREE.FloatType);
  tex.magFilter = tex.minFilter = THREE.NearestFilter;
  tex.generateMipmaps = false;
  tex.colorSpace = THREE.NoColorSpace;
  tex.needsUpdate = true;
  return tex;
}

const toHalf = THREE.DataUtils.toHalfFloat;

function catmullWeights(t, out) {
  out[0] = t * (-0.5 + t * (1 - 0.5 * t));
  out[1] = 1 + t * t * (-2.5 + 1.5 * t);
  out[2] = t * (0.5 + t * (2 - 1.5 * t));
  out[3] = t * t * (-0.5 + 0.5 * t);
}
const _wx = new Float64Array(4), _wy = new Float64Array(4);

function catmullRom(data, res, tx, ty) {
  const sx = tx - 0.5, sy = ty - 0.5;
  const ix = Math.floor(sx), iy = Math.floor(sy);
  catmullWeights(sx - ix, _wx);
  catmullWeights(sy - iy, _wy);
  let r = 0;
  for (let y = 0; y < 4; y++) {
    const yy = Math.min(res - 1, Math.max(0, iy - 1 + y)) * res;
    let row = 0;
    for (let x = 0; x < 4; x++) {
      const xx = Math.min(res - 1, Math.max(0, ix - 1 + x));
      row += _wx[x] * data[yy + xx];
    }
    r += _wy[y] * row;
  }
  return r;
}

function bilinearWrap(data, res, tx, ty, stride = 1, offset = 0) {
  const sx = tx - 0.5, sy = ty - 0.5;
  const ix = Math.floor(sx), iy = Math.floor(sy);
  const fx = sx - ix, fy = sy - iy;
  const x0 = ((ix % res) + res) % res, y0 = ((iy % res) + res) % res;
  const x1 = (x0 + 1) % res, y1 = (y0 + 1) % res;
  const a = data[(y0 * res + x0) * stride + offset], b = data[(y0 * res + x1) * stride + offset];
  const c = data[(y1 * res + x0) * stride + offset], d = data[(y1 * res + x1) * stride + offset];
  return (a + (b - a) * fx) * (1 - fy) + (c + (d - c) * fx) * fy;
}

function bilinearClamp(data, res, tx, ty, stride = 1, offset = 0) {
  const sx = Math.min(res - 1, Math.max(0, tx - 0.5)), sy = Math.min(res - 1, Math.max(0, ty - 0.5));
  const ix = Math.min(res - 2, Math.floor(sx)), iy = Math.min(res - 2, Math.floor(sy));
  const fx = sx - ix, fy = sy - iy;
  const a = data[(iy * res + ix) * stride + offset], b = data[(iy * res + ix + 1) * stride + offset];
  const c = data[((iy + 1) * res + ix) * stride + offset], d = data[((iy + 1) * res + ix + 1) * stride + offset];
  return (a + (b - a) * fx) * (1 - fy) + (c + (d - c) * fx) * fy;
}

const smoothstep = (a, b, x) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

/**
 * Generates the lunar terrain on the GPU and keeps CPU copies for physics,
 * rock placement and culling.
 */
export class TerrainData {
  constructor(renderer, { macroRes = 2048, farRes = 1024, detailRes = 1024, microRes = 512 } = {}) {
    this.renderer = renderer;
    this.macroRes = macroRes;
    this.farRes = farRes;
    this.detailRes = detailRes;
    this.microRes = microRes;
    this.macroTexel = MACRO_SIZE / macroRes;
    this.farTexel = FAR_SIZE / farRes;
    const c = Math.cos(DETAIL_B_ROT), s = Math.sin(DETAIL_B_ROT);
    this._rot = { c, s };
  }

  /** Runs all bakes. onProgress(fraction, label) lets the loader update. */
  async generate(onProgress = () => {}) {
    const r = this.renderer;
    const step = async (frac, label) => {
      onProgress(frac, label);
      await new Promise((res) => setTimeout(res, 0));
    };

    await step(0.02, 'Макрорельеф: кратеры и холмы');
    const macroMat = bakeMaterial(GLSL_MACRO + /* glsl */ `
      void main() {
        vec2 p = uRegion.xy + gl_FragCoord.xy * uRegion.z;
        vec3 extra;
        float h = macroHeight(p, uRegion.w, extra);
        outColor = vec4(h, extra);
      }`, { uRegion: { value: new THREE.Vector4(MACRO_MIN, MACRO_MIN, this.macroTexel, 40) } });
    const macroRT = floatTarget(this.macroRes);
    runFullscreen(r, macroMat, macroRT, 256);
    const macroRaw = readFloat(r, macroRT);
    macroRT.dispose(); macroMat.dispose();

    await step(0.25, 'Дальние массивы');
    const farMat = bakeMaterial(GLSL_MACRO + /* glsl */ `
      void main() {
        vec2 p = uRegion.xy + gl_FragCoord.xy * uRegion.z;
        vec3 extra;
        float h = macroHeight(p, uRegion.w, extra);
        outColor = vec4(h, extra);
      }`, { uRegion: { value: new THREE.Vector4(FAR_MIN, FAR_MIN, this.farTexel, 170) } });
    const farRT = floatTarget(this.farRes);
    runFullscreen(r, farMat, farRT, 256);
    const farRaw = readFloat(r, farRT);
    farRT.dispose(); farMat.dispose();

    await step(0.4, 'Мелкие кратеры и реголит');
    const detailMat = bakeMaterial(GLSL_DETAIL + /* glsl */ `
      void main() {
        vec2 p = gl_FragCoord.xy * uRegion.z;
        vec2 extra;
        float h = detailHeight(p, extra);
        outColor = vec4(h, extra, 0.0);
      }`, { uRegion: { value: new THREE.Vector4(0, 0, DETAIL_TILE / this.detailRes, 0) } });
    const detailRT = floatTarget(this.detailRes);
    runFullscreen(r, detailMat, detailRT, 256);
    const detailRaw = readFloat(r, detailRT);
    detailRT.dispose(); detailMat.dispose();

    const microMat = bakeMaterial(GLSL_MICRO + /* glsl */ `
      void main() {
        vec2 p = gl_FragCoord.xy * uRegion.z;
        float alb;
        float h = microHeight(p, alb);
        outColor = vec4(h, alb, 0.0, 0.0);
      }`, { uRegion: { value: new THREE.Vector4(0, 0, MICRO_TILE / this.microRes, 0) } });
    const microRT = floatTarget(this.microRes);
    runFullscreen(r, microMat, microRT, 256);
    const microRaw = readFloat(r, microRT);
    microRT.dispose(); microMat.dispose();

    await step(0.55, 'Подготовка текстур');
    this._buildMacro(macroRaw);
    this._buildFar(farRaw);
    this._buildDetail(detailRaw);
    this._buildMicro(microRaw);
    this._buildMinMax();
    await step(0.62, 'Готово');
  }

  _gradientField(h, res, texel, wrap) {
    const g = new Float32Array(res * res * 2);
    const inv = 1 / (2 * texel);
    for (let y = 0; y < res; y++) {
      for (let x = 0; x < res; x++) {
        let xm = x - 1, xp = x + 1, ym = y - 1, yp = y + 1;
        if (wrap) {
          xm = (xm + res) % res; xp %= res; ym = (ym + res) % res; yp %= res;
        } else {
          xm = Math.max(0, xm); xp = Math.min(res - 1, xp); ym = Math.max(0, ym); yp = Math.min(res - 1, yp);
        }
        const i = (y * res + x) * 2;
        const sx = wrap || (x > 0 && x < res - 1) ? inv : inv * 2;
        const sy = wrap || (y > 0 && y < res - 1) ? inv : inv * 2;
        g[i] = (h[y * res + xp] - h[y * res + xm]) * sx;
        g[i + 1] = (h[yp * res + x] - h[ym * res + x]) * sy;
      }
    }
    return g;
  }

  _infoTexture(raw, h, res, texel) {
    const g = this._gradientField(h, res, texel, false);
    const n = res * res;
    const info = new Uint16Array(n * 4);
    for (let i = 0; i < n; i++) {
      info[i * 4] = toHalf(g[i * 2]);
      info[i * 4 + 1] = toHalf(g[i * 2 + 1]);
      info[i * 4 + 2] = toHalf(raw[i * 4 + 1]); // ejecta (fresh crater surroundings)
      info[i * 4 + 3] = toHalf(raw[i * 4 + 2]); // albedo variation
    }
    return halfTexture(info, res, THREE.ClampToEdgeWrapping);
  }

  _buildMacro(raw) {
    const n = this.macroRes * this.macroRes;
    this.macroH = channel(raw, 0, n);
    this.macroEjecta = channel(raw, 1, n);
    this.macroHTex = heightTexture(this.macroH, this.macroRes);
    this.macroInfoTex = this._infoTexture(raw, this.macroH, this.macroRes, this.macroTexel);
  }

  _buildFar(raw) {
    const n = this.farRes * this.farRes;
    this.farH = channel(raw, 0, n);
    this.farHTex = heightTexture(this.farH, this.farRes);
    this.farInfoTex = this._infoTexture(raw, this.farH, this.farRes, this.farTexel);
  }

  _buildDetail(raw) {
    const res = this.detailRes;
    const n = res * res;
    this.detailH = channel(raw, 0, n);
    this.detailEjecta = channel(raw, 1, n);
    const g = this._gradientField(this.detailH, res, DETAIL_TILE / res, true);
    const d = new Uint16Array(n * 4);
    for (let i = 0; i < n; i++) {
      d[i * 4] = toHalf(this.detailH[i]);
      d[i * 4 + 1] = toHalf(g[i * 2]);
      d[i * 4 + 2] = toHalf(g[i * 2 + 1]);
      d[i * 4 + 3] = toHalf(raw[i * 4 + 1]);
    }
    this.detailTex = halfTexture(d, res, THREE.RepeatWrapping);
  }

  _buildMicro(raw) {
    const res = this.microRes;
    const n = res * res;
    const h = channel(raw, 0, n);
    const g = this._gradientField(h, res, MICRO_TILE / res, true);
    const d = new Uint8Array(n * 4);
    for (let i = 0; i < n; i++) {
      d[i * 4] = Math.max(0, Math.min(255, Math.round((g[i * 2] * 0.5 + 0.5) * 255)));
      d[i * 4 + 1] = Math.max(0, Math.min(255, Math.round((g[i * 2 + 1] * 0.5 + 0.5) * 255)));
      d[i * 4 + 2] = Math.max(0, Math.min(255, Math.round((raw[i * 4 + 1] * 0.5 + 0.5) * 255)));
      d[i * 4 + 3] = Math.max(0, Math.min(255, Math.round((h[i] / 0.01 * 0.5 + 0.5) * 255)));
    }
    const tex = new THREE.DataTexture(d, res, res, THREE.RGBAFormat, THREE.UnsignedByteType);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    tex.magFilter = THREE.LinearFilter;
    tex.minFilter = THREE.LinearMipmapLinearFilter;
    tex.generateMipmaps = true;
    tex.anisotropy = 8;
    tex.needsUpdate = true;
    this.microTex = tex;
  }

  // Min/max pyramids for quadtree node bounds.
  _buildMinMax() {
    const build = (h, res) => {
      const levels = [];
      let cur = { res, min: h, max: h };
      levels.push(cur);
      while (cur.res > 1) {
        const r2 = cur.res >> 1;
        const mn = new Float32Array(r2 * r2), mx = new Float32Array(r2 * r2);
        for (let y = 0; y < r2; y++) {
          for (let x = 0; x < r2; x++) {
            const i0 = (y * 2) * cur.res + x * 2;
            const i1 = i0 + 1, i2 = i0 + cur.res, i3 = i2 + 1;
            mn[y * r2 + x] = Math.min(cur.min[i0], cur.min[i1], cur.min[i2], cur.min[i3]);
            mx[y * r2 + x] = Math.max(cur.max[i0], cur.max[i1], cur.max[i2], cur.max[i3]);
          }
        }
        cur = { res: r2, min: mn, max: mx };
        levels.push(cur);
      }
      return levels;
    };
    this.macroPyr = build(this.macroH, this.macroRes);
    this.farPyr = build(this.farH, this.farRes);
  }

  _rangeFrom(pyr, gridMin, gridSize, x0, z0, x1, z1, out) {
    const res0 = pyr[0].res;
    const texel = gridSize / res0;
    const span = Math.max(x1 - x0, z1 - z0) / texel;
    let lvl = Math.max(0, Math.min(pyr.length - 1, Math.floor(Math.log2(Math.max(1, span / 2)))));
    const L = pyr[lvl];
    const t = gridSize / L.res;
    const ix0 = Math.max(0, Math.floor((x0 - gridMin) / t) - 1), ix1 = Math.min(L.res - 1, Math.floor((x1 - gridMin) / t) + 1);
    const iz0 = Math.max(0, Math.floor((z0 - gridMin) / t) - 1), iz1 = Math.min(L.res - 1, Math.floor((z1 - gridMin) / t) + 1);
    for (let z = iz0; z <= iz1; z++) {
      for (let x = ix0; x <= ix1; x++) {
        const i = z * L.res + x;
        if (L.min[i] < out.min) out.min = L.min[i];
        if (L.max[i] > out.max) out.max = L.max[i];
      }
    }
  }

  /** Conservative height range of a rectangular region. */
  heightRange(x0, z0, x1, z1, out = { min: Infinity, max: -Infinity }) {
    out.min = Infinity; out.max = -Infinity;
    const e = BLEND_END + 64;
    const insideMacro = x1 > -e && x0 < e && z1 > -e && z0 < e;
    this._rangeFrom(this.farPyr, FAR_MIN, FAR_SIZE, x0, z0, x1, z1, out);
    if (insideMacro) this._rangeFrom(this.macroPyr, MACRO_MIN, MACRO_SIZE, x0, z0, x1, z1, out);
    out.min -= 6; // detail relief margin
    out.max += 6;
    return out;
  }

  blendW(x, z) {
    return smoothstep(BLEND_START, BLEND_END, Math.max(Math.abs(x), Math.abs(z)));
  }

  baseHeight(x, z) {
    const w = this.blendW(x, z);
    const hf = catmullRom(this.farH, this.farRes, (x - FAR_MIN) / this.farTexel, (z - FAR_MIN) / this.farTexel);
    if (w >= 1) return hf;
    const hm = catmullRom(this.macroH, this.macroRes, (x - MACRO_MIN) / this.macroTexel, (z - MACRO_MIN) / this.macroTexel);
    return hm + (hf - hm) * w;
  }

  _detailUvB(x, z) {
    const { c, s } = this._rot;
    const px = x + DETAIL_B_OFFSET[0], pz = z + DETAIL_B_OFFSET[1];
    // GLSL mat2(c, s, -s, c) * p  => (c*px - s*pz, s*px + c*pz)
    const k = 1 / (DETAIL_TILE * DETAIL_B_SCALE);
    return [(c * px - s * pz) * k, (s * px + c * pz) * k];
  }

  detailHeight(x, z) {
    const res = this.detailRes;
    const ha = bilinearWrap(this.detailH, res, (x / DETAIL_TILE) * res, (z / DETAIL_TILE) * res);
    const [bu, bv] = this._detailUvB(x, z);
    const hb = bilinearWrap(this.detailH, res, bu * res, bv * res);
    return (ha + hb * DETAIL_B_SCALE * DETAIL_B_AMP) * (1 - this.blendW(x, z));
  }

  heightAt(x, z) {
    return this.baseHeight(x, z) + this.detailHeight(x, z);
  }

  normalAt(x, z, out = new THREE.Vector3(), e = 0.35) {
    const hx = this.heightAt(x + e, z) - this.heightAt(x - e, z);
    const hz = this.heightAt(x, z + e) - this.heightAt(x, z - e);
    return out.set(-hx, 2 * e, -hz).normalize();
  }

  /** Rock abundance 0..1 at a location (fresh ejecta + base scatter). */
  rockiness(x, z) {
    let ej = 0;
    if (Math.abs(x) < MACRO_SIZE / 2 && Math.abs(z) < MACRO_SIZE / 2) {
      ej = bilinearClamp(this.macroEjecta, this.macroRes, (x - MACRO_MIN) / this.macroTexel, (z - MACRO_MIN) / this.macroTexel);
    }
    const res = this.detailRes;
    const ea = bilinearWrap(this.detailEjecta, res, (x / DETAIL_TILE) * res, (z / DETAIL_TILE) * res);
    const [bu, bv] = this._detailUvB(x, z);
    const eb = bilinearWrap(this.detailEjecta, res, bu * res, bv * res);
    return Math.min(1, ej * 1.2 + Math.max(ea, eb) * 0.8);
  }

  uniforms() {
    return {
      uMacroH: { value: this.macroHTex },
      uFarH: { value: this.farHTex },
      uMacroInfo: { value: this.macroInfoTex },
      uFarInfo: { value: this.farInfoTex },
      uDetail: { value: this.detailTex },
      uMicro: { value: this.microTex },
    };
  }
}
