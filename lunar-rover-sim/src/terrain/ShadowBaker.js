import * as THREE from 'three';
import { runFullscreen } from './TerrainData.js';
import {
  MACRO_MIN, MACRO_SIZE, FAR_MIN, FAR_SIZE, BLEND_START, BLEND_END, MOON_RADIUS, BAKED_NEAR_SKIP,
} from './constants.js';

const f = (v) => (Number.isInteger(v) ? v.toFixed(1) : String(v));

/**
 * Bakes soft sun visibility (horizon shadows) by ray-marching the height maps
 * towards the sun. The penumbra width follows the real angular size of the
 * Sun (0.53°), so distant ridges cast wide soft edges and rocks sharp ones.
 *   R: visibility from all occluders
 *   G: visibility from occluders further than BAKED_NEAR_SKIP (near ones are
 *      handled by the cascaded shadow maps)
 */
export class ShadowBaker {
  constructor(renderer, data, { macroShadowRes = 1024, farShadowRes = 512 } = {}) {
    this.renderer = renderer;
    this.data = data;
    const opts = {
      type: THREE.UnsignedByteType,
      format: THREE.RGBAFormat,
      minFilter: THREE.LinearFilter,
      magFilter: THREE.LinearFilter,
      depthBuffer: false,
      generateMipmaps: false,
    };
    // double-buffered so the Sun can move while a new bake is in progress
    this.sets = [0, 1].map(() => ({
      macro: new THREE.WebGLRenderTarget(macroShadowRes, macroShadowRes, opts),
      far: new THREE.WebGLRenderTarget(farShadowRes, farShadowRes, opts),
    }));
    this.front = 0;
    this.job = null;
    this.onSwap = null;
    this._mesh = null;
    this._cam = new THREE.Camera();

    this.material = new THREE.RawShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: /* glsl */ `in vec3 position; void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }`,
      fragmentShader: /* glsl */ `
        precision highp float;
        precision highp int;
        uniform highp sampler2D uMacroH;
        uniform highp sampler2D uFarH;
        uniform vec3 uSunDir;
        uniform vec4 uRegion; // x0, z0, texel, skip
        out vec4 outColor;

        float bil(highp sampler2D t, vec2 pTex, int res) {
          vec2 st = pTex - 0.5;
          vec2 fi = floor(st);
          vec2 fr = st - fi;
          ivec2 b = ivec2(fi);
          ivec2 hi = ivec2(res - 1);
          float a = texelFetch(t, clamp(b, ivec2(0), hi), 0).r;
          float c = texelFetch(t, clamp(b + ivec2(1, 0), ivec2(0), hi), 0).r;
          float d = texelFetch(t, clamp(b + ivec2(0, 1), ivec2(0), hi), 0).r;
          float e = texelFetch(t, clamp(b + ivec2(1, 1), ivec2(0), hi), 0).r;
          return mix(mix(a, c, fr.x), mix(d, e, fr.x), fr.y);
        }
        float hAt(vec2 p) {
          float w = smoothstep(${f(BLEND_START)}, ${f(BLEND_END)}, max(abs(p.x), abs(p.y)));
          float hf = bil(uFarH, (p - ${f(FAR_MIN)}) / ${f(data.farTexel)}, ${data.farRes});
          if (w >= 1.0) return hf;
          float hm = bil(uMacroH, (p - ${f(MACRO_MIN)}) / ${f(data.macroTexel)}, ${data.macroRes});
          return mix(hm, hf, w);
        }
        void main() {
          vec2 p = uRegion.xy + gl_FragCoord.xy * uRegion.z;
          float horiz = max(length(uSunDir.xz), 1e-4);
          vec2 d = uSunDir.xz / horiz;
          float tanE = uSunDir.y / horiz;
          float h0 = hAt(p) + 0.4;
          float visAll = 1.0, visFar = 1.0;
          float t = uRegion.z * 0.75;
          float lim = ${f(FAR_SIZE / 2 - 64)};
          for (int i = 0; i < 240; i++) {
            vec2 q = p + d * t;
            if (abs(q.x) > lim || abs(q.y) > lim) break;
            float hs = hAt(q) - t * t * ${f(0.5 / MOON_RADIUS)};
            float hr = h0 + t * tanE;
            float k = (hr - hs) / (t * 0.0093) + 0.5;
            visAll = min(visAll, k);
            if (t > uRegion.w) visFar = min(visFar, k);
            if (hr > 4000.0 || visAll <= 0.0) break;
            t += max(uRegion.z * 0.75, t * 0.03);
          }
          if (visAll <= 0.0 && t <= uRegion.w) {
            // occluded by something near: keep marching for the far channel
            for (int i = 0; i < 200; i++) {
              if (t <= uRegion.w) { t += max(uRegion.z * 0.75, t * 0.03); continue; }
              vec2 q = p + d * t;
              if (abs(q.x) > lim || abs(q.y) > lim) break;
              float hs = hAt(q) - t * t * ${f(0.5 / MOON_RADIUS)};
              float hr = h0 + t * tanE;
              visFar = min(visFar, (hr - hs) / (t * 0.0093) + 0.5);
              if (hr > 4000.0 || visFar <= 0.0) break;
              t += max(uRegion.z * 0.75, t * 0.03);
            }
          }
          outColor = vec4(clamp(visAll, 0.0, 1.0), clamp(visFar, 0.0, 1.0), 0.0, 1.0);
        }`,
      uniforms: {
        uMacroH: { value: data.macroHTex },
        uFarH: { value: data.farHTex },
        uSunDir: { value: new THREE.Vector3(0, 1, 0) },
        uRegion: { value: new THREE.Vector4() },
      },
      depthTest: false,
      depthWrite: false,
    });
  }

  get macroRT() { return this.sets[this.front].macro; }
  get farRT() { return this.sets[this.front].far; }

  /** Synchronous full bake into the visible buffers. */
  bake(sunDir) {
    this.job = null;
    const u = this.material.uniforms;
    u.uSunDir.value.copy(sunDir).normalize();
    const set = this.sets[this.front];
    u.uRegion.value.set(MACRO_MIN, MACRO_MIN, MACRO_SIZE / set.macro.width, BAKED_NEAR_SKIP);
    runFullscreen(this.renderer, this.material, set.macro, 256);
    u.uRegion.value.set(FAR_MIN, FAR_MIN, FAR_SIZE / set.far.width, 0);
    runFullscreen(this.renderer, this.material, set.far, 256);
    this.bakedDir = sunDir.clone().normalize();
  }

  get busy() {
    return this.job !== null;
  }

  /** Start baking into the back buffers; call step() every frame. */
  begin(sunDir) {
    const set = this.sets[1 - this.front];
    const tiles = [];
    const tile = 256;
    for (const [rt, min, size, skip] of [[set.macro, MACRO_MIN, MACRO_SIZE, BAKED_NEAR_SKIP], [set.far, FAR_MIN, FAR_SIZE, 0]]) {
      for (let y = 0; y < rt.height; y += tile) {
        for (let x = 0; x < rt.width; x += tile) tiles.push({ rt, min, size, skip, x, y, w: Math.min(tile, rt.width - x), h: Math.min(tile, rt.height - y) });
      }
    }
    this.job = { dir: sunDir.clone().normalize(), tiles, i: 0 };
  }

  /** Render up to maxTiles tiles of the pending bake; swaps when complete. */
  step(maxTiles = 4) {
    const job = this.job;
    if (!job) return false;
    const r = this.renderer;
    if (!this._mesh) {
      const tri = new THREE.BufferGeometry();
      tri.setAttribute('position', new THREE.Float32BufferAttribute([-1, -1, 0, 3, -1, 0, -1, 3, 0], 3));
      this._mesh = new THREE.Mesh(tri, this.material);
      this._mesh.frustumCulled = false;
    }
    const u = this.material.uniforms;
    u.uSunDir.value.copy(job.dir);
    const prevTarget = r.getRenderTarget();
    const prevAutoClear = r.autoClear;
    r.autoClear = false;
    for (let n = 0; n < maxTiles && job.i < job.tiles.length; n++, job.i++) {
      const t = job.tiles[job.i];
      u.uRegion.value.set(t.min, t.min, t.size / t.rt.width, t.skip);
      t.rt.viewport.set(0, 0, t.rt.width, t.rt.height);
      t.rt.scissor.set(t.x, t.y, t.w, t.h);
      t.rt.scissorTest = true;
      r.setRenderTarget(t.rt);
      r.render(this._mesh, this._cam);
      t.rt.scissorTest = false;
    }
    r.setRenderTarget(prevTarget);
    r.autoClear = prevAutoClear;
    if (job.i >= job.tiles.length) {
      this.front = 1 - this.front;
      this.bakedDir = job.dir;
      this.job = null;
      if (this.onSwap) this.onSwap(this.macroRT.texture, this.farRT.texture);
      return true;
    }
    return false;
  }

  uniforms() {
    return {
      uSunVisMacro: { value: this.macroRT.texture },
      uSunVisFar: { value: this.farRT.texture },
    };
  }
}

