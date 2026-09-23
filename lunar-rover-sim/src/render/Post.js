import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { SMAAPass } from 'three/examples/jsm/postprocessing/SMAAPass.js';
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js';
import { N8AOPass } from 'n8ao';

const FinalShader = {
  uniforms: {
    tDiffuse: { value: null },
    uTime: { value: 0 },
    uGrain: { value: 0.035 },
    uVignette: { value: 0.32 },
    uAberration: { value: 0.0014 },
    uContrast: { value: 1.09 },
    uResolution: { value: new THREE.Vector2(1, 1) },
  },
  vertexShader: /* glsl */ `
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse;
    uniform float uTime, uGrain, uVignette, uAberration, uContrast;
    uniform vec2 uResolution;
    varying vec2 vUv;
    float hash(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
    void main() {
      vec2 c = vUv - 0.5;
      float r2 = dot(c, c);
      vec2 off = c * r2 * uAberration * 8.0;
      vec3 col;
      col.r = texture2D(tDiffuse, vUv + off).r;
      col.g = texture2D(tDiffuse, vUv).g;
      col.b = texture2D(tDiffuse, vUv - off).b;
      // gentle S-curve around mid grey (display referred)
      col = clamp((col - 0.5) * uContrast + 0.5, 0.0, 1.0);
      col *= 1.0 - uVignette * smoothstep(0.1, 0.75, r2 * 1.6);
      float n = hash(vUv * uResolution + fract(uTime * 13.7) * 91.0) + hash(vUv * uResolution * 1.37 - fract(uTime * 7.3) * 57.0) - 1.0;
      float lum = dot(col, vec3(0.299, 0.587, 0.114));
      col += n * uGrain * (0.35 + 0.65 * (1.0 - lum)) ;
      gl_FragColor = vec4(col, 1.0);
    }`,
};

export class Post {
  constructor(renderer, scene, camera, { ao = true, bloom = true, smaa = true, halfResAO = true } = {}) {
    this.renderer = renderer;
    const size = renderer.getSize(new THREE.Vector2());
    const pr = renderer.getPixelRatio();
    const w = Math.floor(size.x * pr), h = Math.floor(size.y * pr);
    this.composer = new EffectComposer(renderer);
    this.composer.setPixelRatio(pr);
    this.composer.setSize(size.x, size.y);

    if (ao) {
      this.aoPass = new N8AOPass(scene, camera, w, h);
      const c = this.aoPass.configuration;
      c.aoRadius = 1.6;
      c.distanceFalloff = 0.6;
      c.intensity = 2.6;
      c.aoSamples = 16;
      c.denoiseSamples = 8;
      c.denoiseRadius = 12;
      c.halfRes = halfResAO;
      c.depthAwareUpsampling = true;
      c.gammaCorrection = false;
      c.screenSpaceRadius = false;
      c.color = new THREE.Color(0, 0, 0);
      this.composer.addPass(this.aoPass);
    } else {
      this.composer.addPass(new RenderPass(scene, camera));
    }
    if (bloom) {
      this.bloomPass = new UnrealBloomPass(new THREE.Vector2(w, h), 0.18, 0.4, 3.0);
      this.composer.addPass(this.bloomPass);
    }
    this.composer.addPass(new OutputPass());
    if (smaa) {
      this.smaaPass = new SMAAPass(w, h);
      this.composer.addPass(this.smaaPass);
    }
    this.finalPass = new ShaderPass(FinalShader);
    this.finalPass.uniforms.uResolution.value.set(w, h);
    this.composer.addPass(this.finalPass);
  }

  setPixelRatio(pr) {
    this.composer.setPixelRatio(pr);
    const size = this.renderer.getSize(new THREE.Vector2());
    this.setSize(size.x, size.y);
  }

  setSize(width, height) {
    this.composer.setSize(width, height);
    const pr = this.renderer.getPixelRatio();
    this.finalPass.uniforms.uResolution.value.set(width * pr, height * pr);
  }

  render(dt) {
    this.finalPass.uniforms.uTime.value += dt;
    this.composer.render(dt);
  }
}
