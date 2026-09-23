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
    this.macroRT = new THREE.WebGLRenderTarget(macroShadowRes, macroShadowRes, opts);
    this.farRT = new THREE.WebGLRenderTarget(farShadowRes, farShadowRes, opts);

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

  bake(sunDir) {
    const u = this.material.uniforms;
    u.uSunDir.value.copy(sunDir).normalize();
    u.uRegion.value.set(MACRO_MIN, MACRO_MIN, MACRO_SIZE / this.macroRT.width, BAKED_NEAR_SKIP);
    runFullscreen(this.renderer, this.material, this.macroRT, 256);
    u.uRegion.value.set(FAR_MIN, FAR_MIN, FAR_SIZE / this.farRT.width, 0);
    runFullscreen(this.renderer, this.material, this.farRT, 256);
  }

  uniforms() {
    return {
      uSunVisMacro: { value: this.macroRT.texture },
      uSunVisFar: { value: this.farRT.texture },
    };
  }
}
